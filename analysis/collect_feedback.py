"""
Interactive CLI to collect qualitative feedback on tutor recommendations.

Each annotator runs:
    python analysis/collect_feedback.py --rater <your_name>

For every benchmark position, the script prints the board, the tutor's
recommendation, the engine's best move, and the tutor's natural-language
explanation, then prompts for four 1-5 Likert ratings and an optional note.

Output is appended to ``analysis/results/user_feedback.jsonl`` using the
schema defined in ``analysis/user_feedback.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chess

from analysis.user_feedback import (
    DEFAULT_FEEDBACK_PATH,
    FEEDBACK_FIELDS,
    append_feedback_entry,
    load_feedback_entries,
    summarize_feedback,
)
from app.core.levels import LEVELS
from app.core.services import AnalysisService

DEFAULT_POSITIONS_PATH = REPO_ROOT / "data" / "benchmarks" / "positions_v2.json"

RATING_PROMPTS = {
    "clarity": "Clarity of the explanation (1=confusing, 5=crystal clear): ",
    "usefulness": "Usefulness for a player at this level (1=useless, 5=very useful): ",
    "actionability": "Would you actually play/practice this (1=no way, 5=definitely): ",
    "overwhelm_reduction": "Feels manageable, not overwhelming (1=overwhelming, 5=very manageable): ",
}


def load_positions(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected list in {path}, got {type(data).__name__}")
    return data


def already_rated_labels(rater: str, feedback_path: Path) -> set[str]:
    """Return the set of position labels the given rater has already scored."""
    entries = load_feedback_entries(feedback_path)
    return {
        str(entry.get("position_label", ""))
        for entry in entries
        if str(entry.get("rater_id", "")).strip().lower() == rater.strip().lower()
    }


def render_board(board: chess.Board) -> str:
    try:
        return board.unicode(borders=True, empty_square=".")
    except Exception:
        return str(board)


def render_position(
    case: dict,
    report,
) -> None:
    label = case.get("label", "unlabeled")
    level_key = case.get("level_key", "?")
    theme = case.get("theme", "?")
    notes = case.get("notes", "")
    board = chess.Board(case["fen"])

    print("\n" + "=" * 70)
    print(f"  Position: {label}")
    print(f"  Target ELO band: {level_key}    Theme: {theme}")
    if notes:
        print(f"  Context: {notes}")
    print("=" * 70)
    print(render_board(board))
    print(f"  Side to move: {'White' if board.turn else 'Black'}")
    print(f"  FEN: {board.fen()}")
    print("-" * 70)

    engine_best = report.engine_best_move
    tutor = report.tutor_move
    agree = tutor.uci == engine_best.uci

    print(f"  Engine best : {engine_best.san}  (score {engine_best.score_cp:+d} cp)")
    print(
        f"  Tutor pick  : {tutor.san}  (score {tutor.score_cp:+d} cp, "
        f"gap {tutor.eval_gap_cp} cp, difficulty {tutor.difficulty:.2f}, "
        f"tactical_risk {tutor.tactical_risk_score:.1f}, "
        f"mistake_class {tutor.mistake_class})"
    )
    print(f"  Agreement   : {'same move' if agree else 'DIFFERS from engine best'}")
    print(f"  Primary theme: {tutor.primary_theme}")
    print("-" * 70)
    if report.tutor_explanation:
        print("  Tutor explanation:")
        print("    " + report.tutor_explanation.strip())
    if tutor.player_friendly_explanation:
        print("  Player-facing rationale:")
        print("    " + tutor.player_friendly_explanation.strip())
    if tutor.training_habit:
        print(f"  Training habit: {tutor.training_habit.strip()}")
    print("-" * 70)


def prompt_rating(field: str) -> int | None:
    while True:
        raw = input(RATING_PROMPTS[field]).strip().lower()
        if raw in {"s", "skip"}:
            return None
        if raw in {"q", "quit", "exit"}:
            raise KeyboardInterrupt
        if raw in {"1", "2", "3", "4", "5"}:
            return int(raw)
        print("  -> please type 1-5, or 's' to skip this position, 'q' to quit.")


def collect_one(case: dict, rater: str, report) -> dict | None:
    """Prompt user for ratings on a single case; return None if skipped."""
    render_position(case, report)
    ratings: dict[str, int] = {}
    for field in FEEDBACK_FIELDS:
        value = prompt_rating(field)
        if value is None:
            print("  -> skipped.\n")
            return None
        ratings[field] = value

    note = input("One-line comment (Enter to skip): ").strip()

    engine_best = report.engine_best_move
    tutor = report.tutor_move
    entry: dict = {
        "rater_id": rater,
        "position_label": case.get("label", ""),
        "level_key": case.get("level_key", ""),
        "theme": case.get("theme", ""),
        "fen": case["fen"],
        "tutor_move_san": tutor.san,
        "tutor_move_uci": tutor.uci,
        "engine_best_san": engine_best.san,
        "engine_best_uci": engine_best.uci,
        "tutor_equals_engine": tutor.uci == engine_best.uci,
        "tutor_eval_gap_cp": tutor.eval_gap_cp,
        "tutor_difficulty": round(tutor.difficulty, 3),
        "tutor_tactical_risk": round(tutor.tactical_risk_score, 2),
        "tutor_mistake_class": tutor.mistake_class,
        "tutor_primary_theme": tutor.primary_theme,
        "notes": note,
    }
    entry.update(ratings)
    return entry


def print_summary(feedback_path: Path) -> None:
    entries = load_feedback_entries(feedback_path)
    summary = summarize_feedback(entries)
    raters = sorted({str(e.get("rater_id", "unknown")) for e in entries})

    print("\n" + "=" * 70)
    print("  Feedback log summary")
    print("=" * 70)
    print(f"  File           : {feedback_path}")
    print(f"  Total ratings  : {summary['count']}")
    print(f"  Unique raters  : {len(raters)}  ({', '.join(raters) if raters else '-'})")
    print(f"  By level       : {summary['by_level']}")
    if summary["averages"]:
        print("  Aggregate means (1-5 scale):")
        for field, value in summary["averages"].items():
            print(f"    {field:25s} {value:.2f}")
    if summary["recent_notes"]:
        print("  Recent notes:")
        for note in summary["recent_notes"]:
            note_text = note["notes"].strip().replace("\n", " ")
            print(f"    [{note.get('level_key', '?')}] {note_text}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rater",
        default=os.environ.get("USER") or "anon",
        help="Your annotator id (e.g., yuhang). Required for de-duplication.",
    )
    parser.add_argument(
        "--positions",
        type=Path,
        default=DEFAULT_POSITIONS_PATH,
        help="Path to benchmark positions JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_FEEDBACK_PATH,
        help="Path to user_feedback.jsonl.",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Optional cap on the number of positions shown.",
    )
    parser.add_argument(
        "--redo",
        action="store_true",
        help="Also show positions this rater has already scored.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print the aggregate summary without prompting.",
    )
    args = parser.parse_args()

    if args.summary_only:
        print_summary(args.output)
        return 0

    positions = load_positions(args.positions)
    already_done = set() if args.redo else already_rated_labels(args.rater, args.output)
    queue = [case for case in positions if case.get("label", "") not in already_done]
    if args.max is not None:
        queue = queue[: args.max]

    if not queue:
        print(f"No unseen positions for rater '{args.rater}'. "
              f"Use --redo to revisit or --summary-only to view the log.")
        print_summary(args.output)
        return 0

    print(f"Rater: {args.rater}   Pending positions: {len(queue)}")
    print("Commands: '1'-'5' rate | 's' skip position | 'q' quit now\n")
    print(f"Session started {datetime.now(timezone.utc).isoformat()}")

    service = AnalysisService()
    collected = 0
    try:
        for case in queue:
            board = chess.Board(case["fen"])
            level = LEVELS[case["level_key"]]
            report = service.analyze_position(board, level, candidate_limit=5)
            entry = collect_one(case, args.rater, report)
            if entry is None:
                continue
            append_feedback_entry(entry, args.output)
            collected += 1
            print(f"  -> saved ({collected} this session).\n")
    except KeyboardInterrupt:
        print("\nInterrupted. Saving session and exiting.")

    print(f"\nSession recorded {collected} ratings from {args.rater}.")
    print_summary(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
