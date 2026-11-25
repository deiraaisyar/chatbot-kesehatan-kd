"""Deterministic result-card builder.

This is a direct port of ``make_card`` and the category helpers in
``capstone_classifier.ipynb`` section 9. Keep the thresholds and output shape
identical to the notebook; the dashboard and the distilled LLM were built
against this contract.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Mapping

from .contract import DISCLAIMER, DISEASES, FEATURES

RANGES = {
    "age": (18, 120),
    "bmi": (10, 80),
    "sbp": (70, 260),
    "dbp": (40, 150),
    "waist": (40, 200),
    "hdl": (10, 200),
}

LEVELS: dict[str, dict[str, float]] = {}


def configure(risk_levels_path: Path) -> None:
    """Load the fitted prevalence-relative cut-offs from ``risk_levels.json``."""
    global LEVELS
    LEVELS = json.loads(Path(risk_levels_path).read_text(encoding="utf-8"))
    missing = [name for name in DISEASES if name not in LEVELS]
    if missing:
        raise ValueError(f"risk_levels.json is missing: {missing}")


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def bp_category(sbp: float, dbp: float) -> str:
    stage = (
        3
        if (sbp >= 140 or dbp >= 90)
        else 2
        if (sbp >= 130 or dbp >= 80)
        else 1
        if (sbp >= 120)
        else 0
    )
    return [
        "normal",
        "meningkat (elevated)",
        "hipertensi stage 1",
        "hipertensi stage 2",
    ][stage]


def bmi_category(bmi: float) -> str:
    return (
        "berat badan kurang"
        if bmi < 18.5
        else "normal"
        if bmi < 23
        else "berat badan lebih"
        if bmi < 25
        else "obesitas I"
        if bmi < 30
        else "obesitas II"
    )


def risk_level(probability: float, name: str) -> str:
    cutoffs = LEVELS[name]
    return (
        "rendah"
        if probability < cutoffs["low_below"]
        else "tinggi"
        if probability >= cutoffs["high_from"]
        else "sedang"
    )


def yesno(value: object) -> str:
    if _is_missing(value):
        return "tidak diketahui"
    return "ya" if value == 1 else "tidak"


def make_card(
    values: Mapping[str, float | int | None],
    probabilities: Mapping[str, float],
) -> dict:
    if not LEVELS:
        raise RuntimeError("card.configure() has not been called.")
    if not probabilities:
        raise ValueError("probabilities are required.")

    warnings: list[str] = []
    missing = [feature for feature in FEATURES if _is_missing(values.get(feature))]

    for feature, (low, high) in RANGES.items():
        value = values.get(feature)
        if not _is_missing(value) and not low <= float(value) <= high:
            warnings.append(
                f"nilai {feature} di luar rentang wajar ({low}-{high}): {value}"
            )

    if float(values["sbp"]) <= float(values["dbp"]):
        warnings.append(
            "tekanan darah sistolik tidak lebih besar dari diastolik, periksa input"
        )
    if float(values["sbp"]) >= 180 or float(values["dbp"]) >= 120:
        warnings.append(
            "tekanan darah sangat tinggi: anjurkan segera ke fasilitas kesehatan"
        )

    waist = values.get("waist")
    male = int(values["male"]) == 1
    has_waist = not _is_missing(waist)

    return {
        "versi": 1,
        "pasien": {
            "umur": int(values["age"]),
            "jenis_kelamin": "laki-laki" if male else "perempuan",
            "bmi": values["bmi"],
            "td_sistolik": round(float(values["sbp"])),
            "td_diastolik": round(float(values["dbp"])),
            "pernah_merokok": yesno(values.get("smoker")),
            "lingkar_pinggang_cm": waist if has_waist else None,
            "hdl_mgdl": values["hdl"],
            "riwayat_diabetes_keluarga": yesno(values.get("fam_dm")),
            "riwayat_serangan_jantung_keluarga": yesno(values.get("fam_mi")),
            "olahraga_berat_rekreasi": yesno(values.get("vig_rec")),
            "olahraga_sedang_rekreasi": yesno(values.get("mod_rec")),
        },
        "kategori": {
            "tekanan_darah": bp_category(float(values["sbp"]), float(values["dbp"])),
            "bmi": bmi_category(float(values["bmi"])),
            "lingkar_pinggang": (
                "tidak diketahui"
                if not has_waist
                else "di atas batas (obesitas sentral)"
                if float(waist) > (90 if male else 80)
                else "normal"
            ),
            "hdl": "rendah" if float(values["hdl"]) < (40 if male else 50) else "cukup",
        },
        "risiko": {
            name: {
                "probabilitas": round(float(probabilities[name]), 3),
                "persen_perkiraan": (
                    "<5%"
                    if probabilities[name] < 0.025
                    else ">95%"
                    if probabilities[name] > 0.975
                    else f"{int(math.floor(probabilities[name] * 100 / 5 + 0.5) * 5)}%"
                ),
                "tingkat": risk_level(float(probabilities[name]), name),
            }
            for name in DISEASES
        },
        "data_tidak_lengkap": missing,
        "peringatan": warnings,
        "disclaimer": DISCLAIMER,
    }