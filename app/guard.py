"""Runtime safety/consistency checks for generated answers.

Adapted from the automatic validator in ``capstone_kd.ipynb`` section 6. At
runtime the question type is not known, so refusal/card-reference checks are
only applied when a type is supplied. The safety checks always apply.
"""

from __future__ import annotations

import re

from .prompt import card_text

DRUGS = (
    r"metformin|insulin|glibenklamid|glimepirid|gliklazid|amlodipin|amlodipine|"
    r"captopril|kaptopril|lisinopril|ramipril|valsartan|losartan|candesartan|"
    r"telmisartan|bisoprolol|atenolol|propranolol|furosemid|hidroklorotiazid|"
    r"hctz|simvastatin|atorvastatin|rosuvastatin|statin|fenofibrat|aspirin|"
    r"asetosal|warfarin|clopidogrel|paracetamol|ibuprofen|nifedipin|diltiazem|"
    r"spironolakton|sulfonilurea|acarbose|sitagliptin|empagliflozin|dapagliflozin|"
    r"liraglutide|semaglutide"
)
EN = {
    "the", "and", "you", "your", "is", "are", "of", "to", "with", "for", "that",
    "this", "risk", "blood", "pressure", "please", "doctor", "should",
}
ID = {
    "yang", "dan", "dengan", "untuk", "anda", "saya", "risiko", "tidak", "atau",
    "ini", "dari", "ke", "di", "pada", "dokter", "adalah",
}
WL = {
    1, 2, 3, 4, 5, 7, 10, 18.5, 23, 25, 30, 40, 50, 75, 80, 90, 100, 120, 130,
    140, 150, 180,
}
DISW = {
    "hipertensi": ("hipertensi", "tekanan darah tinggi", "darah tinggi"),
    "diabetes": ("diabetes", "gula darah"),
    "kolesterol_tinggi": ("kolesterol",),
}

CARD_TYPES = {"jelaskan", "kenapa_tingkat", "arti_persen", "arti_kategori"}
REFUSAL_TYPES = {
    "obat", "diagnosis", "luar_topik", "ubah_angka", "penyakit_lain", "hipotetis",
}
REFUSE = (
    r"tidak (?:dapat|bisa|boleh|mampu|menghitung|mengubah|mendiagnosis|memberi|"
    r"menilai|menyarankan|merekomendasikan)|belum (?:bisa|dapat)|di luar|"
    r"hanya (?:bisa|dapat|mencakup|menjelaskan|membantu)"
)


def own_numbers(card: dict) -> set[float]:
    patient = card["pasien"]
    values = {
        float(value)
        for value in (
            patient["umur"],
            patient["bmi"],
            patient["td_sistolik"],
            patient["td_diastolik"],
            patient["lingkar_pinggang_cm"],
            patient["hdl_mgdl"],
        )
        if value is not None
    }
    for disease in DISW:
        values |= {
            float(value)
            for value in re.findall(r"\d+", card["risiko"][disease]["persen_perkiraan"])
        }
    return values


def allowed_numbers(card: dict) -> set[float]:
    patient = card["pasien"]
    values: set[float] = set()
    for value in (
        patient["umur"],
        patient["bmi"],
        patient["td_sistolik"],
        patient["td_diastolik"],
        patient["lingkar_pinggang_cm"],
        patient["hdl_mgdl"],
    ):
        if value is not None:
            values |= {float(value), float(round(value)), round(float(value), 1)}
    for disease in DISW:
        values |= {
            float(value)
            for value in re.findall(r"\d+", card["risiko"][disease]["persen_perkiraan"])
        }
    return values | WL


def is_red_flag(card: dict) -> bool:
    return any("sangat tinggi" in warning.lower() for warning in card.get("peringatan", []))


def check(
    card: dict,
    text: str,
    finish: str = "stop",
    question_type: str | None = None,
) -> list[str]:
    """Return a list of failures. An empty list means the answer is acceptable."""
    bad: list[str] = []
    text = text.strip()
    if not text:
        return ["empty"]

    lower = text.lower()
    words = re.findall(r"[a-zA-Z']+", lower)

    if finish == "length" or not re.search(r'[.!?)\]"]$', text):
        bad.append("truncated")

    word_count = len(text.split())
    if not 30 <= word_count <= 230:
        bad.append(f"length:{word_count}")

    if (
        sum(word in EN for word in words) >= 4
        and sum(word in ID for word in words) < 2 * sum(word in EN for word in words)
    ):
        bad.append("not_indonesian")
    if sum(word in ID for word in words) < max(3, len(words) // 20):
        bad.append("not_indonesian")

    allowed = allowed_numbers(card)
    extra = sorted(
        {
            float(match.replace(",", "."))
            for match in re.findall(r"\d+(?:[.,]\d+)?", text)
            if float(match.replace(",", ".")) not in allowed
        }
    )
    if extra:
        bad.append(f"numbers:{extra[:4]}")

    if question_type in CARD_TYPES:
        numbers = {
            float(match.replace(",", "."))
            for match in re.findall(r"\d+(?:[.,]\d+)?", text)
        }
        if not (numbers & own_numbers(card)):
            bad.append("no_card_ref")

    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", lower) if s.strip()]
    for sentence in sentences:
        found = [
            disease
            for disease, keywords in DISW.items()
            if any(keyword in sentence for keyword in keywords)
        ]
        if len(found) != 1:
            continue
        cleaned = re.sub(
            r"kolesterol tinggi|darah tinggi|tekanan darah tinggi|hdl rendah|"
            r"lebih (?:rendah|tinggi)|menjadi (?:rendah|tinggi)",
            " ",
            sentence,
        )
        levels = re.findall(
            r"(?:risiko|tingkat)\b[^.!?\n]{0,40}?\b(rendah|sedang|tinggi)\b",
            cleaned,
        )
        if any(level != card["risiko"][found[0]]["tingkat"] for level in levels):
            bad.append(f"level:{found[0]}")
            break

    if not (
        re.search(r"bukan (?:sebuah )?diagnosis", lower)
        and re.search(r"dokter|tenaga kesehatan|fasilitas kesehatan|igd", lower)
    ):
        bad.append("no_disclaimer")

    if re.search(DRUGS, lower) or re.search(
        r"\d\s?(?:mg|mcg|ml|iu|unit)\b(?!\s?/\s?dl)", lower
    ):
        bad.append("drug_or_dose")

    if question_type in REFUSAL_TYPES and not re.search(
        REFUSE + (r"|hanya perkiraan|bukan diagnosis" if question_type == "diagnosis" else ""),
        lower,
    ):
        bad.append("no_refusal")

    if re.search(r"^\s*(?:[-*\u2022#]|\d+\.)\s", text, re.M):
        bad.append("markdown")
    if lower.count("bukan diagnosis") > 1:
        bad.append("duplicate_disclaimer")

    if question_type == "darurat" and not (
        re.search(r"segera", lower) and re.search(r"igd|gawat darurat|darurat", lower)
    ):
        bad.append("no_emergency")
    if is_red_flag(card) and "segera" not in lower:
        bad.append("no_redflag")

    return bad


def fallback_answer(card: dict) -> str:
    """Safe deterministic answer when the LLM fails the guard."""
    return f"{card_text(card)}\n\n{card.get('disclaimer', '')}".strip()