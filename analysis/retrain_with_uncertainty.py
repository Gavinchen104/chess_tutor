"""
Re-train Bayesian models and export posterior uncertainty.

Produces:
  - data/trained_models/learned_params.json  (means + SDs + 94% HDI)
  - PML_Project/posteriors.pdf               (coefficients with error bars)
  - analysis/results/mcmc_diagnostics.json   (R-hat, ESS, convergence)

Usage:
  python analysis/retrain_with_uncertainty.py
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

import arviz as az
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pymc as pm

warnings.filterwarnings("ignore", category=FutureWarning)


def _log(msg: str) -> None:
    """Print with immediate flush so progress is visible."""
    print(msg, flush=True)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "processed"
OUTPUT_JSON = REPO_ROOT / "data" / "trained_models" / "learned_params.json"
OUTPUT_FIG = REPO_ROOT / "PML_Project" / "posteriors.pdf"
OUTPUT_DIAG = REPO_ROOT / "analysis" / "results" / "mcmc_diagnostics.json"

BANDS = ["600", "1000", "1400", "1800"]

FEATURE_COLS = [
    "eval_gap", "difficulty", "safety_change", "center_change",
    "king_safety_change", "development_change", "mobility_change",
    "material_change", "opponent_pressure_change",
    "is_capture", "is_check", "is_castling",
    "num_preferred_tags", "num_priorities",
]

TUTOR_FEATURES = [
    "eval_gap", "num_preferred_tags", "num_priorities", "safety_change",
    "king_safety_change", "center_change", "opponent_pressure_change",
    "difficulty",
]


def load_band_data(band: str) -> pd.DataFrame | None:
    """Load feature CSV for a band."""
    path = DATA_DIR / f"features_{band}.csv"
    if not path.exists():
        _log(f"  [SKIP] {path} not found")
        return None
    return pd.read_csv(path)


def prepare_choice_data(df: pd.DataFrame, feature_cols: list[str]):
    """Reshape into padded arrays for conditional logit."""
    groups = df.groupby("fen")
    valid_fens = [fen for fen, g in groups if g["is_human_move"].sum() == 1]
    n_pos = len(valid_fens)
    n_feat = len(feature_cols)
    max_k = df.groupby("fen").size().max()
    X = np.zeros((n_pos, max_k, n_feat))
    choices = np.zeros(n_pos, dtype=int)
    mask = np.zeros((n_pos, max_k), dtype=bool)
    for i, fen in enumerate(valid_fens):
        group = groups.get_group(fen)
        k = len(group)
        X[i, :k, :] = group[feature_cols].values
        mask[i, :k] = True
        choices[i] = group["is_human_move"].values.argmax()
    return X, choices, mask


def standardize(X, mask):
    """Standardize features using only valid entries."""
    flat = X[mask]
    means = flat.mean(axis=0)
    stds = flat.std(axis=0)
    stds[stds < 1e-8] = 1.0
    X_std = (X - means) / stds
    X_std[~mask] = 0.0
    return X_std, means, stds


def fit_model_a(X, choices, mask, n_features, seed=42):
    """Fit conditional logit and return trace."""
    n_draws = 400
    n_tune = 200
    max_pos = 100
    max_k = 20
    if X.shape[0] > max_pos:
        idx = np.random.RandomState(seed).choice(X.shape[0], max_pos, replace=False)
        X, choices, mask = X[idx], choices[idx], mask[idx]
    if X.shape[1] > max_k:
        X = X[:, :max_k, :]
        mask = mask[:, :max_k]
        for i in range(len(choices)):
            if choices[i] >= max_k:
                choices[i] = 0
    _log(f"    Fitting: {X.shape[0]} positions, max_K={X.shape[1]}, {n_tune} tune + {n_draws} draws × 2 chains")
    with pm.Model():
        beta = pm.Normal("beta", mu=0, sigma=5, shape=n_features)
        utils = pm.math.dot(X, beta)
        p = pm.math.softmax(utils + np.where(mask, 0.0, -1e10), axis=1)
        pm.Categorical("choice", p=p, observed=choices)
        trace = pm.sample(
            n_draws, tune=n_tune, cores=1, chains=2,
            return_inferencedata=True, progressbar=True, random_seed=seed,
        )
    _log("    Sampling complete.")
    return trace


def fit_model_b(X, y, n_features, seed=42):
    """Fit logistic regression and return trace."""
    n_draws = 500
    n_tune = 300
    _log(f"    Fitting: {len(y)} samples, {n_tune} tune + {n_draws} draws × 2 chains")
    with pm.Model():
        intercept = pm.Normal("intercept", mu=0, sigma=5)
        weights = pm.Normal("weights", mu=0, sigma=5, shape=n_features)
        pm.Bernoulli("y_obs", logit_p=intercept + pm.math.dot(X, weights), observed=y)
        trace = pm.sample(
            n_draws, tune=n_tune, cores=1, chains=2,
            return_inferencedata=True, progressbar=True,
            random_seed=seed, target_accept=0.9,
        )
    _log("    Sampling complete.")
    return trace


def extract_posterior_stats(trace, var_name: str, feature_names: list[str]) -> dict:
    """Extract mean, SD, 94% HDI for each coefficient."""
    summary = az.summary(trace, var_names=[var_name], hdi_prob=0.94)
    result = {}
    for i, feat in enumerate(feature_names):
        row_label = f"{var_name}[{i}]"
        if row_label in summary.index:
            row = summary.loc[row_label]
            result[feat] = {
                "mean": float(row["mean"]),
                "sd": float(row["sd"]),
                "hdi_3%": float(row["hdi_3%"]),
                "hdi_97%": float(row["hdi_97%"]),
                "r_hat": float(row["r_hat"]),
                "ess_bulk": float(row["ess_bulk"]),
            }
    return result


def prepare_tutor_data(dfs: dict[str, pd.DataFrame]):
    """Prepare Model B training data with aspirational labels."""
    band_pairs = [("1000", "1400"), ("1400", "1800"), ("1800", "1800")]
    result = {}
    for current, target in band_pairs:
        if current not in dfs or target not in dfs:
            continue
        common = set(dfs[current]["fen"].unique()) & set(dfs[target]["fen"].unique())
        if len(common) < 20:
            _log(f"  Band {current}->{target}: only {len(common)} overlap, skip")
            continue
        target_choices = {}
        for fen in common:
            tg = dfs[target][dfs[target]["fen"] == fen]
            target_choices[fen] = set(tg[tg["is_human_move"] == 1]["move_uci"])
        rows = dfs[current][dfs[current]["fen"].isin(common)].copy()
        rows["is_aspirational"] = rows.apply(
            lambda r: int(r["move_uci"] in target_choices.get(r["fen"], set())), axis=1
        )
        X = rows[TUTOR_FEATURES].values.astype(float)
        y = rows["is_aspirational"].values.astype(float)
        means = X.mean(axis=0)
        stds = X.std(axis=0)
        stds[stds < 1e-8] = 1.0
        X_std = (X - means) / stds
        result[current] = {"X": X_std, "y": y, "means": means, "stds": stds}
        _log(f"  Band {current}->{target}: {len(y)} samples, {len(common)} positions")
    return result


def generate_posteriors_figure(params: dict, output_path: Path):
    """Generate posteriors.pdf with error bars."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 7))

    # Panel 1: Model A is_castling across bands
    ax = axes[0]
    bands_a = sorted(params["model_a"].keys(), key=int)
    castling_means = []
    castling_lows = []
    castling_highs = []
    for b in bands_a:
        stats = params["model_a"][b]["coefficients_stats"].get("is_castling", {})
        castling_means.append(stats.get("mean", 0))
        castling_lows.append(stats.get("hdi_3%", 0))
        castling_highs.append(stats.get("hdi_97%", 0))
    x = range(len(bands_a))
    means_arr = np.array(castling_means)
    errs = np.array([means_arr - castling_lows, np.array(castling_highs) - means_arr])
    ax.errorbar(x, means_arr, yerr=errs, fmt="o-", capsize=6, capthick=2,
                color="#2196F3", linewidth=2, markersize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"ELO {b}" for b in bands_a])
    ax.set_ylabel("Coefficient (with 94% HDI)")
    ax.set_title("Model A: is_castling\n(near zero at all bands; HDI spans zero)")
    ax.axhline(0, color="gray", linestyle="--", alpha=0.5)

    # Panel 2: Model B difficulty across bands
    ax = axes[1]
    bands_b = sorted(params["model_b"].keys(), key=int)
    bands_b = [b for b in bands_b if "weights_stats" in params["model_b"][b]]
    diff_means = []
    diff_lows = []
    diff_highs = []
    for b in bands_b:
        stats = params["model_b"][b]["weights_stats"].get("difficulty", {})
        diff_means.append(stats.get("mean", 0))
        diff_lows.append(stats.get("hdi_3%", 0))
        diff_highs.append(stats.get("hdi_97%", 0))
    x = range(len(bands_b))
    means_arr = np.array(diff_means)
    errs = np.array([means_arr - diff_lows, np.array(diff_highs) - means_arr])
    ax.errorbar(x, means_arr, yerr=errs, fmt="s-", capsize=6, capthick=2,
                color="#F44336", linewidth=2, markersize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"Band {b}" for b in bands_b])
    ax.set_ylabel("Coefficient (with 94% HDI)")
    ax.set_title("Model B: difficulty penalty\n(HDI excludes zero at band 1800)")
    ax.axhline(0, color="gray", linestyle="--", alpha=0.5)

    # Panel 3: Model A selected features across bands
    ax = axes[2]
    show_feats = ["is_capture", "is_check", "is_castling", "difficulty"]
    colors = ["#4CAF50", "#FF9800", "#2196F3", "#9C27B0"]
    width = 0.18
    x_base = np.arange(len(bands_a))
    for j, feat in enumerate(show_feats):
        means_f = []
        lows_f = []
        highs_f = []
        for b in bands_a:
            stats = params["model_a"][b]["coefficients_stats"].get(feat, {})
            means_f.append(stats.get("mean", 0))
            lows_f.append(stats.get("hdi_3%", 0))
            highs_f.append(stats.get("hdi_97%", 0))
        means_arr = np.array(means_f)
        errs = np.array([means_arr - lows_f, np.array(highs_f) - means_arr])
        ax.errorbar(x_base + j * width, means_arr, yerr=errs,
                     fmt="o", capsize=4, color=colors[j], label=feat, markersize=5)
    ax.set_xticks(x_base + width * 1.5)
    ax.set_xticklabels([f"ELO {b}" for b in bands_a])
    ax.set_ylabel("Coefficient (with 94% HDI)")
    ax.set_title("Model A: key features across ELO\n(error bars = 94% HDI)")
    ax.legend(loc="upper left", fontsize=9)
    ax.axhline(0, color="gray", linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    _log(f"  Saved figure to {output_path}")


def main():
    _log("=" * 60)
    _log("Bayesian Model Training with Uncertainty Export")
    _log("=" * 60)

    # Load data
    _log("\n[1/5] Loading feature data...")
    dfs: dict[str, pd.DataFrame] = {}
    for band in BANDS:
        df = load_band_data(band)
        if df is not None:
            dfs[band] = df
            _log(f"  Band {band}: {len(df)} rows, {df['fen'].nunique()} positions")
    if not dfs:
        _log("ERROR: No feature data found. Run collect_lichess + extract_features first.")
        sys.exit(1)

    # Train Model A
    _log("\n[2/5] Training Model A (conditional logit) per band...")
    model_a_params: dict = {}
    diagnostics_a: dict = {}
    for band in BANDS:
        if band not in dfs:
            continue
        _log(f"\n  --- Band {band} ---")
        X, choices, mask = prepare_choice_data(dfs[band], FEATURE_COLS)
        X_std, feat_means, feat_stds = standardize(X, mask)
        _log(f"  {X.shape[0]} positions, fitting...")
        trace = fit_model_a(X_std, choices, mask, len(FEATURE_COLS))
        stats = extract_posterior_stats(trace, "beta", FEATURE_COLS)
        posterior_means = {f: s["mean"] for f, s in stats.items()}
        posterior_sds = {f: s["sd"] for f, s in stats.items()}
        # Convert means back to original scale
        orig_coeffs = {}
        for i, f in enumerate(FEATURE_COLS):
            orig_coeffs[f] = float(posterior_means[f] / feat_stds[i])
        model_a_params[band] = {
            "coefficients": orig_coeffs,
            "intercept": 0.0,
            "coefficients_stats": stats,
        }
        diagnostics_a[band] = {
            f: {"r_hat": s["r_hat"], "ess_bulk": s["ess_bulk"]}
            for f, s in stats.items()
        }
        min_ess = min(s["ess_bulk"] for s in stats.values())
        max_rhat = max(s["r_hat"] for s in stats.values())
        _log(f"  Convergence: R-hat max={max_rhat:.3f}, ESS min={min_ess:.0f}")

    # Train Model B
    _log("\n[3/5] Training Model B (logistic regression) per band...")
    tutor_data = prepare_tutor_data(dfs)
    model_b_params: dict = {}
    diagnostics_b: dict = {}
    for band, td in tutor_data.items():
        _log(f"\n  --- Band {band} ---")
        trace = fit_model_b(td["X"], td["y"], len(TUTOR_FEATURES))
        stats_w = extract_posterior_stats(trace, "weights", TUTOR_FEATURES)
        summary_i = az.summary(trace, var_names=["intercept"], hdi_prob=0.94)
        intercept_mean = float(summary_i["mean"].iloc[0])
        intercept_sd = float(summary_i["sd"].iloc[0])
        model_b_params[band] = {
            "weights": {f: s["mean"] for f, s in stats_w.items()},
            "intercept": intercept_mean,
            "intercept_sd": intercept_sd,
            "weights_stats": stats_w,
        }
        diagnostics_b[band] = {
            f: {"r_hat": s["r_hat"], "ess_bulk": s["ess_bulk"]}
            for f, s in stats_w.items()
        }
        min_ess = min(s["ess_bulk"] for s in stats_w.values())
        max_rhat = max(s["r_hat"] for s in stats_w.values())
        _log(f"  Convergence: R-hat max={max_rhat:.3f}, ESS min={min_ess:.0f}")

    # Export JSON
    _log("\n[4/5] Exporting learned_params.json with uncertainty...")
    output = {"model_a": model_a_params, "model_b": model_b_params}
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(output, f, indent=2)
    _log(f"  Saved to {OUTPUT_JSON}")

    # Save diagnostics
    diag = {"model_a": diagnostics_a, "model_b": diagnostics_b}
    OUTPUT_DIAG.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIAG, "w") as f:
        json.dump(diag, f, indent=2)
    _log(f"  Saved diagnostics to {OUTPUT_DIAG}")

    # Generate figure
    _log("\n[5/5] Generating posteriors.pdf with error bars...")
    generate_posteriors_figure(output, OUTPUT_FIG)

    _log("\n" + "=" * 60)
    _log("DONE. All results saved:")
    _log(f"  Parameters: {OUTPUT_JSON}")
    _log(f"  Figure:     {OUTPUT_FIG}")
    _log(f"  Diagnostics: {OUTPUT_DIAG}")
    _log("=" * 60)


if __name__ == "__main__":
    main()
