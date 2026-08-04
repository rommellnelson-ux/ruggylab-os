"""Malaria cell image classifier — MobileNetV2 via ONNX Runtime.

Architecture
------------
Inference uses `onnxruntime-cpu` to run a MobileNetV2 model exported to
ONNX format.  The model expects:
    - Input  : float32 tensor, shape (1, 3, 224, 224), CHW layout
    - Values : normalised with ImageNet statistics
                mean = [0.485, 0.456, 0.406]
                std  = [0.229, 0.224, 0.225]
    - Output : float32 logits, shape (1, 2)  — [negative, positive]

Model provisioning
------------------
Place a compatible ONNX file at ``settings.MALARIA_MODEL_PATH`` before
starting the server.  A ready-made export script is available at:

    scripts/build_malaria_model.py

That script fine-tunes a pre-trained MobileNetV2 from torchvision on the
NIH/Kaggle cell-image dataset and exports the result to ONNX.  Run it once
on a machine with GPU/CPU:

    pip install torch torchvision pillow tqdm
    python scripts/build_malaria_model.py \\
        --data-dir data/malaria_cells \\
        --output-path models/malaria_mobilenetv2/model.onnx

Fail-closed behaviour
---------------------
If ``onnxruntime`` is not installed, the model file is absent or inference
fails, no prediction is produced. A prediction from a real model remains a
non-clinical aid stored on the analysis job and never mutates ``Result``.

Clinical disclaimer
-------------------
⚠️  THIS SOFTWARE IS FOR RESEARCH / DEMONSTRATION PURPOSES ONLY.
Even with a fine-tuned model, results MUST be confirmed by a qualified
medical professional before any clinical decision is taken.  The software
authors accept no liability for clinical outcomes.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import MalariaAnalysisJob, Result, User
from app.services.audit import log_audit_event
from app.utils.datetime_utils import utcnow_naive

logger = logging.getLogger(__name__)

MODEL_NAME = "malaria-mobilenetv2-onnx"

# ImageNet normalisation constants (standard for MobileNetV2 pre-training)
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_INPUT_SIZE = 224

# Label index → class name
_LABELS = ["negative", "positive"]


@dataclass(frozen=True)
class MalariaPrediction:
    label: str
    confidence: float


class ClinicalModelUnavailableError(RuntimeError):
    """Le modèle clinique qualifié n'est pas disponible ou exploitable."""


def _softmax(x: np.ndarray) -> np.ndarray:
    e: np.ndarray = np.exp(x - x.max())
    result: np.ndarray = e / e.sum()
    return result


def _preprocess_image(image_path: str) -> np.ndarray:
    """Load an image file and return a (1, 3, 224, 224) float32 tensor.

    Applies:
    1. Resize to 224×224 using BILINEAR resampling
    2. RGB normalisation with ImageNet statistics
    3. HWC → CHW → add batch dimension

    Args:
        image_path: Absolute or relative path to the image file (JPEG, PNG,
                    BMP, TIFF, …).

    Returns:
        NumPy array ready for ONNX Runtime inference.
    """
    from PIL import Image  # imported lazily so Pillow remains optional

    img = Image.open(image_path).convert("RGB")
    img = img.resize((_INPUT_SIZE, _INPUT_SIZE), Image.Resampling.BILINEAR)
    arr = np.array(img, dtype=np.float32) / 255.0
    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
    arr = arr.transpose(2, 0, 1)  # HWC → CHW
    return arr[np.newaxis]  # → (1, 3, 224, 224)


class MobileNetV2Classifier:
    """ONNX Runtime inference wrapper for a fine-tuned MobileNetV2 model.

    When the model file or ``onnxruntime`` package is unavailable, prediction
    fails closed. No heuristic is exposed through the public API.
    """

    def __init__(self, model_path: str) -> None:
        self.model_path = model_path
        self.model_name = MODEL_NAME
        self._session: Any = None  # ort.InferenceSession when loaded, else None
        self._input_name: str = "input"
        self._load_model()

    def _load_model(self) -> None:
        """Attempt to load the ONNX model into an ONNX Runtime session."""
        if not os.path.isfile(self.model_path):
            logger.warning(
                "Malaria ONNX model not found at '%s'. Clinical inference remains disabled.",
                self.model_path,
            )
            return

        try:
            import onnxruntime as ort  # noqa: PLC0415

            opts = ort.SessionOptions()
            opts.log_severity_level = 3  # suppress verbose ONNX Runtime logs
            self._session = ort.InferenceSession(
                self.model_path,
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            # Cache the first input name (must be "input" by convention)
            self._input_name = self._session.get_inputs()[0].name
            logger.info(
                "MobileNetV2 malaria model loaded from '%s' (input='%s')",
                self.model_path,
                self._input_name,
            )
        except ImportError:
            logger.warning(
                "onnxruntime not installed; clinical inference remains disabled.",
            )
        except Exception as exc:
            logger.warning(
                "Failed to load malaria ONNX model (%s); clinical inference remains disabled.",
                type(exc).__name__,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, image_url: str) -> MalariaPrediction:
        """Classify a cell image as positive or negative for malaria.

        Args:
            image_url: Local filesystem path to the cell image.

        Returns:
            ``MalariaPrediction`` with ``label`` ("positive"/"negative") and
            ``confidence`` in [0, 1].
        """
        if self._session is None or not os.path.isfile(image_url):
            raise ClinicalModelUnavailableError("Qualified malaria model unavailable.")
        try:
            return self._onnx_predict(image_url)
        except Exception as exc:
            logger.warning("ONNX inference failed closed (%s).", type(exc).__name__)
            raise ClinicalModelUnavailableError("Qualified malaria inference failed.") from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _onnx_predict(self, image_path: str) -> MalariaPrediction:
        """Run real MobileNetV2 inference via ONNX Runtime."""
        arr = _preprocess_image(image_path)
        outputs = self._session.run(None, {self._input_name: arr})
        logits: np.ndarray = outputs[0][0]  # shape (2,)
        probs = _softmax(logits)
        idx = int(np.argmax(probs))
        return MalariaPrediction(
            label=_LABELS[idx],
            confidence=round(float(probs[idx]), 4),
        )

    @property
    def is_real_model(self) -> bool:
        """Return True when ONNX inference is active (not the heuristic stub)."""
        return self._session is not None


# Module-level singleton
classifier = MobileNetV2Classifier(settings.MALARIA_MODEL_PATH)


# ---------------------------------------------------------------------------
# Job orchestration (unchanged public API)
# ---------------------------------------------------------------------------


def enqueue_malaria_analysis(
    db: Session,
    *,
    result: Result,
    user: User,
) -> MalariaAnalysisJob:
    job = MalariaAnalysisJob(
        result_id=result.id,
        requested_by_user_id=user.id,
        status="queued",
        model_name=classifier.model_name,
        image_url=result.image_url or "",
    )
    db.add(job)
    db.flush()
    log_audit_event(
        db,
        user=user,
        event_type="malaria.analysis.enqueue",
        entity_type="malaria_analysis_job",
        entity_id=str(job.id),
        payload={"result_id": result.id},
    )
    db.commit()
    db.refresh(job)
    return job


def process_malaria_job(db: Session, *, job_id: int) -> MalariaAnalysisJob | None:
    job = (
        db.query(MalariaAnalysisJob)
        .filter(MalariaAnalysisJob.id == job_id)
        .with_for_update()
        .first()
    )
    if not job:
        return None
    if job.status == "completed":
        return job

    job.status = "processing"
    job.started_at = utcnow_naive()
    db.flush()

    try:
        prediction = classifier.predict(job.image_url)
        job.prediction_label = prediction.label
        job.confidence = prediction.confidence
        job.status = "completed"
        job.completed_at = utcnow_naive()
        job.error_message = None
        log_audit_event(
            db,
            user=job.requested_by,
            event_type="malaria.analysis.complete",
            entity_type="malaria_analysis_job",
            entity_id=str(job.id),
            payload={
                "result_id": job.result_id,
                "prediction_label": prediction.label,
                "confidence": prediction.confidence,
                "clinical_use": False,
                "result_mutated": False,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive inference boundary
        job.status = "failed"
        job.error_message = type(exc).__name__
        job.completed_at = utcnow_naive()
        log_audit_event(
            db,
            user=job.requested_by,
            event_type="malaria.analysis.fail",
            entity_type="malaria_analysis_job",
            entity_id=str(job.id),
            payload={"result_id": job.result_id, "error_type": type(exc).__name__},
        )

    db.commit()
    db.refresh(job)
    return job


def process_malaria_job_background(job_id: int) -> None:
    db = SessionLocal()
    try:
        process_malaria_job(db, job_id=job_id)
    finally:
        db.close()
