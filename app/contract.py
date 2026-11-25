"""Shared API/card contract for the dashboard and the Pi backend.

Keep this file aligned with the dashboard in ``dashboard/src`` and with the
result-card format produced by ``capstone_classifier.ipynb`` section 9.
"""

from __future__ import annotations

API_VERSION = "1.0"

# Order matters: this is the feature order expected by the three CatBoost ONNX
# models. ``data/final/meta.json`` is the source of truth at runtime; this is a
# fallback/validation copy.
FEATURES = [
    "age",
    "male",
    "bmi",
    "sbp",
    "dbp",
    "smoker",
    "waist",
    "hdl",
    "fam_dm",
    "fam_mi",
    "vig_rec",
    "mod_rec",
]

DISEASES = ["hipertensi", "diabetes", "kolesterol_tinggi"]

DIS_NAME = {
    "hipertensi": "Hipertensi",
    "diabetes": "Diabetes",
    "kolesterol_tinggi": "Kolesterol tinggi",
}

# Values exposed by GET /v1/meta and consumed by the dashboard form.
FEATURE_META = [
    {"name": "age", "label": "Umur", "type": "int", "required": True, "min": 18, "max": 120, "unit": "tahun"},
    {"name": "male", "label": "Jenis kelamin", "type": "binary", "required": True},
    {"name": "bmi", "label": "BMI", "type": "float", "required": True, "min": 10, "max": 80, "unit": "kg/m²"},
    {"name": "sbp", "label": "Sistolik", "type": "float", "required": True, "min": 70, "max": 260, "unit": "mmHg"},
    {"name": "dbp", "label": "Diastolik", "type": "float", "required": True, "min": 40, "max": 150, "unit": "mmHg"},
    {"name": "smoker", "label": "Pernah merokok (≥100 batang seumur hidup)", "type": "binary", "required": False},
    {"name": "waist", "label": "Lingkar pinggang", "type": "float", "required": False, "min": 40, "max": 200, "unit": "cm"},
    {"name": "hdl", "label": "Kolesterol HDL", "type": "float", "required": True, "min": 10, "max": 200, "unit": "mg/dL"},
    {"name": "fam_dm", "label": "Riwayat diabetes pada keluarga dekat", "type": "binary", "required": False},
    {"name": "fam_mi", "label": "Riwayat serangan jantung pada keluarga dekat", "type": "binary", "required": False},
    {"name": "vig_rec", "label": "Olahraga berat (rekreasi rutin)", "type": "binary", "required": False},
    {"name": "mod_rec", "label": "Olahraga sedang (rekreasi rutin)", "type": "binary", "required": False},
]

DISCLAIMER = (
    "Hasil ini adalah perkiraan risiko statistik dari data survei dewasa Amerika "
    "(NHANES), bukan diagnosis. Konsultasikan dengan dokter atau tenaga kesehatan "
    "untuk pemeriksaan dan keputusan medis."
)

# Human-readable labels for the internal keys in card.data_tidak_lengkap.
MISSING_LABELS = {
    "age": "Umur",
    "male": "Jenis kelamin",
    "bmi": "BMI",
    "sbp": "Tekanan darah sistolik",
    "dbp": "Tekanan darah diastolik",
    "smoker": "Status merokok",
    "waist": "Lingkar pinggang",
    "hdl": "HDL",
    "fam_dm": "Riwayat diabetes keluarga",
    "fam_mi": "Riwayat serangan jantung keluarga",
    "vig_rec": "Olahraga berat",
    "mod_rec": "Olahraga sedang",
}