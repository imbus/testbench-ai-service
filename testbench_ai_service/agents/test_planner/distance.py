"""Cosine distances on L2-normalised embeddings, row by row or in blocks.

No n x n matrix is ever built, so memory stays O(n * d).
"""

import numpy as np


def normalize(embeddings: np.ndarray) -> np.ndarray:
    """Scale every row to unit length as float32; all-zero rows stay zero."""
    matrix = np.asarray(embeddings, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms > 0)


def distances_to(unit: np.ndarray, index: int) -> np.ndarray:
    """Cosine distance of every row to row ``index``, clipped to ``[0, 1]``."""
    return np.clip(1.0 - unit @ unit[index], 0.0, 1.0)


def mean_distances(unit: np.ndarray) -> np.ndarray:
    """Mean cosine distance of every row to all rows (itself included)."""
    return np.clip(1.0 - unit @ unit.mean(axis=0), 0.0, 1.0)


def close_pairs(
    unit: np.ndarray, threshold: float, block_size: int = 1024
) -> list[tuple[int, int]]:
    """All index pairs ``i < j`` whose distance is below ``threshold``."""
    pairs: list[tuple[int, int]] = []
    for start in range(0, len(unit), block_size):
        distances = np.clip(1.0 - unit[start : start + block_size] @ unit.T, 0.0, 1.0)
        rows, cols = np.nonzero(distances < threshold)
        rows = rows + start
        upper = cols > rows
        pairs.extend(zip(rows[upper].tolist(), cols[upper].tolist(), strict=True))
    return pairs
