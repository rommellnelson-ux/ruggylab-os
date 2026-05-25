# Malaria Classifier — Training Guide

This guide explains how to fine-tune MobileNetV2 on malaria blood-smear images
and export the result to ONNX for use by the RuggyLab OS server.

---

## 1. Prerequisites

The training pipeline uses **PyTorch**, which is deliberately excluded from
`requirements.txt` (inference-only).  Install the training extras once on the
machine that will run the training:

```bash
pip install -r ml/requirements-train.txt
```

This installs:

| Package | Minimum version |
|---------|----------------|
| torch | 2.3.0 |
| torchvision | 0.18.0 |
| scikit-learn | 1.5.0 |
| tqdm | 4.66.0 |

> A GPU is optional.  Training on CPU is slow (~30 min / epoch for the NIH
> dataset) but fully supported.

---

## 2. Dataset

### Option A — NIH Malaria Dataset (recommended)

Download from the official NIH page:
<https://lhncbc.nlm.nih.gov/LHC-research/LHC-projects/image-processing/malaria-screener.html>

Or the Kaggle mirror:
<https://www.kaggle.com/datasets/iarunava/cell-images-for-detecting-malaria>

After downloading, reorganise the folders to match the expected layout:

```
data/malaria/
    infected/       # Parasitized cells  (Plasmodium falciparum)
    uninfected/     # Healthy red blood cells
```

Example commands (Linux/macOS):

```bash
mkdir -p data/malaria/infected data/malaria/uninfected
cp cell_images/Parasitized/*.png  data/malaria/infected/
cp cell_images/Uninfected/*.png   data/malaria/uninfected/
```

### Option B — BBBC041 (Plasmodium falciparum)

Download from the Broad Institute:
<https://bbbc.broadinstitute.org/BBBC041>

The `infected/` folder should contain images annotated as containing
Plasmodium.  The `uninfected/` folder should contain images without parasites.

---

## 3. Directory layout

```
data/malaria/
    infected/
        img_000001.png
        img_000002.png
        …
    uninfected/
        img_000001.png
        img_000002.png
        …
```

Supported image formats: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff`, `.tif`

---

## 4. Training

```bash
python scripts/train_mobilenet.py \
    --data-dir  data/malaria \
    --output-dir models/ \
    --epochs    30 \
    --batch-size 32 \
    --val-split  0.2 \
    --seed       42 \
    --export-onnx \
    --validate-onnx
```

### Key options

| Flag | Default | Description |
|------|---------|-------------|
| `--data-dir` | required | Root of the dataset |
| `--output-dir` | `models/` | Destination for all outputs |
| `--epochs` | 30 | Max epochs (early stopping at patience=5) |
| `--batch-size` | 32 | Mini-batch size |
| `--val-split` | 0.2 | Validation fraction (stratified) |
| `--seed` | 42 | Random seed |
| `--export-onnx` | off | Export best checkpoint to ONNX |
| `--validate-onnx` | off | Run compatibility check after export |
| `--device` | auto | Force `cuda` or `cpu` |
| `--num-workers` | 0 | DataLoader workers (0 = safe on Windows) |

---

## 5. Outputs

After a successful run, `models/` will contain:

| File | Description |
|------|-------------|
| `mobilenet_malaria_best.pt` | Best PyTorch checkpoint (lowest val_loss) |
| `mobilenet_malaria.onnx` | ONNX export ready for the server |
| `training_report.json` | Accuracy, precision, recall, F1, AUC-ROC |

---

## 6. Deploy the model

Copy the ONNX file to the path configured in `settings.MALARIA_MODEL_PATH`
(default: `models/malaria_mobilenetv2/model.onnx`):

```bash
mkdir -p models/malaria_mobilenetv2
cp models/mobilenet_malaria.onnx models/malaria_mobilenetv2/model.onnx
```

Then restart (or reload) the FastAPI server.  The `MobileNetV2Classifier` in
`app/services/malaria_ai.py` will automatically detect and load the new model.

---

## 7. Validation

To verify the model is compatible with the app before deploying:

```python
from ml.onnx_validator import validate_onnx_model
from pathlib import Path

result = validate_onnx_model(Path("models/mobilenet_malaria.onnx"))
print(result)
# {"valid": True, "output_shape": (1, 2), "inference_time_ms": 45.3, ...}
```

Or run the full test suite (requires PyTorch):

```bash
python -m pytest tests/test_ml_pipeline.py -v
```

---

## 8. Architecture summary

| Component | Details |
|-----------|---------|
| Backbone | MobileNetV2, ImageNet-pretrained (torchvision) |
| Frozen layers | All feature layers except last 2 blocks |
| Classifier head | Linear(1280→256) → ReLU → Dropout(0.3) → Linear(256→2) |
| Loss | CrossEntropyLoss with class-frequency weights |
| Optimizer | AdamW (lr=1e-4, weight_decay=1e-5) |
| Scheduler | CosineAnnealingLR |
| Early stopping | patience=5 epochs on val_loss |
| Input | float32 (1, 3, 224, 224), ImageNet-normalised |
| Output | float32 logits (N, 2) — [negative, positive] |

---

## 9. Clinical disclaimer

> This software is for **research and demonstration purposes only**.
> Results must be confirmed by a qualified medical professional before
> any clinical decision is taken.  The software authors accept no
> liability for clinical outcomes.
