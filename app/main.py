"""FastAPI application for the Raspberry Pi health-risk API and dashboard."""

from __future__ import annotations

import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import card, guard
from .chat import ChatBackendError, LlamaChat
from .config import Settings, load_settings
from .contract import API_VERSION, DISCLAIMER, DISEASES, FEATURE_META
from .prompt import SYS_STUDENT, user_msg
from .risk import RiskRegistry
from .schemas import AssessmentRequest, ChatRequest
from .store import AssessmentStore, SessionStore, iso

logger = logging.getLogger("health_api")
bearer = HTTPBearer(auto_error=False)


class ServiceError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        fields: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or {}


def _error(
    request: Request,
    status: int,
    code: str,
    message: str,
    fields: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return JSONResponse(
        status_code=status,
        content={
            "error": error,
            "request_id": getattr(request.state, "request_id", ""),
        },
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.settings = settings
        application.state.started_at = time.time()
        application.state.registry = None
        application.state.registry_error = None

        try:
            meta = json.loads(settings.meta_path.read_text(encoding="utf-8"))
            features = meta["features"]
            card.configure(settings.risk_levels_path)
            registry = RiskRegistry(
                settings.model_dir,
                features,
                version=settings.risk_model_version,
            )
            registry.warmup()
            application.state.registry = registry
            if registry.error:
                application.state.registry_error = registry.error
        except Exception as exc:  # noqa: BLE001 - report degradation, keep UI up
            application.state.registry_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Risk registry failed to initialize")

        application.state.assessments = AssessmentStore(settings.assessment_ttl_seconds)
        application.state.sessions = SessionStore(settings.session_ttl_seconds)
        application.state.chat = LlamaChat(
            settings.chat_base_url,
            settings.chat_model_version,
            settings.chat_timeout_seconds,
        )
        try:
            yield
        finally:
            await application.state.chat.close()

    app = FastAPI(
        title="Kartu Risiko Pi API",
        version=API_VERSION,
        description="Local risk assessment and result-card chatbot API.",
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Client-Version",
        ],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or (
            f"req_{uuid.uuid4().hex}"
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError):
        return _error(request, exc.status, exc.code, exc.message, exc.fields)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        fields: dict[str, str] = {}
        for item in exc.errors():
            location = item.get("loc") or ()
            name = str(location[-1]) if location else "body"
            fields[name] = item.get("msg", "Nilai tidak valid.")
        return _error(
            request,
            422,
            "validation_error",
            "Input tidak valid.",
            fields,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled API error: %s", exc)
        return _error(
            request,
            500,
            "internal_error",
            "Terjadi kesalahan pada server.",
        )

    async def require_auth(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> None:
        expected = request.app.state.settings.api_token
        if not expected:
            return
        if (
            credentials is None
            or credentials.scheme.lower() != "bearer"
            or not secrets.compare_digest(credentials.credentials, expected)
        ):
            raise ServiceError(
                401,
                "unauthorized",
                "Bearer token Raspberry Pi tidak valid.",
            )

    @app.get("/v1/health")
    async def health(request: Request):
        application = request.app
        registry = application.state.registry
        risk = (
            registry.health()
            if registry is not None
            else {name: "not_ready" for name in DISEASES}
        )
        ready = registry is not None and registry.ready()
        chat_ok = await application.state.chat.health()
        status = "ok" if ready and chat_ok else "degraded" if ready else "down"
        return {
            "status": status,
            "risk": risk,
            "chat": {
                "available": chat_ok,
                "backend": "llama.cpp" if chat_ok else "unavailable",
            },
            "versions": {
                "risk": application.state.settings.risk_model_version,
                "chat": application.state.settings.chat_model_version,
            },
            "uptime_s": int(time.time() - application.state.started_at),
        }

    @app.get("/v1/meta", dependencies=[Depends(require_auth)])
    async def meta(request: Request):
        application = request.app
        chat_ok = await application.state.chat.health()
        runtime = application.state.settings
        return {
            "api_version": API_VERSION,
            "features": FEATURE_META,
            "chat": {
                "available": chat_ok,
                "multi_turn": runtime.chat_multi_turn,
                "max_turns": runtime.effective_max_turns,
                "session_ttl_seconds": runtime.session_ttl_seconds,
                "model_version": runtime.chat_model_version,
            },
            "disclaimer": DISCLAIMER,
        }

    @app.post(
        "/v1/assessments",
        status_code=201,
        dependencies=[Depends(require_auth)],
    )
    async def create_assessment(payload: AssessmentRequest, request: Request):
        application = request.app
        registry = application.state.registry
        if registry is None or not registry.ready():
            raise ServiceError(
                503,
                "risk_unavailable",
                "Model risiko di Raspberry Pi belum siap.",
            )
        values = payload.model_values()
        probabilities = await run_in_threadpool(registry.predict, values)
        result_card = await run_in_threadpool(card.make_card, values, probabilities)
        assessment = application.state.assessments.create(
            result_card,
            probabilities,
            {
                "risk": registry.version,
                "chat": application.state.settings.chat_model_version,
            },
        )
        return {
            "assessment_id": assessment.id,
            "created_at": iso(assessment.created_at),
            "expires_at": iso(assessment.expires_at),
            "probabilities": probabilities,
            "card": result_card,
            "versions": assessment.versions,
        }

    @app.get(
        "/v1/assessments/{assessment_id}",
        dependencies=[Depends(require_auth)],
    )
    async def get_assessment(assessment_id: str, request: Request):
        assessment = request.app.state.assessments.get(assessment_id)
        if assessment is None:
            raise ServiceError(
                404,
                "assessment_not_found",
                "Hasil sudah kedaluwarsa atau tidak ditemukan.",
            )
        return {
            "assessment_id": assessment.id,
            "created_at": iso(assessment.created_at),
            "expires_at": iso(assessment.expires_at),
            "probabilities": assessment.probabilities,
            "card": assessment.card,
            "versions": assessment.versions,
        }

    @app.post(
        "/v1/assessments/{assessment_id}/chat",
        dependencies=[Depends(require_auth)],
    )
    async def chat_with_assessment(
        assessment_id: str,
        payload: ChatRequest,
        request: Request,
    ):
        application = request.app
        runtime = application.state.settings
        assessment = application.state.assessments.get(assessment_id)
        if assessment is None:
            raise ServiceError(
                404,
                "assessment_not_found",
                "Hasil sudah kedaluwarsa atau tidak ditemukan.",
            )

        chat_backend: LlamaChat = application.state.chat
        if not await chat_backend.health():
            raise ServiceError(
                503,
                "chat_unavailable",
                "Fitur tanya jawab belum tersedia.",
            )

        if payload.session_id:
            session = application.state.sessions.get(
                payload.session_id, assessment_id
            )
            if session is None:
                raise ServiceError(
                    404,
                    "session_not_found",
                    "Sesi tanya jawab berakhir. Silakan mulai sesi baru.",
                )
        else:
            session = application.state.sessions.create(assessment_id)

        if len(session.turns) >= runtime.effective_max_turns:
            raise ServiceError(
                409,
                "turn_limit_reached",
                "Batas pertanyaan untuk sesi ini tercapai.",
            )

        messages = [{"role": "system", "content": SYS_STUDENT}]
        if runtime.chat_multi_turn:
            history_limit = max(0, runtime.effective_max_turns - 1)
            history = session.turns[-history_limit:] if history_limit else []
        else:
            history = []
        for turn in history:
            messages.append(
                {"role": "user", "content": user_msg(assessment.card, turn.question)}
            )
            messages.append({"role": "assistant", "content": turn.answer})
        messages.append(
            {"role": "user", "content": user_msg(assessment.card, payload.message)}
        )

        try:
            raw_answer, finish = await chat_backend.chat(
                messages,
                max_tokens=runtime.chat_max_tokens,
                temperature=runtime.chat_temperature,
                top_p=runtime.chat_top_p,
            )
        except ChatBackendError as exc:
            raise ServiceError(exc.status, exc.code, str(exc)) from exc

        answer = raw_answer.strip()
        flags = guard.check(assessment.card, answer, finish=finish)
        fallback = not answer or bool(flags)
        if fallback:
            answer = guard.fallback_answer(assessment.card)

        try:
            turn_number = application.state.sessions.add_turn(
                session,
                payload.message,
                answer,
                fallback,
            )
        except ValueError as exc:
            raise ServiceError(
                410,
                "session_not_found",
                "Sesi tanya jawab berakhir. Silakan mulai sesi baru.",
            ) from exc

        return {
            "session_id": session.id,
            "answer": answer,
            "turn": turn_number,
            "guard": {"ok": not bool(flags), "flags": flags},
            "fallback": fallback,
            "model_version": runtime.chat_model_version,
        }

    dashboard_dir = Path(settings.dashboard_dir)
    if (dashboard_dir / "index.html").is_file():
        app.mount(
            "/",
            StaticFiles(directory=str(dashboard_dir), html=True),
            name="dashboard",
        )
    else:
        # Useful while developing the API before the dashboard is copied in.
        @app.get("/")
        async def root():
            return {
                "service": "Kartu Risiko Pi API",
                "version": API_VERSION,
                "dashboard": False,
                "docs": "/docs",
            }

    return app


app = create_app()