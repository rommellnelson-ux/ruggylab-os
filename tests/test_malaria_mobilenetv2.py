"""Tests for the MobileNetV2 / ONNX malaria classifier.

When no real ONNX model file exists the classifier fails closed, so no
synthetic prediction can enter a clinical workflow.

Tests cover:
- Fail-closed behaviour when model file is absent
- Label consistency (only "positive" or "negative")
- Confidence is in (0, 1]
- ONNX inference path (with a minimal 2-class ONNX model generated at test time)
- is_real_model property
- Preprocessing pipeline (resize, normalise, shape)
"""

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_classifier(tmp_path):
    """Classifier with a non-existent model path → heuristic mode."""
    from app.services.malaria_ai import MobileNetV2Classifier

    return MobileNetV2Classifier(str(tmp_path / "nonexistent.onnx"))


@pytest.fixture
def onnx_model_path(tmp_path):
    """Generate a minimal 2-class ONNX model (linear layer only) for testing.

    Skipped automatically when the ``onnx`` package is not installed.
    """
    onnx = pytest.importorskip("onnx", reason="onnx package not installed")
    import onnx.helper as h
    import onnx.TensorProto as tp

    # Model: input (1,3,224,224) → GlobalAvgPool → Flatten → Linear(2) → output
    # We build the simplest valid ONNX graph that matches the inference code's
    # expectations: input name = "input", output shape = (N, 2).

    X = h.make_tensor_value_info("input", tp.FLOAT, [1, 3, 224, 224])
    Y = h.make_tensor_value_info("output", tp.FLOAT, [1, 2])

    # Global average pool: (1,3,224,224) → (1,3,1,1)
    gap_node = h.make_node("GlobalAveragePool", inputs=["input"], outputs=["pooled"])

    # Flatten: (1,3,1,1) → (1,3)
    flatten_node = h.make_node("Flatten", inputs=["pooled"], outputs=["flat"], axis=1)

    # Initialiser: weight matrix (2,3) and bias (2,)
    W_data = np.zeros((2, 3), dtype=np.float32)
    W_data[1, :] = 0.1  # slight bias toward "positive" class
    b_data = np.array([0.0, 0.1], dtype=np.float32)

    W_init = h.make_tensor("W", tp.FLOAT, [2, 3], W_data.flatten().tolist())
    b_init = h.make_tensor("b", tp.FLOAT, [2], b_data.tolist())

    gemm_node = h.make_node("Gemm", inputs=["flat", "W", "b"], outputs=["output"], transB=1)

    graph = h.make_graph(
        [gap_node, flatten_node, gemm_node],
        "malaria-test",
        [X],
        [Y],
        initializer=[W_init, b_init],
    )
    model = h.make_model(graph, opset_imports=[h.make_opsetid("", 17)])
    model.ir_version = 8

    path = str(tmp_path / "model.onnx")
    onnx.save(model, path)
    return path


@pytest.fixture
def real_classifier(onnx_model_path):
    """Classifier loaded with the minimal test ONNX model."""
    from app.services.malaria_ai import MobileNetV2Classifier

    clf = MobileNetV2Classifier(onnx_model_path)
    assert clf.is_real_model, "ONNX session should have loaded"
    return clf


# ---------------------------------------------------------------------------
# Fail-closed tests
# ---------------------------------------------------------------------------


def test_stub_rejects_positive_keyword(stub_classifier):
    from app.services.malaria_ai import ClinicalModelUnavailableError

    with pytest.raises(ClinicalModelUnavailableError):
        stub_classifier.predict("microscopy/positive_cell.jpg")


def test_stub_rejects_negative_keyword(stub_classifier):
    from app.services.malaria_ai import ClinicalModelUnavailableError

    with pytest.raises(ClinicalModelUnavailableError):
        stub_classifier.predict("microscopy/negative_cell.jpg")


def test_stub_rejects_arbitrary_identifiers(stub_classifier):
    from app.services.malaria_ai import ClinicalModelUnavailableError

    for url in ["a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg"]:
        with pytest.raises(ClinicalModelUnavailableError):
            stub_classifier.predict(url)


def test_stub_is_not_real_model(stub_classifier):
    assert stub_classifier.is_real_model is False


# ---------------------------------------------------------------------------
# ONNX inference tests
# ---------------------------------------------------------------------------


def test_onnx_classifier_is_real_model(real_classifier):
    assert real_classifier.is_real_model is True


def test_onnx_predict_from_image_file(real_classifier, tmp_path):
    """Generate a small random image, save it, and run real ONNX inference."""
    from PIL import Image

    # 50×50 random-colour image
    arr = np.random.randint(0, 256, (50, 50, 3), dtype=np.uint8)
    img_path = str(tmp_path / "cell.jpg")
    Image.fromarray(arr).save(img_path)

    pred = real_classifier.predict(img_path)
    assert pred.label in ("positive", "negative")
    assert 0.0 < pred.confidence <= 1.0


def test_onnx_confidence_sums_to_one(real_classifier, tmp_path):
    """Softmax probabilities from a 2-class model must sum to ~1.0."""
    from PIL import Image

    from app.services.malaria_ai import _preprocess_image, _softmax

    arr = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)
    img_path = str(tmp_path / "cell2.jpg")
    Image.fromarray(arr).save(img_path)

    tensor = _preprocess_image(img_path)
    outputs = real_classifier._session.run(None, {"input": tensor})
    probs = _softmax(outputs[0][0])
    assert pytest.approx(probs.sum(), abs=1e-5) == 1.0


# ---------------------------------------------------------------------------
# Preprocessing pipeline tests
# ---------------------------------------------------------------------------


def test_preprocess_output_shape(tmp_path):
    """_preprocess_image must return (1, 3, 224, 224)."""
    from PIL import Image

    from app.services.malaria_ai import _preprocess_image

    arr = np.random.randint(0, 256, (300, 250, 3), dtype=np.uint8)
    img_path = str(tmp_path / "cell3.jpg")
    Image.fromarray(arr).save(img_path)

    tensor = _preprocess_image(img_path)
    assert tensor.shape == (1, 3, 224, 224)
    assert tensor.dtype == np.float32


def test_preprocess_normalisation(tmp_path):
    """Pixel values after normalisation must span a reasonable range."""
    from PIL import Image

    from app.services.malaria_ai import _preprocess_image

    # All-white image (255, 255, 255)
    arr = np.full((224, 224, 3), 255, dtype=np.uint8)
    img_path = str(tmp_path / "white.jpg")
    Image.fromarray(arr).save(img_path)

    tensor = _preprocess_image(img_path)
    # After normalisation a white pixel should be (1.0 - mean) / std
    # channel 0: (1.0 - 0.485) / 0.229 ≈ 2.25
    assert tensor[0, 0, 0, 0] == pytest.approx(2.2489, abs=0.05)
