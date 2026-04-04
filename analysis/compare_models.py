"""
Compare learned Bayesian model vs heuristic baseline.

Runs both scoring systems on benchmark positions and held-out games,
producing quantitative metrics and qualitative case studies.

Usage (from chess_tutor/ directory):
    python analysis/compare_models.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chess
import chess.pgn

from app.core.move_engine import (
    MoveEngine,
    MoveDelta,
    build_position_snapshot,
    build_move_delta,
    describe_move_features,
    identify_position_needs,
    estimate_difficulty,
)
from app.core.levels import LEVELS, LevelProfile
from app.core.learned_params import learned_params


# ---------------------------------------------------------------------------
# Heuristic tutor score (original hardcoded formula, for comparison)
# ---------------------------------------------------------------------------


def heuristic_tutor_score(
    score_cp: int,
    best_score_cp: int,
    level: LevelProfile,
    tags: list[str],
    difficulty: float,
    priorities_addressed: list[str],
    delta: MoveDelta,
) -> float:
    """Original hardcoded tutor score — always uses heuristic weights."""
    eval_gap = max(0, best_score_cp - score_cp)
    eval_credit = max(0.0, 150.0 - float(eval_gap))
    preferred_bonus = sum(8.0 for tag in tags if tag in level.preferred_tags)
    priority_bonus = 12.0 * len(priorities_addressed)
    safety_bonus = max(0.0, delta.safety_change / 12.0)
    king_safety_bonus = max(0.0, delta.king_safety_change * 1.8)
    center_bonus = max(0.0, delta.center_control_change / 6.0)
    pressure_bonus = max(0.0, delta.opponent_king_pressure_change)
    complexity_penalty = difficulty * level.complexity_weight
    tactical_risk_penalty = max(0.0, -delta.safety_change / 8.0)
    king_risk_penalty = max(0.0, -delta.king_safety_change * 3.0)
    return (
        eval_credit + preferred_bonus + priority_bonus + safety_bonus
        + king_safety_bonus + center_bonus + pressure_bonus
        - complexity_penalty - tactical_risk_penalty - king_risk_penalty
    )


# ---------------------------------------------------------------------------
# Benchmark comparison
# ---------------------------------------------------------------------------


def compare_on_benchmarks(engine: MoveEngine) -> dict:
    """
    Compare model vs heuristic on the 15 benchmark positions.

    Returns a summary dict with per-position results.
    """
    bench_path = REPO_ROOT / "data" / "benchmarks" / "positions.json"
    with open(bench_path) as fh:
        benchmarks = json.load(fh)

    results = []
    for entry in benchmarks:
        fen = entry["fen"]
        level_key = entry.get("level_key", "1000")
        level = LEVELS.get(level_key, LEVELS["1000"])
        board = chess.Board(fen)

        analysis = engine.analyze(board, level)
        tutor_move = analysis.tutor_move

        # Recompute with heuristic weights
        heuristic_scores = {}
        for c in analysis.candidates:
            if c.delta is None:
                continue
            h_score = heuristic_tutor_score(
                c.score_cp, analysis.best_move.score_cp, level,
                c.tags, c.difficulty, c.priorities_addressed, c.delta,
            )
            heuristic_scores[c.san] = h_score

        heuristic_best = max(heuristic_scores, key=heuristic_scores.get) if heuristic_scores else "?"

        results.append({
            "fen": fen,
            "level": level_key,
            "engine_best": analysis.best_move.san,
            "learned_tutor": tutor_move.san,
            "heuristic_tutor": heuristic_best,
            "agree": tutor_move.san == heuristic_best,
            "learned_score": round(tutor_move.tutor_score, 1),
            "heuristic_score": round(heuristic_scores.get(tutor_move.san, 0), 1),
        })

    agree_pct = sum(1 for r in results if r["agree"]) / len(results) * 100
    return {
        "positions": results,
        "agreement_pct": round(agree_pct, 1),
        "total_positions": len(results),
    }


# ---------------------------------------------------------------------------
# Held-out game comparison
# ---------------------------------------------------------------------------


def compare_on_heldout_games(engine: MoveEngine) -> dict:
    """
    On held-out positions from collected games, compare how well each model's
    top recommendation matches what the human actually played.
    """
    results_by_band = {}

    for band_key in ["600", "1000", "1400", "1800"]:
        csv_path = REPO_ROOT / "data" / "processed" / f"features_{band_key}.csv"
        if not csv_path.exists():
            continue

        df = pd.read_csv(csv_path)
        level = LEVELS[band_key]
        positions = df.groupby("fen")

        learned_hits = 0
        heuristic_hits = 0
        total_positions = 0

        for fen, group in positions:
            if group["is_human_move"].sum() != 1:
                continue
            human_uci = group.loc[group["is_human_move"] == 1, "move_uci"].values[0]

            board = chess.Board(fen)
            if board.is_game_over():
                continue

            try:
                analysis = engine.analyze(board, level)
            except (ValueError, Exception):
                continue

            total_positions += 1

            # Learned model recommendation (current tutor_move)
            if analysis.tutor_move.move.uci() == human_uci:
                learned_hits += 1

            # Heuristic recommendation
            heuristic_scores = {}
            for c in analysis.candidates:
                if c.delta is None:
                    continue
                h = heuristic_tutor_score(
                    c.score_cp, analysis.best_move.score_cp, level,
                    c.tags, c.difficulty, c.priorities_addressed, c.delta,
                )
                heuristic_scores[c.move.uci()] = h

            if heuristic_scores:
                heuristic_top = max(heuristic_scores, key=heuristic_scores.get)
                if heuristic_top == human_uci:
                    heuristic_hits += 1

            if total_positions >= 300:
                break

        if total_positions > 0:
            results_by_band[band_key] = {
                "total": total_positions,
                "learned_match_rate": round(learned_hits / total_positions * 100, 1),
                "heuristic_match_rate": round(heuristic_hits / total_positions * 100, 1),
            }

    return results_by_band


# ---------------------------------------------------------------------------
# Case studies
# ---------------------------------------------------------------------------


def generate_case_studies(engine: MoveEngine, n_cases: int = 5) -> list[dict]:
    """
    Find positions where learned and heuristic models disagree, producing
    interesting case studies for the report.
    """
    bench_path = REPO_ROOT / "data" / "benchmarks" / "positions.json"
    with open(bench_path) as fh:
        benchmarks = json.load(fh)

    cases = []
    for entry in benchmarks:
        if len(cases) >= n_cases:
            break

        fen = entry["fen"]
        level_key = entry.get("level_key", "1000")
        level = LEVELS.get(level_key, LEVELS["1000"])
        board = chess.Board(fen)

        analysis = engine.analyze(board, level)

        # Find heuristic best
        heuristic_scores = {}
        for c in analysis.candidates:
            if c.delta is None:
                continue
            h = heuristic_tutor_score(
                c.score_cp, analysis.best_move.score_cp, level,
                c.tags, c.difficulty, c.priorities_addressed, c.delta,
            )
            heuristic_scores[c.san] = h

        if not heuristic_scores:
            continue

        heuristic_best_san = max(heuristic_scores, key=heuristic_scores.get)
        learned_best_san = analysis.tutor_move.san

        cases.append({
            "fen": fen,
            "level": level_key,
            "engine_best": analysis.best_move.san,
            "learned_recommends": learned_best_san,
            "learned_score": round(analysis.tutor_move.tutor_score, 1),
            "heuristic_recommends": heuristic_best_san,
            "heuristic_score": round(heuristic_scores[heuristic_best_san], 1),
            "tags": analysis.tutor_move.tags,
            "reasons": analysis.tutor_move.reasons[:2],
            "agrees_with_heuristic": learned_best_san == heuristic_best_san,
        })

    return cases


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    engine = MoveEngine()
    engine.stockfish_path = None
    using_learned = learned_params.is_available()

    print("=" * 60)
    print("Chess Tutor: Learned Model vs Heuristic Comparison")
    print("=" * 60)
    print(f"Using learned parameters: {using_learned}")

    # 1. Benchmark comparison
    print("\n--- Benchmark Positions ---")
    bench = compare_on_benchmarks(engine)
    print(f"Agreement between learned and heuristic: {bench['agreement_pct']}%")
    print(f"Total positions: {bench['total_positions']}")
    for r in bench["positions"]:
        marker = "=" if r["agree"] else "!"
        print(f"  [{marker}] {r['level']:>4s} | engine: {r['engine_best']:>6s} | "
              f"learned: {r['learned_tutor']:>6s} ({r['learned_score']:>6.1f}) | "
              f"heuristic: {r['heuristic_tutor']:>6s} ({r['heuristic_score']:>6.1f})")

    # 2. Held-out game comparison
    print("\n--- Held-out Game Positions ---")
    heldout = compare_on_heldout_games(engine)
    for band, stats in heldout.items():
        print(f"  Band {band}: learned={stats['learned_match_rate']}% vs "
              f"heuristic={stats['heuristic_match_rate']}% "
              f"(n={stats['total']})")

    # 3. Case studies
    print("\n--- Case Studies ---")
    cases = generate_case_studies(engine)
    for i, case in enumerate(cases, 1):
        print(f"\n  Case {i}: ELO {case['level']}")
        print(f"    Engine best:        {case['engine_best']}")
        print(f"    Learned recommends: {case['learned_recommends']} "
              f"(score={case['learned_score']})")
        print(f"    Heuristic recommends: {case['heuristic_recommends']} "
              f"(score={case['heuristic_score']})")
        print(f"    Tags: {', '.join(case['tags'])}")
        if case['reasons']:
            print(f"    Reason: {case['reasons'][0]}")

    # Save full results
    output = {
        "using_learned_params": using_learned,
        "benchmarks": bench,
        "heldout": heldout,
        "case_studies": cases,
    }
    output_path = REPO_ROOT / "data" / "processed" / "comparison_results.json"
    with open(output_path, "w") as fh:
        json.dump(output, fh, indent=2)
    print(f"\nFull results saved to {output_path}")


if __name__ == "__main__":
    main()
