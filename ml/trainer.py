"""MobileNetV2 fine-tuning trainer for malaria blood-smear classification.

This module is intentionally **not imported** by the application runtime
(``app/``).  It is only used by the training pipeline and tests that
explicitly install PyTorch.

Architecture
------------
  backbone  : MobileNetV2 (torchvision), ImageNet weights
  frozen    : all layers except the last 2 feature blocks + classifier
  head      : Linear(1280, 256) → ReLU → Dropout(0.3) → Linear(256, 2)
  loss      : CrossEntropyLoss with class weights
  optimizer : AdamW(lr=1e-4, weight_decay=1e-5)
  scheduler : CosineAnnealingLR(T_max=epochs)
  early stop: patience=5 on val_loss

ONNX export
-----------
The exported model matches the interface expected by
``app/services/malaria_ai.py``:
  - input  name : "input"
  - input  shape: (1, 3, 224, 224) float32, ImageNet-normalised
  - output name : "output"
  - output shape: (N, 2) float32 logits [negative, positive]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader
    from torchvision import models

    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------


def _build_mobilenetv2(num_classes: int = 2) -> nn.Module:
    """Return a MobileNetV2 with the custom 2-class head.

    Frozen layers: all feature layers except the last 2 blocks.
    The classifier head is always trained from scratch.
    """
    weights = models.MobileNet_V2_Weights.IMAGENET1K_V1
    model = models.mobilenet_v2(weights=weights)

    # Freeze all backbone parameters
    for param in model.features.parameters():
        param.requires_grad = False

    # Unfreeze last 2 feature blocks (indices -2, -1)
    for block in list(model.features.children())[-2:]:
        for param in block.parameters():
            param.requires_grad = True

    # Replace the default head
    in_features = model.classifier[1].in_features  # 1280
    model.classifier = nn.Sequential(
        nn.Linear(in_features, 256),
        nn.ReLU(inplace=True),
        nn.Dropout(p=0.3),
        nn.Linear(256, num_classes),
    )
    return model


# ---------------------------------------------------------------------------
# Metrics helpers (scikit-learn)
# ---------------------------------------------------------------------------


def _compute_metrics(y_true: list[int], y_pred: list[int], y_prob: list[float]) -> dict[str, float]:
    """Return accuracy, precision, recall, F1, AUC-ROC."""
    try:
        from sklearn.metrics import (
            accuracy_score,
            f1_score,
            precision_score,
            recall_score,
            roc_auc_score,
        )

        metrics: dict[str, float] = {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "precision": float(precision_score(y_true, y_pred, zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, zero_division=0)),
            "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        }
        if len(set(y_true)) > 1:
            metrics["auc_roc"] = float(roc_auc_score(y_true, y_prob))
        else:
            metrics["auc_roc"] = float("nan")
        return metrics
    except ImportError:
        logger.warning("scikit-learn not installed — skipping extended metrics")
        correct = sum(p == t for p, t in zip(y_pred, y_true, strict=False))
        return {"accuracy": correct / max(len(y_true), 1)}


# ---------------------------------------------------------------------------
# Main trainer class
# ---------------------------------------------------------------------------


class MobileNetTrainer:
    """Fine-tune MobileNetV2 on malaria cell images and export to ONNX.

    Parameters
    ----------
    device:
        Torch device string, e.g. ``"cuda"`` or ``"cpu"``.  When *None*
        (default) the best available device is chosen automatically.
    """

    def __init__(self, device: str | None = None) -> None:
        if not _TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch is required.  Install with: pip install -r ml/requirements-train.txt"
            )
        self.device = torch.device(
            device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        )
        logger.info("MobileNetTrainer using device: %s", self.device)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train(
        self,
        data_dir: Path,
        output_dir: Path,
        *,
        epochs: int = 30,
        batch_size: int = 32,
        val_split: float = 0.2,
        seed: int = 42,
        num_workers: int = 0,
    ) -> dict[str, Any]:
        """Fine-tune MobileNetV2 and save the best checkpoint.

        Parameters
        ----------
        data_dir:
            Root directory with ``infected/`` and ``uninfected/`` sub-folders.
        output_dir:
            Directory where ``mobilenet_malaria_best.pt`` is written.
        epochs:
            Maximum number of training epochs.
        batch_size:
            Mini-batch size for training and validation loaders.
        val_split:
            Fraction of data reserved for validation (stratified).
        seed:
            Random seed for reproducibility.
        num_workers:
            DataLoader worker processes (0 = main process, safe on Windows).

        Returns
        -------
        dict
            Final training metrics and paths to saved artefacts.
        """
        from ml.dataset import MalariaSlideDataset, train_val_split

        torch.manual_seed(seed)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # ---- Dataset --------------------------------------------------------
        full_ds = MalariaSlideDataset(data_dir, train=True)
        train_ds, val_ds = train_val_split(full_ds, val_fraction=val_split, seed=seed)

        train_loader = DataLoader(
            train_ds,
            batch_size=batch_size,
            shuffle=True,
            num_workers=num_workers,
            pin_memory=(self.device.type == "cuda"),
        )
        val_loader = DataLoader(
            val_ds,
            batch_size=batch_size,
            shuffle=False,
            num_workers=num_workers,
            pin_memory=(self.device.type == "cuda"),
        )

        # ---- Model ----------------------------------------------------------
        model = _build_mobilenetv2().to(self.device)

        criterion = nn.CrossEntropyLoss(weight=full_ds.class_weights.to(self.device))
        optimizer = torch.optim.AdamW(
            filter(lambda p: p.requires_grad, model.parameters()),
            lr=1e-4,
            weight_decay=1e-5,
        )
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

        # ---- Training loop --------------------------------------------------
        best_val_loss = float("inf")
        patience_counter = 0
        patience = 5
        best_state: dict[str, Any] = {}
        history: list[dict[str, float]] = []
        best_epoch = 0

        for epoch in range(1, epochs + 1):
            train_metrics = self._run_epoch(
                model, train_loader, criterion, optimizer, training=True
            )
            val_metrics = self._run_epoch(
                model, val_loader, criterion, optimizer=None, training=False
            )
            scheduler.step()

            epoch_info = {
                "epoch": epoch,
                "train_loss": train_metrics["loss"],
                "train_acc": train_metrics["accuracy"],
                "val_loss": val_metrics["loss"],
                "val_acc": val_metrics["accuracy"],
            }
            history.append(epoch_info)
            logger.info(
                "Epoch %d/%d  train_loss=%.4f  train_acc=%.4f  val_loss=%.4f  val_acc=%.4f",
                epoch,
                epochs,
                epoch_info["train_loss"],
                epoch_info["train_acc"],
                epoch_info["val_loss"],
                epoch_info["val_acc"],
            )

            # Early stopping
            if val_metrics["loss"] < best_val_loss:
                best_val_loss = val_metrics["loss"]
                best_epoch = epoch
                patience_counter = 0
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info("Early stopping at epoch %d (patience=%d)", epoch, patience)
                    break

        # ---- Save checkpoint ------------------------------------------------
        model.load_state_dict(best_state)
        checkpoint_path = output_dir / "mobilenet_malaria_best.pt"
        torch.save(
            {
                "epoch": best_epoch,
                "model_state_dict": best_state,
                "val_loss": best_val_loss,
                "history": history,
            },
            checkpoint_path,
        )
        logger.info("Best checkpoint saved to %s (epoch %d)", checkpoint_path, best_epoch)

        # ---- Final evaluation on val set ------------------------------------
        val_report = self._evaluate_loader(model, val_loader)

        result: dict[str, Any] = {
            "best_epoch": best_epoch,
            "best_val_loss": best_val_loss,
            "checkpoint_path": str(checkpoint_path),
            "history": history,
            **val_report,
        }
        return result

    def evaluate(self, data_dir: Path, model_path: Path) -> dict[str, Any]:
        """Load a saved checkpoint and evaluate on the full dataset.

        Parameters
        ----------
        data_dir:
            Root directory with ``infected/`` and ``uninfected/`` sub-folders.
        model_path:
            Path to the ``.pt`` checkpoint produced by :meth:`train`.

        Returns
        -------
        dict
            accuracy, precision, recall, f1, auc_roc
        """
        from ml.dataset import MalariaSlideDataset

        model = _build_mobilenetv2().to(self.device)
        checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)
        model.load_state_dict(checkpoint["model_state_dict"])

        ds = MalariaSlideDataset(data_dir, train=False)
        loader = DataLoader(ds, batch_size=32, shuffle=False, num_workers=0)
        return self._evaluate_loader(model, loader)

    def export_onnx(
        self,
        model_path: Path,
        output_path: Path,
        input_size: tuple[int, int, int, int] = (1, 3, 224, 224),
    ) -> Path:
        """Export a saved PyTorch checkpoint to ONNX format.

        The exported model is compatible with ``app/services/malaria_ai.py``:
          - input  name  : ``"input"``
          - output name  : ``"output"``
          - output shape : ``(N, 2)`` float32 logits

        Parameters
        ----------
        model_path:
            Path to the ``.pt`` checkpoint.
        output_path:
            Destination ``.onnx`` file.
        input_size:
            NCHW shape for the dummy input (default: ``(1, 3, 224, 224)``).

        Returns
        -------
        Path
            *output_path* after successful export.
        """
        model = _build_mobilenetv2().to(self.device)
        checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        dummy = torch.zeros(*input_size, dtype=torch.float32, device=self.device)
        torch.onnx.export(
            model,
            dummy,
            str(output_path),
            opset_version=17,
            input_names=["input"],
            output_names=["output"],
            dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
            do_constant_folding=True,
        )
        logger.info("ONNX model exported to %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_epoch(
        self,
        model: nn.Module,
        loader: DataLoader,
        criterion: nn.Module,
        optimizer: Any | None,
        *,
        training: bool,
    ) -> dict[str, float]:
        """Run one epoch of training or validation."""
        model.train(training)
        total_loss = 0.0
        correct = 0
        total = 0

        context = torch.enable_grad() if training else torch.no_grad()
        with context:
            for imgs, labels in loader:
                imgs = imgs.to(self.device, non_blocking=True)
                labels = labels.to(self.device, non_blocking=True)

                outputs = model(imgs)
                loss = criterion(outputs, labels)

                if training and optimizer is not None:
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()

                total_loss += loss.item() * imgs.size(0)
                preds = outputs.argmax(dim=1)
                correct += (preds == labels).sum().item()
                total += imgs.size(0)

        return {
            "loss": total_loss / max(total, 1),
            "accuracy": correct / max(total, 1),
        }

    def _evaluate_loader(self, model: nn.Module, loader: DataLoader) -> dict[str, Any]:
        """Collect predictions from *loader* and compute extended metrics."""
        model.eval()
        y_true: list[int] = []
        y_pred: list[int] = []
        y_prob: list[float] = []

        with torch.no_grad():
            for imgs, labels in loader:
                imgs = imgs.to(self.device, non_blocking=True)
                outputs = model(imgs)
                probs = torch.softmax(outputs, dim=1)[:, 1]  # P(positive)
                preds = outputs.argmax(dim=1)

                y_true.extend(labels.cpu().tolist())
                y_pred.extend(preds.cpu().tolist())
                y_prob.extend(probs.cpu().tolist())

        return _compute_metrics(y_true, y_pred, y_prob)
