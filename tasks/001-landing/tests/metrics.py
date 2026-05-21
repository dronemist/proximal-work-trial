"""
Phase 1 grader metrics.

Only SSIM here. DreamSim, Block-Match, and TreeBLEU land in Phase 2+ — see
key_decisions.md R1. Interface is shaped so additional metrics drop in without
re-plumbing the grader.

Each metric returns a float in [0.0, 1.0] where 1.0 means identical.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity


@dataclass
class MetricResult:
    name: str
    score: float
    extra: dict


def _load_pair(reference: Path, candidate: Path) -> tuple[np.ndarray, np.ndarray, tuple, tuple]:
    """Load both as RGB arrays WITHOUT silent resizing.

    Returns (ref_array, cand_array, ref_size, cand_size).
    Caller is responsible for handling dimension mismatch.
    """
    ref = Image.open(reference).convert("RGB")
    cand = Image.open(candidate).convert("RGB")
    return np.array(ref), np.array(cand), ref.size, cand.size


def ssim(reference: Path, candidate: Path) -> MetricResult:
    """SSIM with height-mismatch handled by zero-padding shorter image.

    - Width mismatch → hard 0.0 (width is fixed at 1440 by render.py; any drift is a real bug).
    - Height mismatch → pad shorter image's bottom with black to match taller; score normally.
      Symmetric: candidate-too-tall and candidate-too-short are both penalized by the
      padded region not matching the other's actual content.
    """
    ref_arr, cand_arr, ref_size, cand_size = _load_pair(reference, candidate)

    # Width mismatch: real bug, fail loud.
    if ref_arr.shape[1] != cand_arr.shape[1]:
        return MetricResult(
            name="ssim",
            score=0.0,
            extra={
                "reference_size": list(ref_size),
                "candidate_size": list(cand_size),
                "width_mismatch": True,
            },
        )

    # Height mismatch: pad shorter to taller with black.
    height_padded = False
    if ref_arr.shape[0] != cand_arr.shape[0]:
        height_padded = True
        target_h = max(ref_arr.shape[0], cand_arr.shape[0])
        ref_arr = _pad_to(ref_arr, target_h)
        cand_arr = _pad_to(cand_arr, target_h)

    score, _ = structural_similarity(
        ref_arr,
        cand_arr,
        channel_axis=2,
        data_range=255,
        full=True,
    )
    score = float(max(0.0, min(1.0, score)))
    return MetricResult(
        name="ssim",
        score=score,
        extra={
            "reference_size": list(ref_size),
            "candidate_size": list(cand_size),
            "height_padded": height_padded,
            "width_mismatch": False,
        },
    )


def _pad_to(arr: np.ndarray, target_h: int) -> np.ndarray:
    """Pad arr's bottom with black (RGB 0,0,0) until it reaches target_h rows."""
    if arr.shape[0] >= target_h:
        return arr
    pad = np.zeros((target_h - arr.shape[0], arr.shape[1], arr.shape[2]), dtype=arr.dtype)
    return np.concatenate([arr, pad], axis=0)
