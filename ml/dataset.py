"""PyTorch Dataset for malaria blood smear images.

Compatible with:
  - BBBC041 (Plasmodium falciparum)
  - NIH Malaria Dataset (cell-images)

Expected directory layout
--------------------------
data/
    infected/    *.png or *.jpg  (Plasmodium present)
    uninfected/  *.png or *.jpg  (healthy red blood cells)

Label convention (matches app/services/malaria_ai.py)
------------------------------------------------------
  0 → "negative" (uninfected)
  1 → "positive" (infected)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

try:
    import torch
    from PIL import Image
    from torch.utils.data import Dataset
    from torchvision import transforms

    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)

# ImageNet normalisation — same as app/services/malaria_ai.py
_IMAGENET_MEAN = [0.485, 0.456, 0.406]
_IMAGENET_STD = [0.229, 0.224, 0.225]

_SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}


def _build_train_transform():
    """Return the augmentation pipeline for the training split."""
    return transforms.Compose(
        [
            transforms.Resize(256),
            transforms.RandomCrop(224),
            transforms.RandomHorizontalFlip(),
            transforms.RandomVerticalFlip(),
            transforms.RandomRotation(90),
            transforms.ColorJitter(brightness=0.2, contrast=0.2),
            transforms.ToTensor(),
            transforms.Normalize(_IMAGENET_MEAN, _IMAGENET_STD),
        ]
    )


def _build_val_transform():
    """Return the deterministic pipeline for the validation / inference split."""
    return transforms.Compose(
        [
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(_IMAGENET_MEAN, _IMAGENET_STD),
        ]
    )


def _collect_samples(data_dir: Path) -> list[tuple[Path, int]]:
    """Walk *data_dir* and return ``(image_path, label)`` pairs.

    Folder names are case-insensitive.  Any folder whose name starts with
    ``infected`` (excluding ``uninfected``) gets label **1**; folders starting
    with ``uninfected`` get label **0**.  Unknown folders are ignored with a
    warning.
    """
    samples: list[tuple[Path, int]] = []
    for subdir in sorted(data_dir.iterdir()):
        if not subdir.is_dir():
            continue
        name_lower = subdir.name.lower()
        if name_lower.startswith("uninfected"):
            label = 0
        elif "infected" in name_lower or "parasitized" in name_lower or "positive" in name_lower:
            label = 1
        else:
            logger.warning("Skipping unknown subdirectory: %s", subdir)
            continue
        for path in sorted(subdir.iterdir()):
            if path.suffix.lower() in _SUPPORTED_EXTENSIONS:
                samples.append((path, label))
    return samples


if _TORCH_AVAILABLE:

    class MalariaSlideDataset(Dataset):
        """Dataset of malaria blood-smear images for binary classification.

        Parameters
        ----------
        data_dir:
            Root directory with ``infected/`` and ``uninfected/`` sub-folders.
        train:
            When *True* applies data-augmentation transforms; when *False*
            applies the deterministic validation pipeline.
        transform:
            Optional custom ``torchvision.transforms`` pipeline.  When
            provided it overrides the default train/val transforms.
        """

        def __init__(
            self,
            data_dir: str | Path,
            *,
            train: bool = True,
            transform=None,
        ) -> None:
            self.data_dir = Path(data_dir)
            self.train = train
            self.samples = _collect_samples(self.data_dir)
            if not self.samples:
                raise ValueError(
                    f"No images found in {self.data_dir}.  "
                    "Expected sub-folders: infected/ and uninfected/"
                )
            self.transform = transform or (
                _build_train_transform() if train else _build_val_transform()
            )
            # Class weights for imbalanced datasets
            n_total = len(self.samples)
            n_infected = sum(1 for _, lbl in self.samples if lbl == 1)
            n_uninfected = n_total - n_infected
            # Weight inversely proportional to class frequency
            w_infected = n_total / (2.0 * max(n_infected, 1))
            w_uninfected = n_total / (2.0 * max(n_uninfected, 1))
            self.class_weights = torch.tensor([w_uninfected, w_infected], dtype=torch.float32)

            logger.info(
                "MalariaSlideDataset: %d images (%d infected, %d uninfected) [%s]",
                n_total,
                n_infected,
                n_uninfected,
                "train" if train else "val",
            )

        # ------------------------------------------------------------------
        def __len__(self) -> int:
            return len(self.samples)

        def __getitem__(self, idx: int):
            path, label = self.samples[idx]
            img = Image.open(path).convert("RGB")
            tensor = self.transform(img)
            return tensor, label

        # ------------------------------------------------------------------
        @property
        def labels(self) -> list[int]:
            """Return a flat list of all labels (useful for stratified splits)."""
            return [lbl for _, lbl in self.samples]

else:  # pragma: no cover — torch not installed

    class MalariaSlideDataset:  # type: ignore[no-redef]
        """Stub raised when PyTorch is not installed."""

        def __init__(self, *args, **kwargs) -> None:
            raise ImportError(
                "PyTorch is required for MalariaSlideDataset.  "
                "Install it with: pip install -r ml/requirements-train.txt"
            )


def train_val_split(
    dataset: MalariaSlideDataset,
    val_fraction: float = 0.2,
    seed: int = 42,
) -> tuple[MalariaSlideDataset, MalariaSlideDataset]:
    """Split *dataset* into training and validation subsets.

    Uses stratified sampling to preserve the infected/uninfected ratio.

    Returns
    -------
    train_dataset, val_dataset
        Two ``MalariaSlideDataset`` instances sharing the same ``data_dir``
        but with disjoint ``samples`` lists and appropriate transforms.
    """
    if not _TORCH_AVAILABLE:
        raise ImportError("PyTorch is required.  pip install -r ml/requirements-train.txt")

    from sklearn.model_selection import train_test_split

    indices = list(range(len(dataset)))
    labels = dataset.labels
    train_idx, val_idx = train_test_split(
        indices,
        test_size=val_fraction,
        stratify=labels,
        random_state=seed,
    )

    # Build lightweight wrappers that reuse the parent's sample list
    train_ds = _SubsetDataset(dataset, train_idx, transform=_build_train_transform())
    val_ds = _SubsetDataset(dataset, val_idx, transform=_build_val_transform())
    return train_ds, val_ds  # type: ignore[return-value]


if _TORCH_AVAILABLE:

    class _SubsetDataset(Dataset):
        """Internal: wraps a MalariaSlideDataset with a subset of indices."""

        def __init__(self, parent: MalariaSlideDataset, indices: list[int], transform) -> None:
            self._parent = parent
            self._indices = indices
            self.transform = transform
            self.class_weights = parent.class_weights

        def __len__(self) -> int:
            return len(self._indices)

        def __getitem__(self, idx: int):
            path, label = self._parent.samples[self._indices[idx]]
            img = Image.open(path).convert("RGB")
            return self.transform(img), label

        @property
        def labels(self) -> list[int]:
            return [self._parent.samples[i][1] for i in self._indices]

else:  # pragma: no cover

    class _SubsetDataset:  # type: ignore[no-redef]
        pass


def make_synthetic_dataset(tmp_dir: Path, n_infected: int = 10, n_uninfected: int = 10) -> Path:
    """Create a tiny synthetic dataset for unit tests (no real images needed).

    Generates random-colour PNG images using only Pillow + numpy.

    Parameters
    ----------
    tmp_dir:
        Directory where ``infected/`` and ``uninfected/`` sub-folders are created.
    n_infected:
        Number of synthetic infected images to generate.
    n_uninfected:
        Number of synthetic uninfected images to generate.

    Returns
    -------
    Path
        *tmp_dir* itself, ready to pass to ``MalariaSlideDataset``.
    """
    from PIL import Image as PILImage

    rng = np.random.default_rng(0)
    for folder, count in [("infected", n_infected), ("uninfected", n_uninfected)]:
        out = tmp_dir / folder
        out.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            arr = rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)
            PILImage.fromarray(arr).save(out / f"img_{i:04d}.png")
    return tmp_dir
