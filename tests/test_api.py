from __future__ import annotations

import logging
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.contract import DISEASES
from app.main import create_app

ROOT = Path(__file__).resolve().parent.parent
logging.getLogger("app.risk").setLevel(logging.CRITICAL)
TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
LOW = {
    "age": 35,
    "male": 1,
    "bmi": 25.2,
    "sbp": 119,
    "dbp": 68,
    "smoker": 0,
    "waist": 88,
    "hdl": 46,
    "fam_dm": 0,
    "fam_mi": 0,
    "vig_rec": 1,
    "mod_rec": 1,
}
GOOD_ANSWER = (
    "Hasil Anda menunjukkan risiko hipertensi sekitar 5%, diabetes kurang dari 5%, "
    "dan kolesterol tinggi sekitar 15%, semuanya berada pada tingkat rendah. "
    "Ini perkiraan statistik, bukan diagnosis; sebaiknya berkonsultasi dengan dokter "
    "atau tenaga kesehatan untuk pemeriksaan lebih lanjut."
)


class FakeRegistry:
    version = "test-risk-model"

    def ready(self) -> bool:
        return True

    def health(self) -> dict[str, str]:
        return {name: "ok" for name in DISEASES}

    def predict(self, values: dict) -> dict[str, float]:
        return {"hipertensi": 0.062, "diabetes": 0.009, "kolesterol_tinggi": 0.143}


class FakeChat:
    def __init__(self, answer: str = GOOD_ANSWER) -> None:
        self.answer = answer
        self.calls: list[list[dict]] = []

    async def health(self) -> bool:
        return True

    async def chat(self, messages, **kwargs):
        self.calls.append(messages)
        return self.answer, "stop"

    async def close(self) -> None:
        return None


class ApiTest(unittest.TestCase):
    def setUp(self) -> None:
        settings = Settings(
            api_token=TOKEN,
            model_dir=ROOT / "does-not-exist",
            dashboard_dir=ROOT / "does-not-exist",
        )
        self.app = create_app(settings)
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self.app.state.registry = FakeRegistry()
        self.chat = FakeChat()
        self.app.state.chat = self.chat

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def _assess(self) -> dict:
        response = self.client.post("/v1/assessments", json=LOW, headers=HEADERS)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_health_is_public_and_reports_ready(self) -> None:
        response = self.client.get("/v1/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["risk"], {name: "ok" for name in DISEASES})
        self.assertTrue(body["chat"]["available"])

    def test_meta_requires_token_and_exposes_single_turn_default(self) -> None:
        self.assertEqual(self.client.get("/v1/meta").status_code, 401)
        response = self.client.get("/v1/meta", headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["api_version"], "1.0")
        self.assertEqual(len(body["features"]), 12)
        self.assertFalse(body["chat"]["multi_turn"])
        self.assertEqual(body["chat"]["max_turns"], 1)

    def test_assessment_returns_the_dashboard_card(self) -> None:
        body = self._assess()
        self.assertTrue(body["assessment_id"].startswith("asm_"))
        self.assertEqual(set(body["probabilities"]), set(DISEASES))
        self.assertEqual(body["card"]["pasien"]["umur"], 35)
        self.assertEqual(body["card"]["kategori"]["tekanan_darah"], "normal")
        self.assertEqual(body["card"]["risiko"]["hipertensi"]["tingkat"], "rendah")
        self.assertEqual(body["card"]["data_tidak_lengkap"], [])
        self.assertIn("bukan diagnosis", body["card"]["disclaimer"])

    def test_validation_errors_are_field_errors(self) -> None:
        payload = dict(LOW)
        payload.pop("hdl")
        response = self.client.post("/v1/assessments", json=payload, headers=HEADERS)
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"]["code"], "validation_error")
        self.assertIn("hdl", body["error"]["fields"])
        self.assertTrue(body["request_id"])

    def test_optional_nulls_are_listed_as_missing(self) -> None:
        payload = {
            **LOW,
            "smoker": None,
            "waist": None,
            "fam_dm": None,
            "fam_mi": None,
            "vig_rec": None,
            "mod_rec": None,
        }
        response = self.client.post("/v1/assessments", json=payload, headers=HEADERS)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(
            response.json()["card"]["data_tidak_lengkap"],
            ["smoker", "waist", "fam_dm", "fam_mi", "vig_rec", "mod_rec"],
        )

    def test_chat_uses_session_and_returns_guard(self) -> None:
        assessment = self._assess()
        response = self.client.post(
            f"/v1/assessments/{assessment['assessment_id']}/chat",
            json={"session_id": None, "message": "Tolong jelaskan hasil saya."},
            headers=HEADERS,
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["session_id"].startswith("cht_"))
        self.assertEqual(body["turn"], 1)
        self.assertFalse(body["fallback"])
        self.assertTrue(body["guard"]["ok"])
        self.assertEqual(len(self.chat.calls), 1)

        # Single-turn is the safe default for the current student model.
        second = self.client.post(
            f"/v1/assessments/{assessment['assessment_id']}/chat",
            json={"session_id": body["session_id"], "message": "Kenapa?"},
            headers=HEADERS,
        )
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"]["code"], "turn_limit_reached")

    def test_chat_falls_back_when_guard_rejects(self) -> None:
        self.chat.answer = "Tidak bisa."
        assessment = self._assess()
        response = self.client.post(
            f"/v1/assessments/{assessment['assessment_id']}/chat",
            json={"session_id": None, "message": "Tolong jelaskan hasil saya."},
            headers=HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["fallback"])
        self.assertIn("bukan diagnosis", body["answer"].lower())
        self.assertTrue(body["guard"]["flags"])


class MultiTurnApiTest(unittest.TestCase):
    def setUp(self) -> None:
        settings = Settings(
            api_token=TOKEN,
            model_dir=ROOT / "does-not-exist",
            dashboard_dir=ROOT / "does-not-exist",
            chat_multi_turn=True,
            chat_max_turns=2,
        )
        self.app = create_app(settings)
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self.app.state.registry = FakeRegistry()
        self.chat = FakeChat()
        self.app.state.chat = self.chat

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def test_two_turns_include_previous_question_and_answer(self) -> None:
        assessment = self.client.post(
            "/v1/assessments", json=LOW, headers=HEADERS
        ).json()
        first = self.client.post(
            f"/v1/assessments/{assessment['assessment_id']}/chat",
            json={"session_id": None, "message": "Tolong jelaskan hasil saya."},
            headers=HEADERS,
        )
        self.assertEqual(first.status_code, 200, first.text)
        session_id = first.json()["session_id"]

        second = self.client.post(
            f"/v1/assessments/{assessment['assessment_id']}/chat",
            json={"session_id": session_id, "message": "Apa yang bisa saya lakukan?"},
            headers=HEADERS,
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["turn"], 2)
        self.assertEqual(len(self.chat.calls), 2)
        second_messages = self.chat.calls[1]
        self.assertEqual(second_messages[0]["role"], "system")
        self.assertEqual(second_messages[1]["role"], "user")
        self.assertEqual(second_messages[2]["role"], "assistant")
        self.assertEqual(second_messages[3]["role"], "user")

        third = self.client.post(
            f"/v1/assessments/{assessment['assessment_id']}/chat",
            json={"session_id": session_id, "message": "Kenapa?"},
            headers=HEADERS,
        )
        self.assertEqual(third.status_code, 409)


if __name__ == "__main__":
    unittest.main()