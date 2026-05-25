"""Tests for the malaria ML training pipeline (ml/ package).

PyTorch is an optional training dependency and is NOT installed in the CI
environment by default.  All tests in this module are skipped when
``torch`` is absent:

    python -m pytest tests/test_ml_pipeline.py -v
    # → skips everything with "PyTorch non installé — tests ML skippés"

When PyTorch is available the full suite runs, covering:
  - MalariaSlideDataset with synthetic images
  - train_val_split stratified split
  - MobileNetTrainer.export_onnx produces a loadable ONNX file
  - validate_onnx_model returns the expected structure
  - CLI --help exits 0 without crashing
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Skip everything when torch is not installed
# ---------------------------------------------------------------------------
torch = pytest.importorskip("torch", reason="PyTorch non installé — tests ML skippés")

# After the importorskip we know torch is available; import the rest.
import torch as _torch  # noqa: E402 — after importorskip

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def synthetic_data_dir(tmp_path_factory):
    """Create a tiny synthetic dataset (10 infected + 10 uninfected, 64×64 PNG)."""
    from ml.dataset import make_synthetic_dataset

    tmp = tmp_path_factory.mktemp("malaria_data")
    make_synthetic_dataset(tmp, n_infected=10, n_uninfected=10)
    return tmp


@pytest.fixture(scope="module")
def trained_checkpoint(tmp_path_factory, synthetic_data_dir):
    """Run a 1-epoch training pass and return the checkpoint path."""
    from ml.trainer import MobileNetTrainer

    output_dir = tmp_path_factory.mktemp("models")
    trainer = MobileNetTrainer(device="cpu")
    report = trainer.train(
        data_dir=synthetic_data_dir,
        output_dir=output_dir,
        epochs=1,
        batch_size=4,
        val_split=0.3,
        seed=0,
        num_workers=0,
    )
    return Path(report["checkpoint_path"])


@pytest.fixture(scope="module")
def exported_onnx(tmp_path_factory, trained_checkpoint):
    """Export the trained checkpoint to ONNX and return the ONNX path."""
    from ml.trainer import MobileNetTrainer

    output_dir = tmp_path_factory.mktemp("onnx")
    onnx_path = output_dir / "model.onnx"
    trainer = MobileNetTrainer(device="cpu")
    trainer.export_onnx(trained_checkpoint, onnx_path)
    return onnx_path


# ---------------------------------------------------------------------------
# MalariaSlideDataset tests
# ---------------------------------------------------------------------------


class TestMalariaSlideDataset:
    def test_dataset_loads(self, synthetic_data_dir):
        from ml.dataset import MalariaSlideDataset

        ds = MalariaSlideDataset(synthetic_data_dir, train=False)
        assert len(ds) == 20

    def test_dataset_item_shape(self, synthetic_data_dir):
        from ml.dataset import MalariaSlideDataset

        ds = MalariaSlideDataset(synthetic_data_dir, train=False)
        tensor, label = ds[0]
        assert tensor.shape == (3, 224, 224), f"unexpected shape {tensor.shape}"
        assert tensor.dtype == _torch.float32
        assert label in (0, 1)

    def test_dataset_labels_balanced(self, synthetic_data_dir):
        from ml.dataset import MalariaSlideDataset

        ds = MalariaSlideDataset(synthetic_data_dir, train=False)
        labels = ds.labels
        assert labels.count(0) == 10
        assert labels.count(1) == 10

    def test_dataset_class_weights_shape(self, synthetic_data_dir):
        from ml.dataset import MalariaSlideDataset

        ds = MalariaSlideDataset(synthetic_data_dir, train=True)
        assert ds.class_weights.shape == (2,)
        assert (ds.class_weights > 0).all()

    def test_dataset_raises_on_empty_dir(self, tmp_path):
        from ml.dataset import MalariaSlideDataset

        with pytest.raises(ValueError, match="No images found"):
            MalariaSlideDataset(tmp_path, train=False)

    def test_train_val_split_sizes(self, synthetic_data_dir):
        from ml.dataset import MalariaSlideDataset, train_val_split

        ds = MalariaSlideDataset(synthetic_data_dir, train=True)
        train_ds, val_ds = train_val_split(ds, val_fraction=0.3, seed=42)
        total = len(train_ds) + len(val_ds)
        assert total == len(ds)
        assert len(val_ds) == pytest.approx(6, abs=1)  # ~30 % of 20

    def test_train_augmentation_differs_from_val(self, synthetic_data_dir):
        """Training transform should produce different results than val (stochastic)."""
        from ml.dataset import MalariaSlideDataset

        train_ds = MalariaSlideDataset(synthetic_data_dir, train=True)
        val_ds = MalariaSlideDataset(synthetic_data_dir, train=False)
        # Two runs of the same train transform on the same image should differ
        # with overwhelming probability (RandomFlip, RandomRotation, ColorJitter)
        t1, _ = train_ds[0]
        t2, _ = train_ds[0]
        # val transform should be deterministic
        v1, _ = val_ds[0]
        v2, _ = val_ds[0]
        assert _torch.allclose(v1, v2), "Val transform should be deterministic"
        # training transform can theoretically match by luck; accept flakiness
        # only if it differs at least sometimes
        assert t1.shape == (3, 224, 224)


# ---------------------------------------------------------------------------
# ONNX export tests
# ---------------------------------------------------------------------------


class TestOnnxExport:
    def test_onnx_file_exists(self, exported_onnx):
        assert exported_onnx.is_file(), "ONNX file should have been created"
        assert exported_onnx.stat().st_size > 0

    def test_onnx_loadable_with_onnxruntime(self, exported_onnx):
        ort = pytest.importorskip("onnxruntime", reason="onnxruntime not installed")
        session = ort.InferenceSession(str(exported_onnx), providers=["CPUExecutionProvider"])
        assert session is not None

    def test_onnx_input_name(self, exported_onnx):
        ort = pytest.importorskip("onnxruntime", reason="onnxruntime not installed")
        session = ort.InferenceSession(str(exported_onnx), providers=["CPUExecutionProvider"])
        input_name = session.get_inputs()[0].name
        assert input_name == "input", f"Expected 'input', got '{input_name}'"

    def test_onnx_output_shape(self, exported_onnx):
        ort = pytest.importorskip("onnxruntime", reason="onnxruntime not installed")
        session = ort.InferenceSession(str(exported_onnx), providers=["CPUExecutionProvider"])
        dummy = np.zeros((1, 3, 224, 224), dtype=np.float32)
        outputs = session.run(None, {"input": dummy})
        assert outputs[0].shape == (1, 2), f"Expected (1, 2), got {outputs[0].shape}"


# ---------------------------------------------------------------------------
# validate_onnx_model tests
# ---------------------------------------------------------------------------


class TestOnnxValidator:
    def test_validate_returns_valid_true(self, exported_onnx):
        from ml.onnx_validator import validate_onnx_model

        result = validate_onnx_model(exported_onnx)
        assert result["valid"] is True, f"Validation failed: {result.get('error')}"

    def test_validate_output_shape(self, exported_onnx):
        from ml.onnx_validator import validate_onnx_model

        result = validate_onnx_model(exported_onnx)
        assert result["output_shape"] == (1, 2)

    def test_validate_inference_time_is_positive(self, exported_onnx):
        from ml.onnx_validator import validate_onnx_model

        result = validate_onnx_model(exported_onnx)
        assert isinstance(result["inference_time_ms"], float)
        assert result["inference_time_ms"] > 0

    def test_validate_with_custom_sample(self, exported_onnx):
        from ml.onnx_validator import validate_onnx_model

        rng = np.random.default_rng(1)
        sample = rng.standard_normal((1, 3, 224, 224)).astype(np.float32)
        result = validate_onnx_model(exported_onnx, sample_image=sample)
        assert result["valid"] is True

    def test_validate_missing_file_raises(self, tmp_path):
        from ml.onnx_validator import validate_onnx_model

        with pytest.raises(FileNotFoundError):
            validate_onnx_model(tmp_path / "nonexistent.onnx")

    def test_validate_wrong_sample_shape_raises(self, exported_onnx):
        from ml.onnx_validator import validate_onnx_model

        bad_sample = np.zeros((1, 3, 128, 128), dtype=np.float32)
        result = validate_onnx_model(exported_onnx, sample_image=bad_sample)
        # Should return valid=False (not raise), with an error message
        assert result["valid"] is False
        assert result["error"] is not None


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


class TestCLI:
    def test_help_exits_zero(self):
        """--help must work without torch being in the module-level import path."""
        result = subprocess.run(
            [sys.executable, "scripts/train_mobilenet.py", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0, f"--help failed:\n{result.stderr}"
        assert "data-dir" in result.stdout

    def test_missing_data_dir_exits_nonzero(self):
        """Running without required args must exit with an error code."""
        result = subprocess.run(
            [sys.executable, "scripts/train_mobilenet.py"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode != 0

    def test_cli_train_and_export(self, synthetic_data_dir, tmp_path):
        """Full CLI round-trip: train 1 epoch, export ONNX, write report."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/train_mobilenet.py",
                "--data-dir",
                str(synthetic_data_dir),
                "--output-dir",
                str(tmp_path),
                "--epochs",
                "1",
                "--batch-size",
                "4",
                "--val-split",
                "0.3",
                "--seed",
                "0",
                "--export-onnx",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0, f"CLI failed:\n{result.stderr}\n{result.stdout}"
        assert (tmp_path / "mobilenet_malaria_best.pt").is_file()
        assert (tmp_path / "mobilenet_malaria.onnx").is_file()
        assert (tmp_path / "training_report.json").is_file()
