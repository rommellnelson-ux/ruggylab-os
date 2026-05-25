"""ONNX model validator for the malaria MobileNetV2 classifier.

Ensures that an exported ONNX model is compatible with the inference
interface defined in ``app/services/malaria_ai.py``:
  - input  : float32 tensor, shape (1, 3, 224, 224), ImageNet-normalised
  - output : float32 logits, shape (1, 2) — [negative, positive]
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Expected I/O contract (mirrors app/services/malaria_ai.py)
_EXPECTED_INPUT_SHAPE = (1, 3, 224, 224)
_EXPECTED_OUTPUT_CLASSES = 2


def validate_onnx_model(
    onnx_path: Path,
    sample_image: np.ndarray | None = None,
) -> dict[str, object]:
    """Load an ONNX model and verify it is compatible with the app inference path.

    Parameters
    ----------
    onnx_path:
        Path to the ``.onnx`` file to validate.
    sample_image:
        Optional float32 NumPy array of shape ``(1, 3, 224, 224)``.
        When *None* a random tensor (ImageNet-scale values) is used.

    Returns
    -------
    dict with keys:
        - ``valid`` (bool)         — True when all checks pass
        - ``output_shape`` (tuple) — shape of the model's first output
        - ``inference_time_ms`` (float) — wall-clock time for one forward pass
        - ``error`` (str | None)   — description of the first failure, or None
        - ``checks`` (dict)        — individual check results

    Raises
    ------
    ImportError
        When ``onnxruntime`` is not installed.
    FileNotFoundError
        When *onnx_path* does not exist.
    """
    import onnxruntime as ort  # hard dependency for this validator

    onnx_path = Path(onnx_path)
    if not onnx_path.is_file():
        raise FileNotFoundError(f"ONNX model not found: {onnx_path}")

    result: dict[str, object] = {
        "valid": False,
        "output_shape": (),
        "inference_time_ms": 0.0,
        "error": None,
        "checks": {},
    }
    checks: dict[str, bool] = {}

    # ---- Load model ---------------------------------------------------------
    try:
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        session = ort.InferenceSession(
            str(onnx_path),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
    except Exception as exc:
        result["error"] = f"Failed to load ONNX model: {exc}"
        result["checks"] = checks
        logger.error("ONNX load failed: %s", exc)
        return result

    # ---- Inspect inputs -----------------------------------------------------
    inputs = session.get_inputs()
    checks["has_single_input"] = len(inputs) == 1

    input_name: str = inputs[0].name
    checks["input_name_is_input"] = input_name == "input"
    if input_name != "input":
        logger.warning("Input name is '%s', expected 'input'", input_name)

    # Shape may contain None (dynamic axes) — check static dims
    raw_shape = inputs[0].shape  # e.g. [1, 3, 224, 224] or ['batch', 3, 224, 224]
    static_dims = [d for d in raw_shape if isinstance(d, int)]
    checks["input_channels_correct"] = len(static_dims) >= 3 and static_dims[-3] == 3
    checks["input_height_correct"] = len(static_dims) >= 2 and static_dims[-2] == 224
    checks["input_width_correct"] = len(static_dims) >= 1 and static_dims[-1] == 224

    # ---- Inspect outputs ----------------------------------------------------
    outputs = session.get_outputs()
    checks["has_at_least_one_output"] = len(outputs) >= 1

    # ---- Build sample input -------------------------------------------------
    if sample_image is None:
        rng = np.random.default_rng(0)
        sample_image = rng.standard_normal(_EXPECTED_INPUT_SHAPE).astype(np.float32)
    else:
        if sample_image.shape != _EXPECTED_INPUT_SHAPE:
            result["error"] = (
                f"sample_image has shape {sample_image.shape}, expected {_EXPECTED_INPUT_SHAPE}"
            )
            result["checks"] = checks
            return result
        sample_image = sample_image.astype(np.float32)

    # ---- Run inference ------------------------------------------------------
    try:
        t0 = time.perf_counter()
        raw_outputs = session.run(None, {input_name: sample_image})
        t1 = time.perf_counter()
        inference_ms = (t1 - t0) * 1000.0
    except Exception as exc:
        result["error"] = f"Inference failed: {exc}"
        result["checks"] = checks
        logger.error("ONNX inference failed: %s", exc)
        return result

    output_tensor: np.ndarray = raw_outputs[0]
    output_shape = tuple(output_tensor.shape)
    result["output_shape"] = output_shape
    result["inference_time_ms"] = round(inference_ms, 3)

    # ---- Validate output shape ----------------------------------------------
    checks["output_is_2d"] = output_tensor.ndim == 2
    checks["output_has_2_classes"] = (
        output_tensor.ndim >= 2 and output_tensor.shape[-1] == _EXPECTED_OUTPUT_CLASSES
    )

    # ---- Validate softmax is plausible (logits should be finite) ------------
    checks["output_is_finite"] = bool(np.all(np.isfinite(output_tensor)))

    # Softmax sanity check: probabilities must sum to ~1
    exp_out = np.exp(output_tensor - output_tensor.max(axis=-1, keepdims=True))
    probs = exp_out / exp_out.sum(axis=-1, keepdims=True)
    prob_sum = float(probs.sum(axis=-1).mean())
    checks["softmax_sums_to_one"] = abs(prob_sum - 1.0) < 1e-4

    # ---- Overall validity ---------------------------------------------------
    all_passed = all(checks.values())
    result["valid"] = all_passed
    result["checks"] = checks
    if not all_passed:
        failed = [k for k, v in checks.items() if not v]
        result["error"] = f"Failed checks: {failed}"
        logger.warning("ONNX validation failed: %s", failed)
    else:
        logger.info(
            "ONNX model validated successfully (inference=%.1f ms, output=%s)",
            inference_ms,
            output_shape,
        )

    return result
