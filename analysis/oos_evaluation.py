"""
Out-of-sample evaluation for Model A (conditional logit).

Performs an 80/20 position-level train/test split per ELO band,
fits Model A on the training fold (max_pos=100, same as the
committed learned_params), and evaluates top-1 human-choice
prediction accuracy on both folds.

Produces:
  - analysis/results/oos_evaluation.json

Usage (from repo root):
  python analysis/oos_evaluation.py

Runtime: ~20 min (MCMC × 4 bands). Results may vary slightly
across platforms due to floating-point differences in PyMC/JAX,
but should be very close to the committed JSON with seed=42.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.retrain_with_uncertainty import (
    BANDS,
    FEATURE_COLS,
    _log,
    fit_model_a,
    load_band_data,
    prepare_choice_data,
    standardize,
)

OUTPUT_PATH = REPO_ROOT / "analysis" / "results" / "oos_evaluation.json"
SEED = 42
TRAIN_FRACTION = 0.8


def _top1_accuracy(X_std: np.ndarray, choices: np.ndarray,
                   mask: np.ndarray, beta: np.ndarray) -> float:
    """Fraction of positions where argmax(utility) == human choice."""
    utils = np.einsum("ijk,k->ij", X_std, beta)
    utils[~mask] = -1e10
    preds = utils.argmax(axis=1)
    return float((preds == choices).mean() * 100)


def _baseline_accuracy(mask: np.ndarray) -> float:
    """Expected accuracy of uniform-random candidate selection."""
    k_per_pos = mask.sum(axis=1).astype(float)
    return float((1.0 / k_per_pos).mean() * 100)


def evaluate_band(band: str) -> dict | None:
    """80/20 OOS evaluation for one ELO band."""
    df = load_band_data(band)
    if df is None:
        return None

    # Identify valid positions (exactly one human move flagged)
    groups = df.groupby("fen")
    valid_fens = [fen for fen, g in groups if g["is_human_move"].sum() == 1]
    n_total = len(valid_fens)
    if n_total < 20:
        _log(f"  Band {band}: only {n_total} valid positions, skip")
        return None

    # Position-level 80/20 split
    rng = np.random.RandomState(SEED)
    n_train = int(n_total * TRAIN_FRACTION)
    perm = rng.permutation(n_total)
    fen_arr = np.array(valid_fens)
    train_fens = set(fen_arr[perm[:n_train]])
    test_fens = set(fen_arr[perm[n_train:]])

    df_train = df[df["fen"].isin(train_fens)]
    df_test = df[df["fen"].isin(test_fens)]

    X_train, ch_train, mask_train = prepare_choice_data(df_train, FEATURE_COLS)
    X_test, ch_test, mask_test = prepare_choice_data(df_test, FEATURE_COLS)

    # Standardize using training statistics only
    X_train_std, means, stds = standardize(X_train, mask_train)
    X_test_std = (X_test - means) / stds
    X_test_std[~mask_test] = 0.0

    _log(f"  Band {band}: {X_train.shape[0]} train, {X_test.shape[0]} test positions")

    # Fit Model A on training fold (internally subsamples to max_pos=100)
    trace = fit_model_a(X_train_std, ch_train, mask_train,
                        len(FEATURE_COLS), seed=SEED)

    beta_mean = trace.posterior["beta"].values.mean(axis=(0, 1))

    in_acc = _top1_accuracy(X_train_std, ch_train, mask_train, beta_mean)
    in_bl = _baseline_accuracy(mask_train)
    out_acc = _top1_accuracy(X_test_std, ch_test, mask_test, beta_mean)
    out_bl = _baseline_accuracy(mask_test)

    return {
        "n_train": X_train.shape[0],
        "n_test": X_test.shape[0],
        "in_sample_acc": round(in_acc, 1),
        "in_sample_baseline": round(in_bl, 1),
        "in_sample_lift": round(in_acc / in_bl, 1),
        "out_sample_acc": round(out_acc, 1),
        "out_sample_baseline": round(out_bl, 1),
        "out_sample_lift": round(out_acc / out_bl, 1),
    }


def main() -> None:
    _log("=" * 60)
    _log("Model A: Out-of-Sample Evaluation (80/20 position split)")
    _log("=" * 60)

    results = {}
    for band in BANDS:
        _log(f"\n--- Band {band} ---")
        r = evaluate_band(band)
        if r is None:
            continue
        results[band] = r
        _log(f"  In-sample:  {r['in_sample_acc']}% "
             f"(baseline {r['in_sample_baseline']}%, "
             f"lift {r['in_sample_lift']}x)")
        _log(f"  Out-sample: {r['out_sample_acc']}% "
             f"(baseline {r['out_sample_baseline']}%, "
             f"lift {r['out_sample_lift']}x)")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    _log(f"\nResults saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
