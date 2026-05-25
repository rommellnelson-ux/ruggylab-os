#!/usr/bin/env python
"""Fine-tune MobileNetV2 on malaria blood-smear images and export to ONNX.

This script is the main entry-point for the training pipeline.  It does NOT
modify ``requirements.txt``; PyTorch and related packages are listed in
``ml/requirements-train.txt`` and must be installed separately.

Quick start
-----------
Install training dependencies (once, on the training machine):

    pip install -r ml/requirements-train.txt

Prepare your dataset (BBBC041 or NIH Malaria Dataset):

    data/malaria/
        infected/    *.png / *.jpg
        uninfected/  *.png / *.jpg

Run training:

    python scripts/train_mobilenet.py \\
        --data-dir data/malaria \\
        --output-dir models/ \\
        --epochs 30 \\
        --batch-size 32 \\
        --val-split 0.2 \\
        --seed 42 \\
        --export-onnx

Outputs
-------
  models/mobilenet_malaria_best.pt      — best PyTorch checkpoint
  models/mobilenet_malaria.onnx         — ONNX export (if --export-onnx)
  models/training_report.json           — metrics + artefact paths
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("train_mobilenet")


def _check_torch() -> None:
    """Exit with a clear message when PyTorch is not installed."""
    try:
        import torch  # noqa: F401
        import torchvision  # noqa: F401
    except ImportError as exc:
        sys.exit(
            f"Missing dependency: {exc}\n"
            "Install training dependencies with:\n"
            "    pip install -r ml/requirements-train.txt"
        )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fine-tune MobileNetV2 for malaria blood-smear classification",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Root directory with infected/ and uninfected/ sub-folders",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("models"),
        help="Directory for checkpoints, ONNX export, and training report",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=30,
        help="Maximum number of training epochs (early stopping may end sooner)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Mini-batch size",
    )
    parser.add_argument(
        "--val-split",
        type=float,
        default=0.2,
        help="Fraction of data reserved for validation (stratified)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--export-onnx",
        action="store_true",
        help="Export the best checkpoint to ONNX after training",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Torch device (e.g. 'cuda', 'cpu').  Auto-detected when omitted.",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="DataLoader worker processes (0 = main process, safe on Windows)",
    )
    parser.add_argument(
        "--validate-onnx",
        action="store_true",
        help="Run onnx_validator after export to confirm app compatibility",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    _check_torch()

    # Late import — only after we know torch is available
    # (keeps the --help path functional without torch)
    from ml.trainer import MobileNetTrainer

    # ------------------------------------------------------------------ train
    logger.info("Starting training  data=%s  output=%s", args.data_dir, args.output_dir)
    trainer = MobileNetTrainer(device=args.device)

    report = trainer.train(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        val_split=args.val_split,
        seed=args.seed,
        num_workers=args.num_workers,
    )

    checkpoint_path = Path(report["checkpoint_path"])

    # ------------------------------------------------------------------ onnx
    onnx_path: Path | None = None
    if args.export_onnx:
        onnx_path = args.output_dir / "mobilenet_malaria.onnx"
        logger.info("Exporting to ONNX: %s", onnx_path)
        trainer.export_onnx(checkpoint_path, onnx_path)
        report["onnx_path"] = str(onnx_path)

        if args.validate_onnx:
            from ml.onnx_validator import validate_onnx_model

            val_result = validate_onnx_model(onnx_path)
            report["onnx_validation"] = val_result
            if val_result["valid"]:
                logger.info(
                    "ONNX validation passed (inference=%.1f ms)",
                    val_result["inference_time_ms"],
                )
            else:
                logger.warning("ONNX validation FAILED: %s", val_result.get("error"))

    # ------------------------------------------------------------------ report
    report_path = args.output_dir / "training_report.json"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    logger.info("Training report saved to %s", report_path)

    # ------------------------------------------------------------------ summary
    print("\n" + "=" * 60)
    print("Training complete")
    print(f"  Best epoch    : {report.get('best_epoch')}")
    print(f"  Best val loss : {report.get('best_val_loss', 0):.4f}")
    print(f"  Accuracy      : {report.get('accuracy', 0):.4f}")
    print(f"  F1            : {report.get('f1', 0):.4f}")
    print(f"  AUC-ROC       : {report.get('auc_roc', float('nan')):.4f}")
    print(f"  Checkpoint    : {checkpoint_path}")
    if onnx_path:
        print(f"  ONNX export   : {onnx_path}")
    print(f"  Report        : {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
