from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

from app import card

ROOT = Path(__file__).resolve().parent.parent


def _number(value: str, *, integer: bool = False):
    if value == "":
        return None
    return int(float(value)) if integer else float(value)


def _load_train() -> dict[int, dict]:
    rows = {}
    with (ROOT / "data" / "final" / "train.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[int(row["SEQN"])] = {
                "age": _number(row["age"], integer=True),
                "male": _number(row["male"], integer=True),
                "bmi": _number(row["bmi"]),
                "sbp": _number(row["sbp"]),
                "dbp": _number(row["dbp"]),
                "smoker": _number(row["smoker"], integer=True),
                "waist": _number(row["waist"]),
                "hdl": _number(row["hdl"]),
                "fam_dm": _number(row["fam_dm"], integer=True),
                "fam_mi": _number(row["fam_mi"], integer=True),
                "vig_rec": _number(row["vig_rec"], integer=True),
                "mod_rec": _number(row["mod_rec"], integer=True),
            }
    return rows


class CardParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        card.configure(ROOT / "data" / "final" / "risk_levels.json")
        cls.samples = json.loads(
            (ROOT / "data" / "final" / "cards_sample.json").read_text(encoding="utf-8")
        )
        cls.train = _load_train()

    def test_all_sample_cards_are_reproduced(self) -> None:
        for sample in self.samples:
            with self.subTest(patient=sample["id_pasien"]):
                result = card.make_card(
                    self.train[sample["id_pasien"]],
                    {name: entry["probabilitas"] for name, entry in sample["risiko"].items()},
                )
                self.assertEqual(result["versi"], sample["versi"])
                self.assertEqual(result["pasien"], sample["pasien"])
                self.assertEqual(result["kategori"], sample["kategori"])
                self.assertEqual(result["risiko"], sample["risiko"])
                self.assertEqual(result["data_tidak_lengkap"], sample["data_tidak_lengkap"])
                self.assertEqual(result["peringatan"], sample["peringatan"])
                self.assertEqual(result["disclaimer"], sample["disclaimer"])

    def test_red_flag_warning(self) -> None:
        sample = next(item for item in self.samples if item["jenis_contoh"] == "TD sangat tinggi")
        result = card.make_card(
            self.train[sample["id_pasien"]],
            {name: entry["probabilitas"] for name, entry in sample["risiko"].items()},
        )
        self.assertTrue(any("sangat tinggi" in warning for warning in result["peringatan"]))


if __name__ == "__main__":
    unittest.main()