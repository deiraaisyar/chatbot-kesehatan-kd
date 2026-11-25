"""ONNX risk-model registry and the v1 prediction contract."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Mapping

import numpy as np

from .contract import DISEASES, FEATURES

logger = logging.getLogger(__name__)

WARMUP_VALUES = {
    "age": 50,
    "male": 1,
    "bmi": 25.0,
    "sbp": 120,
    "dbp": 80,
    "smoker": 0,
    "waist": 90,
    "hdl": 50,
    "fam_dm": 0,
    "fam_mi": 0,
    "vig_rec": 0,
    "mod_rec": 0,
}


class RiskRegistry:
    """Load the three CatBoost ONNX models and run one row at a time.

    The model contract is:
      input  ``features`` float32 [N, 12]
      output ``probabilities`` float32 [N, 2]; class 1 is the positive risk.
    """

    def __init__(
        self,
        model_dir: Path,
        features: list[str],
        version: str = "catboost-2026.11",
    ) -> None:
        self.model_dir = Path(model_dir)
        self.features = list(features)
        self.version = version
        self.sessions: dict[str, object] = {}
        self.status: dict[str, str] = {name: "not_loaded" for name in DISEASES}
        self.error: str | None = None

        if self.features != list(FEATURES):
            # The ONNX files were trained on this exact order. Refuse to guess.
            self.error = f"Unexpected feature order in meta.json: {self.features!r}"
            logger.error(self.error)
            self.status = {name: "misconfigured" for name in DISEASES}
            return

        try:
            import onnxruntime as ort
        except Exception as exc:  # pragma: no cover - depends on the Pi install
            self.error = f"onnxruntime is not available: {exc}"
            logger.error(self.error)
            self.status = {name: "not_installed" for name in DISEASES}
            return

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1

        for name in DISEASES:
            path = self.model_dir / f"{name}.onnx"
            if not path.exists():
                self.status[name] = "missing"
                self.error = f"Missing model: {path}"
                logger.error(self.error)
                continue
            try:
                session = ort.InferenceSession(
                    str(path),
                    sess_options=options,
                    providers=["CPUExecutionProvider"],
                )
                self.sessions[name] = session
                self.status[name] = "ok"
                logger.info(
                    "loaded %s (%s) input=%s outputs=%s",
                    path.name,
                    path.stat().st_size,
                    session.get_inputs()[0].name,
                    [output.name for output in session.get_outputs()],
                )
            except Exception as exc:  # pragma: no cover - model-specific
                self.status[name] = "error"
                self.error = f"Failed to load {path.name}: {exc}"
                logger.exception(self.error)

    def ready(self) -> bool:
        return all(self.status.get(name) == "ok" for name in DISEASES)

    def health(self) -> dict[str, str]:
        return {name: self.status.get(name, "not_loaded") for name in DISEASES}

    def warmup(self) -> None:
        if not self.ready():
            return
        self.predict(WARMUP_VALUES)

    def _vector(self, values: Mapping[str, object]) -> np.ndarray:
        row = []
        for feature in self.features:
            value = values.get(feature)
            row.append(np.nan if value is None else float(value))
        return np.asarray([row], dtype=np.float32)

    def predict(self, values: Mapping[str, object]) -> dict[str, float]:
        if not self.ready():
            raise RuntimeError(self.error or "Risk models are not ready.")
        row = self._vector(values)
        result: dict[str, float] = {}
        for name in DISEASES:
            session = self.sessions[name]
            input_name = session.get_inputs()[0].name
            outputs = session.run(None, {input_name: row})
            output_meta = session.get_outputs()
            probability_index = next(
                (index for index, output in enumerate(output_meta) if output.name == "probabilities"),
                None,
            )
            if probability_index is None:
                probability_index = 1 if len(outputs) > 1 else 0
            raw = outputs[probability_index]
            # CatBoost exports ``probabilities`` as
            # seq(map(int64, tensor(float))): a list of {0: p0, 1: p1} dicts.
            # Older/simple ONNX exports use a float array instead.
            if isinstance(raw, (list, tuple)):
                first = raw[0]
                if isinstance(first, dict):
                    result[name] = float(first[1] if 1 in first else list(first.values())[-1])
                else:
                    flat = np.asarray(first).reshape(-1)
                    result[name] = float(flat[1] if flat.size > 1 else flat[0])
            elif isinstance(raw, dict):
                result[name] = float(raw[1] if 1 in raw else list(raw.values())[-1])
            else:
                flat = np.asarray(raw).reshape(-1)
                result[name] = float(flat[1] if flat.size > 1 else flat[0])
        return result