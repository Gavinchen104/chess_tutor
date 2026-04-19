"""
Automated comparison of tutor recommendations vs engine-best moves.

Samples positions from PGN files, runs ``AnalysisService.analyze_position``
at each of the four ELO bands, and records:

* whether the tutor's recommended move differs from the engine's best move
* how many centipawns the tutor sacrifices
* how much easier (lower difficulty / tactical risk) the tutor move is
* how often the same position yields different recommendations across bands

This gives a quantitative, reproducible answer to the question "does the
tutor actually behave differently from a raw engine, and does that
difference track skill level?" -- without requiring any human raters.

Output: ``analysis/results/tutor_vs_engine.json`` and a Markdown summary
printed to stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chess
import chess.pgn

from app.core.levels import LEVELS
from app.core.services import AnalysisService

DEFAULT_OUTPUT = REPO_ROOT / "analysis" / "results" / "tutor_vs_engine.json"
DEFAULT_PGN_SOURCES = [
    REPO_ROOT / "data" / "benchmarks" / "sample_games.pgn",
    REPO_ROOT / "data" / "benchmarks" / "review_games",
]
DEFAULT_BANDS = ("600", "1000", "1400", "1800")


def iter_pgn_files(sources: list[Path]) -> list[Path]:
    files: list[Path] = []
    for source in sources:
        if not source.exists():
            continue
        if source.is_file() and source.suffix.lower() == ".pgn":
            files.append(source)
        elif source.is_dir():
            files.extend(sorted(source.glob("*.pgn")))
    return files


def sample_positions_from_pgn(
    pgn_path: Path,
    *,
    ply_start: int = 4,
    ply_step: int = 3,
    max_per_game: int = 40,
) -> list[dict]:
    """Return a list of {fen, source, ply} dicts sampled from a PGN file."""
    positions: list[dict] = []
    with pgn_path.open("r", encoding="utf-8") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            board = game.board()
            ply = 0
            taken = 0
            for move in game.mainline_moves():
                board.push(move)
                ply += 1
                if ply < ply_start:
                    continue
                if (ply - ply_start) % ply_step != 0:
                    continue
                if board.is_game_over():
                    break
                if not any(board.legal_moves):
                    break
                positions.append({
                    "fen": board.fen(),
                    "source": pgn_path.name,
                    "ply": ply,
                    "headers": {
                        "event": game.headers.get("Event", ""),
                        "white": game.headers.get("White", ""),
                        "black": game.headers.get("Black", ""),
                    },
                })
                taken += 1
                if taken >= max_per_game:
                    break
    return positions


def dedupe_positions(positions: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for pos in positions:
        if pos["fen"] in seen:
            continue
        seen.add(pos["fen"])
        pos["position_id"] = hashlib.md5(pos["fen"].encode()).hexdigest()[:10]
        out.append(pos)
    return out


def run_comparison(
    positions: list[dict],
    bands: list[str],
) -> list[dict]:
    service = AnalysisService()
    rows: list[dict] = []
    total = len(positions) * len(bands)
    done = 0
    for pos in positions:
        try:
            board = chess.Board(pos["fen"])
        except ValueError:
            continue
        if board.is_game_over():
            continue
        for band in bands:
            done += 1
            level = LEVELS[band]
            try:
                report = service.analyze_position(board, level, candidate_limit=5)
            except Exception as exc:
                rows.append({
                    "position_id": pos["position_id"],
                    "fen": pos["fen"],
                    "source": pos["source"],
                    "band": band,
                    "error": str(exc),
                })
                continue

            engine_best = report.engine_best_move
            tutor = report.tutor_move
            rows.append({
                "position_id": pos["position_id"],
                "fen": pos["fen"],
                "source": pos["source"],
                "ply": pos.get("ply"),
                "band": band,
                "engine_san": engine_best.san,
                "engine_uci": engine_best.uci,
                "engine_score_cp": engine_best.score_cp,
                "engine_difficulty": round(engine_best.difficulty, 3),
                "engine_tactical_risk": round(engine_best.tactical_risk_score, 2),
                "engine_mistake_class": engine_best.mistake_class,
                "tutor_san": tutor.san,
                "tutor_uci": tutor.uci,
                "tutor_score_cp": tutor.score_cp,
                "tutor_eval_gap_cp": tutor.eval_gap_cp,
                "tutor_difficulty": round(tutor.difficulty, 3),
                "tutor_tactical_risk": round(tutor.tactical_risk_score, 2),
                "tutor_mistake_class": tutor.mistake_class,
                "tutor_primary_theme": tutor.primary_theme,
                "tutor_equals_engine": tutor.uci == engine_best.uci,
            })
            print(
                f"  [{done}/{total}] {pos['source']} ply={pos.get('ply')} band={band}: "
                f"engine={engine_best.san} tutor={tutor.san} "
                f"gap={tutor.eval_gap_cp}cp diff_red={engine_best.difficulty - tutor.difficulty:+.2f}"
            )
    return rows


def _valid(rows: list[dict]) -> list[dict]:
    return [row for row in rows if "error" not in row]


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def per_band_aggregates(rows: list[dict], bands: list[str]) -> dict:
    aggregates: dict[str, dict] = {}
    valid = _valid(rows)
    for band in bands:
        band_rows = [row for row in valid if row["band"] == band]
        n = len(band_rows)
        if n == 0:
            aggregates[band] = {"n_positions": 0}
            continue
        differs = [row for row in band_rows if not row["tutor_equals_engine"]]
        gaps = [row["tutor_eval_gap_cp"] for row in band_rows]
        engine_diff = [row["engine_difficulty"] for row in band_rows]
        tutor_diff = [row["tutor_difficulty"] for row in band_rows]
        engine_risk = [row["engine_tactical_risk"] for row in band_rows]
        tutor_risk = [row["tutor_tactical_risk"] for row in band_rows]
        mistake_counter = Counter(row["tutor_mistake_class"] for row in band_rows)
        engine_mistake_counter = Counter(row["engine_mistake_class"] for row in band_rows)
        aggregates[band] = {
            "n_positions": n,
            "pct_tutor_differs_from_engine": _safe_rate(len(differs), n),
            "mean_cp_sacrifice": round(mean(gaps), 2),
            "median_cp_sacrifice": round(median(gaps), 2),
            "mean_cp_sacrifice_when_differs": round(
                mean([row["tutor_eval_gap_cp"] for row in differs]), 2
            ) if differs else 0.0,
            "mean_engine_difficulty": round(mean(engine_diff), 3),
            "mean_tutor_difficulty": round(mean(tutor_diff), 3),
            "mean_difficulty_reduction": round(mean(engine_diff) - mean(tutor_diff), 3),
            "mean_engine_tactical_risk": round(mean(engine_risk), 2),
            "mean_tutor_tactical_risk": round(mean(tutor_risk), 2),
            "mean_tactical_risk_reduction": round(mean(engine_risk) - mean(tutor_risk), 2),
            "tutor_mistake_class_hist": dict(mistake_counter),
            "engine_mistake_class_hist": dict(engine_mistake_counter),
        }
    return aggregates


def cross_band_agreement(rows: list[dict], bands: list[str]) -> dict:
    """For each pair of bands, fraction of positions with same tutor move."""
    valid = _valid(rows)
    by_pos_band: dict[str, dict[str, str]] = {}
    for row in valid:
        by_pos_band.setdefault(row["position_id"], {})[row["band"]] = row["tutor_uci"]

    matrix: dict[str, dict[str, float]] = {}
    for band_a in bands:
        matrix[band_a] = {}
        for band_b in bands:
            same = 0
            total = 0
            for moves in by_pos_band.values():
                if band_a in moves and band_b in moves:
                    total += 1
                    if moves[band_a] == moves[band_b]:
                        same += 1
            matrix[band_a][band_b] = _safe_rate(same, total)
    return matrix


def format_markdown_summary(
    aggregates: dict,
    cross_band: dict,
    bands: list[str],
    n_positions: int,
) -> str:
    lines: list[str] = []
    lines.append(f"# Tutor vs engine summary ({n_positions} positions)\n")
    lines.append("## Per-band metrics\n")
    header = (
        "| Band | n | % tutor ≠ engine | Mean cp sacrifice | Mean cp when ≠ | "
        "Engine difficulty | Tutor difficulty | Δ difficulty | "
        "Engine tact. risk | Tutor tact. risk |"
    )
    sep = "|------|---|-----------------|-------------------|----------------|"
    sep += "-------------------|------------------|--------------|-------------------|------------------|"
    lines.append(header)
    lines.append(sep)
    for band in bands:
        stats = aggregates.get(band, {})
        if stats.get("n_positions", 0) == 0:
            lines.append(f"| {band} | 0 | — | — | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {band} "
            f"| {stats['n_positions']} "
            f"| {stats['pct_tutor_differs_from_engine'] * 100:.1f}% "
            f"| {stats['mean_cp_sacrifice']:.1f} "
            f"| {stats['mean_cp_sacrifice_when_differs']:.1f} "
            f"| {stats['mean_engine_difficulty']:.2f} "
            f"| {stats['mean_tutor_difficulty']:.2f} "
            f"| {stats['mean_difficulty_reduction']:+.2f} "
            f"| {stats['mean_engine_tactical_risk']:.1f} "
            f"| {stats['mean_tutor_tactical_risk']:.1f} |"
        )

    lines.append("\n## Cross-band agreement on tutor move\n")
    lines.append("Fraction of shared positions where bands pick the same tutor move.\n")
    header2 = "| | " + " | ".join(bands) + " |"
    sep2 = "|---|" + "---|" * len(bands)
    lines.append(header2)
    lines.append(sep2)
    for band_a in bands:
        row = [band_a]
        for band_b in bands:
            row.append(f"{cross_band[band_a][band_b] * 100:.1f}%")
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pgn",
        type=Path,
        action="append",
        help="PGN file or directory to sample from (repeatable). "
             "Defaults to data/benchmarks/sample_games.pgn plus review_games/.",
    )
    parser.add_argument(
        "--max-positions",
        type=int,
        default=60,
        help="Cap on the total number of unique positions sampled.",
    )
    parser.add_argument(
        "--ply-start",
        type=int,
        default=4,
        help="First ply (inclusive) to sample from each game.",
    )
    parser.add_argument(
        "--ply-step",
        type=int,
        default=3,
        help="Sample every N-th half-move.",
    )
    parser.add_argument(
        "--bands",
        nargs="+",
        default=list(DEFAULT_BANDS),
        help="ELO bands to include.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON output path.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path to also save the Markdown summary.",
    )
    args = parser.parse_args()

    sources = args.pgn if args.pgn else DEFAULT_PGN_SOURCES
    pgn_files = iter_pgn_files([Path(s) for s in sources])
    if not pgn_files:
        print("No PGN files found in the given sources.")
        return 1

    all_positions: list[dict] = []
    for pgn_path in pgn_files:
        all_positions.extend(
            sample_positions_from_pgn(
                pgn_path,
                ply_start=args.ply_start,
                ply_step=args.ply_step,
            )
        )
    positions = dedupe_positions(all_positions)[: args.max_positions]
    if not positions:
        print("No positions extracted from PGN sources.")
        return 1

    print(
        f"Running comparison on {len(positions)} positions "
        f"across bands {args.bands} "
        f"from {len(pgn_files)} PGN file(s)."
    )
    rows = run_comparison(positions, args.bands)

    aggregates = per_band_aggregates(rows, args.bands)
    cross = cross_band_agreement(rows, args.bands)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "n_positions": len(positions),
        "bands": args.bands,
        "per_band": aggregates,
        "cross_band_agreement": cross,
        "rows": rows,
        "sources": [str(p) for p in pgn_files],
    }
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    summary = format_markdown_summary(aggregates, cross, args.bands, len(positions))
    print("\n" + summary)

    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(summary, encoding="utf-8")
        print(f"Markdown summary saved to {args.markdown_output}")

    print(f"Full JSON payload saved to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
