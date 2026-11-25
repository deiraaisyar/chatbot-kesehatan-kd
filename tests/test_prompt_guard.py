from __future__ import annotations

import json
import unittest
from pathlib import Path

from app import guard
from app.prompt import SYS_STUDENT, card_text, user_msg

ROOT = Path(__file__).resolve().parent.parent
CARDS = json.loads(
    (ROOT / "data" / "final" / "cards_sample.json").read_text(encoding="utf-8")
)


class PromptTest(unittest.TestCase):
    def test_system_prompt_is_the_training_prompt(self) -> None:
        self.assertEqual(
            SYS_STUDENT,
            "Kamu asisten kesehatan yang hanya menjelaskan kartu hasil pasien. Gunakan hanya angka di kartu, jangan mendiagnosis, "
            "jangan menyebut nama obat atau dosis, selalu katakan ini bukan diagnosis dan anjurkan menemui dokter. Jawab dalam bahasa Indonesia.",
        )

    def test_card_text_and_user_message(self) -> None:
        card = CARDS[0]
        text = card_text(card)
        self.assertIn("Tekanan darah: 120/68 mmHg (normal)", text)
        self.assertIn("Hipertensi: sekitar 5% (tingkat rendah)", text)
        self.assertEqual(
            user_msg(card, "Tolong jelaskan hasil saya."),
            f"KARTU HASIL:\n{text}\n\nPERTANYAAN: Tolong jelaskan hasil saya.",
        )


class GuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.low = CARDS[0]
        self.red = next(
            card for card in CARDS if card["jenis_contoh"] == "TD sangat tinggi"
        )

    def test_good_answer_passes(self) -> None:
        answer = (
            "Hasil Anda menunjukkan risiko hipertensi sekitar 5%, diabetes kurang dari 5%, "
            "dan kolesterol tinggi sekitar 15%, semuanya berada pada tingkat rendah. "
            "Ini perkiraan statistik, bukan diagnosis; sebaiknya berkonsultasi dengan dokter "
            "atau tenaga kesehatan untuk pemeriksaan lebih lanjut."
        )
        self.assertEqual(guard.check(self.low, answer), [])

    def test_drug_mention_fails(self) -> None:
        answer = (
            "Hasil Anda menunjukkan risiko rendah. Anda bisa minum metformin 500 mg. "
            "Ini perkiraan statistik, bukan diagnosis; sebaiknya berkonsultasi dengan dokter."
        )
        self.assertIn("drug_or_dose", guard.check(self.low, answer))

    def test_wrong_level_fails(self) -> None:
        answer = (
            "Risiko hipertensi Anda berada pada tingkat tinggi. "
            "Ini perkiraan statistik, bukan diagnosis; sebaiknya berkonsultasi dengan dokter."
        )
        self.assertIn("level:hipertensi", guard.check(self.low, answer))

    def test_truncated_and_missing_disclaimer_fail(self) -> None:
        flags = guard.check(self.low, "Hasil Anda perlu diperhatikan", finish="length")
        self.assertIn("truncated", flags)
        self.assertIn("no_disclaimer", flags)

    def test_red_flag_requires_segera(self) -> None:
        answer = (
            "Tekanan darah Anda sangat tinggi. Ini perkiraan statistik, bukan diagnosis; "
            "sebaiknya berkonsultasi dengan dokter atau tenaga kesehatan."
        )
        self.assertIn("no_redflag", guard.check(self.red, answer))

        answer += " Segera pergi ke IGD atau fasilitas kesehatan terdekat."
        self.assertNotIn("no_redflag", guard.check(self.red, answer))

    def test_fallback_contains_card_and_disclaimer(self) -> None:
        fallback = guard.fallback_answer(self.red)
        self.assertIn("Peringatan:", fallback)
        self.assertIn("segera", fallback.lower())
        self.assertIn("bukan diagnosis", fallback.lower())


if __name__ == "__main__":
    unittest.main()