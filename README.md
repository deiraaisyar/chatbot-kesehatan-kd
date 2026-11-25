# Health risk chatbot for Raspberry Pi (capstone)

A user types a few health values. A classifier estimates the risk of three conditions, a rule engine turns the numbers into a "result card", and a small on-device LLM explains the card in Indonesian.

```
12 typed values -> 3 CatBoost classifiers -> rule engine -> result card -> small LLM -> answer
                   (ONNX, risk %)           (categories,     (JSON)         (explains, answers
                                             levels, flags)                  follow-ups, refuses
                                                                             unsafe questions)
```

The LLM never computes or invents numbers. It only reads the card.

**Status:** classifier and rule engine done. Knowledge-distillation data (teacher LLM) is being generated. LoRA fine-tuning of the student and Raspberry Pi measurements are not done yet; this README will be extended when they are.

---

## 1. Classifier

### Input (12 features, all typable by the user)

| Feature | Meaning | Type / unit | May be left empty |
|---|---|---|---|
| `age` | Age | years (valid range 18-120) | no |
| `male` | Sex | 1 = male, 0 = female | no |
| `bmi` | Body mass index | kg/m² (10-80) | no |
| `sbp` | Systolic blood pressure | mmHg (70-260) | no |
| `dbp` | Diastolic blood pressure | mmHg (40-150) | no |
| `smoker` | Ever smoked 100+ cigarettes | 1 / 0 | yes |
| `waist` | Waist circumference | cm (40-200) | yes |
| `hdl` | HDL cholesterol | mg/dL (10-200) | no |
| `fam_dm` | Close relative with diabetes | 1 / 0 | yes |
| `fam_mi` | Close relative with heart attack | 1 / 0 | yes |
| `vig_rec` | Vigorous recreational activity | 1 / 0 | yes |
| `mod_rec` | Moderate recreational activity | 1 / 0 | yes |

Empty values are passed as missing (NaN); CatBoost handles them natively. Which fields were empty is listed in the card (`data_tidak_lengkap`).

### Output (3 independent probabilities)

Multi-label by binary relevance: one CatBoost model per target. The outputs are not mutually exclusive and do not sum to 1.

| Model file | Target | Label definition (NHANES) |
|---|---|---|
| `models/hipertensi.onnx` | Hypertension | told by a doctor that blood pressure is high (`BPQ020`) |
| `models/diabetes.onnx` | Diabetes | told by a doctor (`DIQ010`) **or** HbA1c >= 6.5 **or** fasting glucose >= 126 |
| `models/kolesterol_tinggi.onnx` | High cholesterol | told by a doctor that cholesterol is high (`BPQ080`) |

Each model returns P(positive) in [0, 1]. Each model is about 0.7 MB and runs with `onnxruntime` on the Pi.

### What the app shows: the result card

The rule engine (deterministic, in `capstone_classifier.ipynb`, section 9) converts the probabilities and inputs into a card:

- **Risk per disease:** probability, rounded percentage (nearest 5%, `<5%`, `>95%`) and level `rendah` / `sedang` / `tinggi`. Level cut-offs are relative to each disease's prevalence in train (low < 0.5x prevalence, high >= 1.5x), see `data/final/risk_levels.json`.
- **Categories:** blood pressure (normal / elevated / stage 1 / stage 2), BMI (Asia-Pacific), waist (central obesity), HDL (low / adequate).
- **Warnings:** value out of plausible range, systolic not above diastolic, very high blood pressure (>= 180 or >= 120) with advice to go to a health facility immediately.
- **Missing data list** and a fixed **disclaimer** (statistical estimate, not a diagnosis, consult a doctor).

Example (`data/final/cards_sample.json` has more):

```json
{"pasien": {"umur": 35, "jenis_kelamin": "laki-laki", "bmi": 25.2, "td_sistolik": 120, "td_diastolik": 68, "...": "..."},
 "kategori": {"tekanan_darah": "normal", "bmi": "obesitas I", "lingkar_pinggang": "normal", "hdl": "cukup"},
 "risiko": {"hipertensi": {"probabilitas": 0.062, "persen_perkiraan": "5%", "tingkat": "rendah"},
            "diabetes": {"probabilitas": 0.009, "persen_perkiraan": "<5%", "tingkat": "rendah"},
            "kolesterol_tinggi": {"probabilitas": 0.143, "persen_perkiraan": "15%", "tingkat": "rendah"}},
 "data_tidak_lengkap": [], "peringatan": [], "disclaimer": "..."}
```

### Data

- **Source:** NHANES (CDC), cycle 2017 to March 2020 only, because the family-history and activity questions exist only in this cycle and the oscillometric BP device is consistent in it. Public domain US government data.
- **Population:** US adults (>= 18). Complete cases on the required fields: 7,425 participants, split 70/15/15 stratified on the label combination: train 5,197, validation 1,114, test 1,114.
- **Blood pressure** = mean of up to 3 oscillometric readings.

### Results (held-out test set, CatBoost)

| Target | ROC-AUC (95% CI) | PR-AUC | Brier | Prevalence |
|---|---|---|---|---|
| Hypertension | 0.837 (0.813-0.858) | 0.729 | 0.160 | 0.381 |
| Diabetes | 0.831 (0.804-0.855) | 0.536 | 0.123 | 0.199 |
| High cholesterol | 0.754 (0.726-0.783) | 0.582 | 0.189 | 0.350 |

Threshold metrics at the threshold chosen on validation (max F1): hypertension F1 0.714 (recall 0.85), diabetes F1 0.548 (recall 0.74), high cholesterol F1 0.613 (recall 0.81). Full table (also at 0.5) in `classifier_results.csv`; chance and majority-class baselines in `classifier_baselines.csv`.

Why no higher: the labels are partly self-reported and the inputs are only 12 typable values, with no lab tests. This is intentional, see leakage below.

### Leakage and honesty checks (section 4 of the notebook)

- Variables that define a label (HbA1c, fasting glucose for diabetes; total cholesterol for high cholesterol) are **not** inputs. The notebook shows how much AUC they would inflate.
- The test set is untouched during ablations and model selection (5-fold CV on train only); no resampling before the split.
- Compared against logistic regression, random forest, XGBoost, LightGBM; CatBoost is the final model.
- Calibration is reported (ECE, slope/intercept, Brier skill); out-of-fold probabilities on train are used as soft labels for the LLM data step.
- ONNX output matches CatBoost (parity check in section 8).

### Limitations

- US population; no Indonesian data. The disclaimer says so.
- Blood-pressure categories follow AHA/ACC (130/80), which is stricter than the Indonesian PERHI 140/90 cut-off. The very-high BP red flag (>= 180/120) is a conservative threshold that we have not verified against a primary source.
- BMI and waist cut-offs follow Kemenkes decree HK.01.07/MENKES/509/2025.
- This is a statistical risk estimate, not a diagnosis.

---

## 2. Project files

| Path | What it is |
|---|---|
| `capstone_classifier.ipynb` | Cleaning, split, ablations, models, evaluation, calibration, ONNX export, rule engine, card export |
| `capstone_kd.ipynb` | Knowledge distillation on Colab: a teacher LLM writes answers for cards + questions, an automatic validator filters them, SFT files are built |
| `models/*.onnx` | The three classifiers |
| `data/final/` | `train/val/test.csv` (12 features + 3 labels), `risk_levels.json`, `cards_sample.json`, `meta.json` |
| `data/final/kd/cards_train.json` | Cards for all 5,197 train patients (input of the KD notebook) |
| `classifier_results.csv`, `classifier_baselines.csv` | Test metrics and trivial baselines |
| `reports/`, `research_notes/` | Dataset research notes |

## 3. How to run

1. **Classifier** (local): download the NHANES `.xpt` files listed in the notebook into `data/nhanes_raw_2017_2020/` and `data/nhanes_extra/`, then run `capstone_classifier.ipynb` top to bottom (about 2 minutes). It writes `models/`, `data/final/` and the card export.
2. **KD data** (Google Colab, T4 GPU): upload `data/final/kd/cards_train.json` to `MyDrive/capstone_kd/`, open `capstone_kd.ipynb`, and run all. It saves progress to Drive after every batch of 64 items and resumes from there if the session stops.
