# Health risk chatbot for Raspberry Pi (capstone)

A user types a few health values. A classifier estimates the risk of three conditions, a rule engine turns the numbers into a "result card", and a small on-device LLM explains the card in Indonesian.

```
Dashboard (form + card + chat) -> FastAPI on the Pi -> 3 CatBoost ONNX models
                                                -> rule engine -> result card
                                                -> llama.cpp student -> guarded answer
```

The LLM never computes or invents numbers. It only reads the card.

**Status:** classifier, rule engine, KD student, dashboard, and Pi API are implemented. The student is published at
[`naiiaiai/chatbot-kesehatan-qwen2.5-0.5b`](https://huggingface.co/naiiaiai/chatbot-kesehatan-qwen2.5-0.5b) (Qwen2.5-0.5B, Q4_K_M GGUF).
Raspberry Pi latency/thermal measurements and a clinician review are still pending.

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
- The student model passed the rule-based validator on 98.7% of 150 held-out validation patients (model card), but those answers were not reviewed by clinicians. The runtime guard checks format and safety rules, not medical correctness.
- The current student was trained on single-turn conversations. Multi-turn mode is off by default and should only be enabled after an A/B test.
- Pi 4 inference speed is measured during deployment; the risk models are small, but the LLM is the latency bottleneck.

---

## 2. Dashboard and Raspberry Pi API

The dashboard in `dashboard/` is a static web app (HTML/CSS/JS, no framework). In production it is served by FastAPI at `http://<pi>:8000/`, so the UI and API share an origin and no CORS is needed.

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /v1/health` | no | Risk-model status, chat availability, versions |
| `GET /v1/meta` | bearer | Form schema, labels, chat capabilities, disclaimer |
| `POST /v1/assessments` | bearer | 12 values -> probabilities + result card |
| `GET /v1/assessments/{id}` | bearer | Retrieve a stored assessment |
| `POST /v1/assessments/{id}/chat` | bearer | Ask about that assessment |

The backend is in `app/`:

- `risk.py` runs the three ONNX sessions in the trained feature order.
- `card.py` is a direct port of the notebook rule engine (validated against all 10 sample cards).
- `prompt.py` contains the exact training-time prompt/card text.
- `guard.py` rejects answers with invented numbers, wrong levels, drugs, missing disclaimers, or unsafe red-flag handling.
- `store.py` keeps assessments and chat sessions in memory; nothing health-related is written to disk.

The deployed student is the Q4_K_M GGUF from the Hugging Face repo. It is **single-turn** in the current deployment (`CHAT_MULTI_TURN=0`), matching the KD data. Use greedy decoding (`CHAT_TEMPERATURE=0`, `CHAT_TOP_P=1`) as in the model card. Set multi-turn only after testing the fine-tuned model; the dashboard already adapts via `/v1/meta`.

The GGUF is not committed (about 380 MiB). Fetch it with:

```powershell
.\scripts\fetch_chat_model.ps1
```

The script verifies the SHA-256:

```text
4117c4248a581dafcf020fd1c1b5fb84826e92236a6c12c37db2a665e0448490
```

---

## 3. Project files

| Path | What it is |
|---|---|
| `app/` | FastAPI backend: ONNX registry, card builder, prompt, guard, chat client, stores |
| `dashboard/` | Static dashboard source, built `dist/`, contract tests, local dev server |
| `deploy/` | systemd services, environment example, Pi deployment notes |
| `scripts/` | Fetch/verify the GGUF, build the dashboard, run dev/tests |
| `tests/` | Card parity, prompt/guard, store/API tests (unittest) |
| `capstone_classifier.ipynb` | Cleaning, split, ablations, models, evaluation, calibration, ONNX export, rule engine, card export |
| `capstone_kd.ipynb` | Knowledge distillation on Colab: a teacher LLM writes answers for cards + questions, an automatic validator filters them, SFT files are built |
| `models/*.onnx` | The three classifiers |
| `models/chat/` | Deployment location for the student GGUF (file not committed) |
| `data/final/` | `train/val/test.csv` (12 features + 3 labels), `risk_levels.json`, `cards_sample.json`, `meta.json` |
| `data/final/kd/cards_train.json` | Cards for all 5,197 train patients (input of the KD notebook) |
| `classifier_results.csv`, `classifier_baselines.csv` | Test metrics and trivial baselines |
| `reports/`, `research_notes/` | Dataset research notes |

## 4. How to run

1. **Classifier** (local): download the NHANES `.xpt` files listed in the notebook into `data/nhanes_raw_2017_2020/` and `data/nhanes_extra/`, then run `capstone_classifier.ipynb` top to bottom (about 2 minutes). It writes `models/`, `data/final/` and the card export.
2. **KD data** (Google Colab, T4 GPU): upload `data/final/kd/cards_train.json` to `MyDrive/capstone_kd/`, open `capstone_kd.ipynb`, and run all. It saves progress to Drive after every batch of 64 items and resumes from there if the session stops.
3. **Pi API + dashboard** (local development): install `requirements.txt`, copy the student GGUF into `models/chat/`, then run:
   ```powershell
   .\scripts\dev.ps1
   ```
   Open `http://127.0.0.1:8000/` for the dashboard served by FastAPI. For dashboard HMR, run `cd dashboard; npm.cmd start` and open `http://127.0.0.1:4173/`; the API allows that origin in development.
4. **Raspberry Pi deployment**: follow `deploy/README.md`. It covers the WiFi/static-IP setup, `llama-server`, systemd units, UFW, and the offline demo checklist.

Run the test suite with:

```powershell
.\scripts\test.ps1
```

The API tests use mocked ONNX/chat backends so they run without a GPU; the ONNX parity test runs when `onnxruntime` is installed. Card parity is checked against `data/final/cards_sample.json` and the raw train rows.
