"""Client for the local llama.cpp OpenAI-compatible chat server."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class ChatBackendError(Exception):
    def __init__(self, message: str, status: int = 503, code: str = "chat_unavailable") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class LlamaChat:
    def __init__(
        self,
        base_url: str,
        model_version: str,
        timeout_seconds: float = 115.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_version = model_version
        self.timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
        )

    async def health(self) -> bool:
        try:
            response = await self._client.get("/health", timeout=1.5)
            return response.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> tuple[str, str]:
        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
        }
        try:
            response = await self._client.post("/v1/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise ChatBackendError(
                "Model terlalu lama menghasilkan jawaban.",
                status=504,
                code="model_timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise ChatBackendError(
                "Chat model tidak dapat dihubungi.",
                status=503,
                code="chat_unavailable",
            ) from exc

        if response.status_code >= 400:
            logger.error(
                "llama-server returned %s: %s",
                response.status_code,
                response.text[:500],
            )
            raise ChatBackendError(
                "Chat model mengembalikan error.",
                status=503,
                code="chat_unavailable",
            )

        try:
            data = response.json()
            choice = data["choices"][0]
            text = (choice.get("message") or {}).get("content") or ""
            finish = choice.get("finish_reason") or "stop"
            return text, str(finish)
        except Exception as exc:
            raise ChatBackendError(
                "Respons chat model tidak dapat dibaca.",
                status=502,
                code="chat_backend_error",
            ) from exc

    async def close(self) -> None:
        await self._client.aclose()