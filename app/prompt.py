"""Student prompt and card rendering.

These strings must match ``capstone_kd.ipynb`` exactly. The fine-tuned model
was trained on this format; changing punctuation or labels silently degrades
its output.
"""

from __future__ import annotations

from .contract import DIS_NAME, DISEASES, MISSING_LABELS

DIS = DISEASES

SYS_STUDENT = (
    "Kamu asisten kesehatan yang hanya menjelaskan kartu hasil pasien. Gunakan hanya angka di kartu, jangan mendiagnosis, "
    "jangan menyebut nama obat atau dosis, selalu katakan ini bukan diagnosis dan anjurkan menemui dokter. Jawab dalam bahasa Indonesia."
)


def pct_text(value: str) -> str:
    return (
        "kurang dari 5%"
        if value == "<5%"
        else "lebih dari 95%"
        if value == ">95%"
        else f"sekitar {value}"
    )


def card_text(card: dict) -> str:
    patient, category = card["pasien"], card["kategori"]
    fmt = lambda value: str(value).replace(".", ",")
    waist = (
        "tidak diketahui"
        if patient["lingkar_pinggang_cm"] is None
        else f"{fmt(patient['lingkar_pinggang_cm'])} cm ({category['lingkar_pinggang']})"
    )
    lines = [
        f"Pasien: {patient['jenis_kelamin']}, {patient['umur']} tahun",
        f"BMI: {fmt(patient['bmi'])} ({category['bmi']})",
        f"Tekanan darah: {patient['td_sistolik']}/{patient['td_diastolik']} mmHg ({category['tekanan_darah']})",
        f"Lingkar pinggang: {waist}",
        f"HDL: {fmt(patient['hdl_mgdl'])} mg/dL ({category['hdl']})",
        f"Pernah merokok: {patient['pernah_merokok']}; riwayat diabetes keluarga: {patient['riwayat_diabetes_keluarga']}; "
        f"riwayat serangan jantung keluarga: {patient['riwayat_serangan_jantung_keluarga']}",
        f"Olahraga rekreasi: berat {patient['olahraga_berat_rekreasi']}, sedang {patient['olahraga_sedang_rekreasi']}",
        "Perkiraan risiko:",
    ]
    lines += [
        f"- {DIS_NAME[disease]}: {pct_text(card['risiko'][disease]['persen_perkiraan'])} "
        f"(tingkat {card['risiko'][disease]['tingkat']})"
        for disease in DIS
    ]
    if card["data_tidak_lengkap"]:
        lines.append(
            "Data tidak diisi: "
            + ", ".join(MISSING_LABELS.get(key, key) for key in card["data_tidak_lengkap"])
        )
    if card["peringatan"]:
        lines.append("Peringatan: " + "; ".join(card["peringatan"]))
    return "\n".join(lines)


def user_msg(card: dict, question: str) -> str:
    return f"KARTU HASIL:\n{card_text(card)}\n\nPERTANYAAN: {question}"