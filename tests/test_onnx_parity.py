from __future__ import annotations

import csv
import importlib.util
import json
import unittest
from pathlib import Path

from app.risk import RiskRegistry

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(
    importlib.util.find_spec("onnxruntime") is not None,
    "onnxruntime is not installed in this environment",
)
class OnnxParityTest(unittest.TestCase):
    def test_final_models_match_teacher_test_predictions(self) -> None:
        meta = json.loads((ROOT / "data" / "final" / "meta.json").read_text(encoding="utf-8"))
        registry = RiskRegistry(ROOT / "models", meta["features"])
        self.assertTrue(registry.ready(), registry.error)
        registry.warmup()

        with (ROOT / "data" / "final" / "test.csv").open(encoding="utf-8", newline="") as handle:
            row = next(csv.DictReader(handle))
        values = {
            name: (None if row[name] == "" else float(row[name]))
            for name in meta["features"]
        }
        for name in ("age", "male", "smoker", "fam_dm", "fam_mi", "vig_rec", "mod_rec"):
            if values[name] is not None:
                values[name] = int(values[name])

        with (ROOT / "data" / "final" / "teacher_test.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            expected_row = next(csv.DictReader(handle))

        predicted = registry.predict(values)
        for name, probability in predicted.items():
            expected = float(expected_row[f"p_{name}"])
            self.assertAlmostEqual(probability, expected, delta=1e-5, msg=name)


if __name__ == "__main__":
    unittest.main()