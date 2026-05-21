#!/usr/bin/env python
"""Fine-tune MobileNetV2 on malaria cell images and export to ONNX.

Usage
-----
Install extra dependencies (NOT in requirements.txt — only needed once):

    pip install torch torchvision pillow tqdm

Download the NIH / Kaggle cell-image dataset, then run:

    python scripts/build_malaria_model.py \\
        --data-dir data/malaria_cells \\
        --output-path models/malaria_mobilenetv2/model.onnx \\
        --epochs 10 \\
        --batch-size 32

Dataset layout expected
-----------------------
data/malaria_cells/
    train/
        Parasitized/   (positive)
        Uninfected/    (negative)
    val/
        Parasitized/
        Uninfected/

The NIH cell-image library can be downloaded from:
    https://lhncbc.nlm.nih.gov/LHC-research/LHC-projects/image-processing/malaria-screener.html

Or the Kaggle mirror:
    https://www.kaggle.com/datasets/iarunava/cell-images-for-detecting-malaria
"""

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Build malaria MobileNetV2 ONNX model")
    parser.add_argument("--data-dir",    required=True,  help="Root directory with train/val sub-dirs")
    parser.add_argument("--output-path", required=True,  help="Output .onnx file path")
    parser.add_argument("--epochs",      type=int, default=10)
    parser.add_argument("--batch-size",  type=int, default=32)
    parser.add_argument("--lr",          type=float, default=1e-4)
    parser.add_argument("--workers",     type=int, default=4)
    args = parser.parse_args()

    # ------------------------------------------------------------------ imports
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
        from torch.utils.data import DataLoader
        from torchvision import datasets, models, transforms
        from tqdm import tqdm
    except ImportError as exc:
        sys.exit(
            f"Missing dependency: {exc}\n"
            "Install with: pip install torch torchvision pillow tqdm"
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # ------------------------------------------------------------------ data
    _mean = [0.485, 0.456, 0.406]
    _std  = [0.229, 0.224, 0.225]

    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(224),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
        transforms.ToTensor(),
        transforms.Normalize(_mean, _std),
    ])
    val_tf = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(_mean, _std),
    ])

    train_ds = datasets.ImageFolder(os.path.join(args.data_dir, "train"), transform=train_tf)
    val_ds   = datasets.ImageFolder(os.path.join(args.data_dir, "val"),   transform=val_tf)

    # The ImageFolder sorts classes alphabetically:
    # Parasitized → index 0  (but we want "positive" = index 1)
    # Uninfected  → index 1
    # Remap so positive=1 matches the model output convention.
    # If your folder names differ, adjust class_to_idx accordingly.
    print("Class mapping:", train_ds.class_to_idx)

    train_dl = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,  num_workers=args.workers)
    val_dl   = DataLoader(val_ds,   batch_size=args.batch_size, shuffle=False, num_workers=args.workers)

    # ------------------------------------------------------------------ model
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1)
    # Replace the classifier head for 2-class output
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, 2)
    model = model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    # ------------------------------------------------------------------ train
    best_val_acc = 0.0
    best_state   = None

    for epoch in range(1, args.epochs + 1):
        # -- train --
        model.train()
        train_loss = 0.0
        train_correct = 0
        for imgs, labels in tqdm(train_dl, desc=f"Epoch {epoch}/{args.epochs} [train]"):
            imgs, labels = imgs.to(device), labels.to(device)
            optimizer.zero_grad()
            out = model(imgs)
            loss = criterion(out, labels)
            loss.backward()
            optimizer.step()
            train_loss    += loss.item() * imgs.size(0)
            train_correct += (out.argmax(1) == labels).sum().item()
        scheduler.step()

        # -- validate --
        model.eval()
        val_correct = 0
        with torch.no_grad():
            for imgs, labels in tqdm(val_dl, desc=f"Epoch {epoch}/{args.epochs} [val]  "):
                imgs, labels = imgs.to(device), labels.to(device)
                out = model(imgs)
                val_correct += (out.argmax(1) == labels).sum().item()

        train_acc = train_correct / len(train_ds)
        val_acc   = val_correct   / len(val_ds)
        print(
            f"  loss={train_loss/len(train_ds):.4f}  "
            f"train_acc={train_acc:.4f}  val_acc={val_acc:.4f}"
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state   = {k: v.clone() for k, v in model.state_dict().items()}

    # ------------------------------------------------------------------ export
    model.load_state_dict(best_state)
    model.eval()

    os.makedirs(os.path.dirname(os.path.abspath(args.output_path)), exist_ok=True)
    dummy = torch.zeros(1, 3, 224, 224, device=device)
    torch.onnx.export(
        model,
        dummy,
        args.output_path,
        opset_version=17,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
    )
    print(f"\nModel exported to {args.output_path}")
    print(f"Best val accuracy: {best_val_acc:.4f}")


if __name__ == "__main__":
    main()
