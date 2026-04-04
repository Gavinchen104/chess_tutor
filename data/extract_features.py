"""
Extract feature matrices from collected PGN games for Bayesian model training.

Reads PGN files (output of collect_lichess.py) and replays each game
position-by-position.  At every sampled position the heuristic MoveEngine
evaluates all candidate moves and records which move the human actually
played.  The result is one CSV per ELO band.

Features per candidate move
----------------------------
Continuous:
    eval_gap, difficulty, safety_change, center_change,
    king_safety_change, development_change, mobility_change,
    material_change, opponent_pressure_change,
    tutor_score_heuristic

Discrete / boolean:
    num_preferred_tags, num_tags, num_priorities,
    is_capture, is_check, is_castling

Label:
    is_human_move   (1 if the human played this move, 0 otherwise)

Usage (from chess_tutor/ directory):
    python -m data.extract_features
    python -m data.extract_features --sample-every 2 --max-games 500
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time

import chess
import chess.pgn
import pandas as pd

# Ensure imports work when run from chess_tutor/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.move_engine import MoveEngine
from app.core.levels import LEVELS, LevelProfile

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# ELO bands must match collect_lichess.py
ELO_BANDS = {
    "600":  (400, 800),
    "1000": (850, 1150),
    "1400": (1250, 1550),
    "1800": (1650, 1950),
}

# Default: sample every Nth half-move (to keep runtime reasonable)
DEFAULT_SAMPLE_EVERY = 3

# Maximum candidate moves to consider per position
MAX_CANDIDATES = 10


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def extract_features_for_position(
    engine: MoveEngine,
    board: chess.Board,
    human_move: chess.Move,
    level: LevelProfile,
    fen: str,
) -> list[dict]:
    """
    Compute feature vectors for all candidate moves in a single position,
    labeling the one the human actually played.

    Args:
        engine: MoveEngine instance (heuristic mode).
        board: Current board state BEFORE the human move.
        human_move: The move the human actually played.
        level: Target LevelProfile for this ELO band.
        fen: FEN string of the current position.

    Returns:
        List of feature dicts, one per candidate move.
    """
    try:
        analysis = engine.analyze(board, level)
    except (ValueError, Exception):
        return []

    human_uci = human_move.uci()
    rows: list[dict] = []

    for candidate in analysis.candidates[:MAX_CANDIDATES]:
        delta = candidate.delta
        if delta is None:
            continue

        uci = candidate.move.uci()
        eval_gap = max(0, analysis.best_move.score_cp - candidate.score_cp)
        num_preferred = sum(
            1 for tag in candidate.tags if tag in level.preferred_tags
        )

        rows.append({
            "fen": fen,
            "move_uci": uci,
            "move_san": candidate.san,
            "elo_band": level.key,
            # --- continuous features ---
            "eval_gap": eval_gap,
            "difficulty": round(candidate.difficulty, 4),
            "safety_change": delta.safety_change,
            "center_change": delta.center_control_change,
            "king_safety_change": delta.king_safety_change,
            "development_change": delta.development_change,
            "mobility_change": delta.mobility_change,
            "material_change": delta.material_change_cp,
            "opponent_pressure_change": delta.opponent_king_pressure_change,
            "tutor_score_heuristic": round(candidate.tutor_score, 2),
            # --- discrete / boolean ---
            "num_preferred_tags": num_preferred,
            "num_tags": len(candidate.tags),
            "num_priorities": len(candidate.priorities_addressed),
            "is_capture": int(board.is_capture(candidate.move)),
            "is_check": int(board.gives_check(candidate.move)),
            "is_castling": int(board.is_castling(candidate.move)),
            # --- label ---
            "is_human_move": int(uci == human_uci),
        })

    # If the human move wasn't in the top candidates, add it explicitly
    if human_uci not in {r["move_uci"] for r in rows}:
        try:
            insight = engine.inspect_move(
                board, human_move, level,
                best_score_cp=analysis.best_move.score_cp,
                position_snapshot=analysis.snapshot,
                position_needs=analysis.position_needs,
            )
            delta = insight.delta
            if delta is not None:
                eval_gap = max(0, analysis.best_move.score_cp - insight.score_cp)
                num_preferred = sum(
                    1 for tag in insight.tags if tag in level.preferred_tags
                )
                rows.append({
                    "fen": fen,
                    "move_uci": human_uci,
                    "move_san": insight.san,
                    "elo_band": level.key,
                    "eval_gap": eval_gap,
                    "difficulty": round(insight.difficulty, 4),
                    "safety_change": delta.safety_change,
                    "center_change": delta.center_control_change,
                    "king_safety_change": delta.king_safety_change,
                    "development_change": delta.development_change,
                    "mobility_change": delta.mobility_change,
                    "material_change": delta.material_change_cp,
                    "opponent_pressure_change": delta.opponent_king_pressure_change,
                    "tutor_score_heuristic": round(insight.tutor_score, 2),
                    "num_preferred_tags": num_preferred,
                    "num_tags": len(insight.tags),
                    "num_priorities": len(insight.priorities_addressed),
                    "is_capture": int(board.is_capture(human_move)),
                    "is_check": int(board.gives_check(human_move)),
                    "is_castling": int(board.is_castling(human_move)),
                    "is_human_move": 1,
                })
        except (ValueError, Exception):
            pass

    return rows


# ---------------------------------------------------------------------------
# PGN processing
# ---------------------------------------------------------------------------


def process_pgn_file(
    pgn_path: str,
    level: LevelProfile,
    engine: MoveEngine,
    sample_every: int = DEFAULT_SAMPLE_EVERY,
    max_games: int | None = None,
) -> pd.DataFrame:
    """
    Process all games in a PGN file and extract features.

    Args:
        pgn_path: Path to the PGN file.
        level: LevelProfile for this band.
        engine: MoveEngine instance.
        sample_every: Sample every Nth half-move (to reduce computation).
        max_games: Optional limit on number of games to process.

    Returns:
        DataFrame with feature rows.
    """
    if not os.path.exists(pgn_path):
        print(f"  [WARN] PGN file not found: {pgn_path}")
        return pd.DataFrame()

    all_rows: list[dict] = []
    game_count = 0

    with open(pgn_path) as fh:
        while True:
            game = chess.pgn.read_game(fh)
            if game is None:
                break

            game_count += 1
            if max_games and game_count > max_games:
                break

            board = game.board()
            moves = list(game.mainline_moves())

            for move_idx, move in enumerate(moves):
                # Sample positions to keep runtime manageable
                if move_idx % sample_every != 0:
                    board.push(move)
                    continue

                # Skip trivial positions (game over, very few legal moves)
                if board.is_game_over() or board.legal_moves.count() < 3:
                    board.push(move)
                    continue

                fen = board.fen()
                rows = extract_features_for_position(
                    engine, board, move, level, fen,
                )
                all_rows.extend(rows)

                board.push(move)

            if game_count % 50 == 0:
                print(f"    {game_count} games processed, {len(all_rows)} feature rows")

    return pd.DataFrame(all_rows)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def print_summary(df: pd.DataFrame, band_key: str) -> None:
    """Print summary statistics for a processed band."""
    if df.empty:
        print(f"  Band {band_key}: no data")
        return

    n_positions = df["fen"].nunique()
    n_human = df["is_human_move"].sum()
    n_total = len(df)
    print(f"  Band {band_key}: {n_total} rows, {n_positions} positions, "
          f"{n_human} human moves ({100*n_human/n_total:.1f}%)")

    # Sanity check: human move should exist for most positions
    positions_with_human = df.groupby("fen")["is_human_move"].sum()
    pct_with_human = (positions_with_human > 0).mean() * 100
    print(f"  Positions with human move in candidates: {pct_with_human:.1f}%")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract features from PGN games for Bayesian training",
    )
    parser.add_argument(
        "--input-dir", default="data/processed",
        help="Directory containing games_*.pgn files",
    )
    parser.add_argument(
        "--output-dir", default="data/processed",
        help="Output directory for feature CSVs",
    )
    parser.add_argument(
        "--sample-every", type=int, default=DEFAULT_SAMPLE_EVERY,
        help=f"Sample every Nth half-move (default: {DEFAULT_SAMPLE_EVERY})",
    )
    parser.add_argument(
        "--max-games", type=int, default=None,
        help="Max games per band (default: all)",
    )
    args = parser.parse_args()

    # Force heuristic mode for reproducibility (no Stockfish dependency)
    engine = MoveEngine()
    engine.stockfish_path = None
    print("MoveEngine: heuristic mode (Stockfish disabled for reproducibility)\n")

    os.makedirs(args.output_dir, exist_ok=True)

    for band_key, level in LEVELS.items():
        pgn_path = os.path.join(args.input_dir, f"games_{band_key}.pgn")
        print(f"Processing band {band_key} ({level.label}) ...")
        print(f"  PGN: {pgn_path}")

        if not os.path.exists(pgn_path):
            print(f"  [SKIP] PGN file not found")
            continue

        t0 = time.time()
        df = process_pgn_file(
            pgn_path, level, engine,
            sample_every=args.sample_every,
            max_games=args.max_games,
        )
        elapsed = time.time() - t0

        if df.empty:
            print(f"  No features extracted")
            continue

        out_path = os.path.join(args.output_dir, f"features_{band_key}.csv")
        df.to_csv(out_path, index=False)
        print(f"  Saved {len(df)} rows to {out_path} ({elapsed:.1f}s)")
        print_summary(df, band_key)
        print()

    print("Feature extraction complete!")


if __name__ == "__main__":
    main()
