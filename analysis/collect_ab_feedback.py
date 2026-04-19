"""
Head-to-head comparison study: tutor recommendation vs raw engine output.

For each benchmark position the rater sees two blinded presentations:

  Advice A: <engine-style or tutor-style, randomized>
  Advice B: <the other one>

and answers three preference questions plus an optional one-line reason.

This directly addresses the project-brief requirement to collect qualitative
and anecdotal evidence that the tutor is more user friendly / useful than
simply using a chess engine.

Output is appended to ``analysis/results/ab_feedback.jsonl`` with:

* rater_id, position, level
* which side (A/B) was tutor and which was engine
* three preference labels (tutor / engine / tied)
* optional one-line reason
* tutor and engine moves captured for later audit
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chess

from app.core.levels import LEVELS
from app.core.services import AnalysisService

DEFAULT_POSITIONS_PATH = REPO_ROOT / "data" / "benchmarks" / "positions_v2.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "analysis" / "results" / "ab_feedback.jsonl"

QUESTIONS = [
    (
        "clearer",
        "Which advice is CLEARER to read (easier to understand)? [A/B/tied]: ",
    ),
    (
        "more_useful",
        "Which advice would you ACTUALLY FOLLOW as a player at this level? [A/B/tied]: ",
    ),
    (
        "less_overwhelming",
        "Which advice feels LESS OVERWHELMING? [A/B/tied]: ",
    ),
]

VALID_ANSWERS = {"a", "b", "tied", "t"}


def load_positions(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected list in {path}")
    return data


def already_rated_labels(rater: str, feedback_path: Path) -> set[str]:
    if not feedback_path.exists():
        return set()
    labels: set[str] = set()
    with feedback_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if str(entry.get("rater_id", "")).strip().lower() == rater.strip().lower():
                labels.add(str(entry.get("position_label", "")))
    return labels


def render_board(board: chess.Board) -> str:
    try:
        return board.unicode(borders=True, empty_square=".")
    except Exception:
        return str(board)


def render_engine_view(report) -> str:
    """Raw engine-style output: best move + cp eval + top alternatives."""
    lines = []
    engine_best = report.engine_best_move
    lines.append(f"  Best move : {engine_best.san}   (eval {engine_best.score_cp / 100:+.2f})")
    alternatives = [c for c in report.candidate_moves if c.uci != engine_best.uci][:3]
    if alternatives:
        lines.append("  Alternatives (by engine score):")
        for cand in alternatives:
            lines.append(f"    {cand.san:8s}  eval {cand.score_cp / 100:+.2f}   (gap {cand.eval_gap_cp} cp)")
    lines.append("  (Raw engine output — no commentary.)")
    return "\n".join(lines)


def render_tutor_view(report) -> str:
    """Tutor-style output adapted by ELO level."""
    lines = []
    tutor = report.tutor_move
    level_key = int(report.level_key)
    engine_best = report.engine_best_move

    lines.append(f"  Recommended move: {tutor.san}")

    if tutor.player_friendly_explanation:
        lines.append(f"  {tutor.player_friendly_explanation.strip()}")

    if level_key >= 1400:
        if tutor.uci != engine_best.uci:
            lines.append(
                f"  Note: the engine prefers {engine_best.san} "
                f"(eval {engine_best.score_cp / 100:+.2f}), but {tutor.san} "
                f"is recommended because it is more practical at this level."
            )
        alternatives = [
            c for c in report.candidate_moves
            if c.uci != tutor.uci
        ][:2]
        if alternatives:
            lines.append("  Other options considered:")
            for cand in alternatives:
                gap = abs(cand.score_cp - tutor.score_cp)
                comparison = "similar strength" if gap < 30 else f"{gap} cp weaker"
                lines.append(f"    {cand.san} ({comparison}) — {cand.primary_theme.replace('_', ' ')}")

    return "\n".join(lines)


def render_position(case: dict, report, assignment: dict[str, str]) -> None:
    label = case.get("label", "unlabeled")
    level_key = case.get("level_key", "?")
    board = chess.Board(case["fen"])

    print("\n" + "=" * 72)
    print(f"  Position: {label}    Target ELO band: {level_key}")
    print("=" * 72)
    print(render_board(board))
    print(f"  Side to move: {'White' if board.turn else 'Black'}")
    print(f"  FEN: {board.fen()}")
    print("-" * 72)

    if assignment["A"] == "engine":
        view_a, view_b = render_engine_view(report), render_tutor_view(report)
    else:
        view_a, view_b = render_tutor_view(report), render_engine_view(report)

    print("  Advice A:")
    print(view_a)
    print("\n  Advice B:")
    print(view_b)
    print("-" * 72)


def prompt_preference(field: str, prompt: str) -> str | None:
    while True:
        raw = input(prompt).strip().lower()
        if raw in {"s", "skip"}:
            return None
        if raw in {"q", "quit", "exit"}:
            raise KeyboardInterrupt
        if raw in {"a", "b"}:
            return raw
        if raw in {"tied", "t", "="}:
            return "tied"
        print("  -> please answer 'a', 'b', or 'tied' (or 's' skip / 'q' quit).")


def preference_to_side(answer: str, assignment: dict[str, str]) -> str:
    """Convert A/B answer + assignment mapping to 'tutor' / 'engine' / 'tied'."""
    if answer == "tied":
        return "tied"
    return assignment[answer.upper()]


def collect_one(case: dict, rater: str, report, rng: random.Random) -> dict | None:
    # Randomize which side is tutor
    tutor_on_left = rng.random() < 0.5
    assignment = {
        "A": "tutor" if tutor_on_left else "engine",
        "B": "engine" if tutor_on_left else "tutor",
    }

    render_position(case, report, assignment)

    preferences: dict[str, str] = {}
    for field, prompt in QUESTIONS:
        answer = prompt_preference(field, prompt)
        if answer is None:
            print("  -> skipped.\n")
            return None
        preferences[field] = preference_to_side(answer, assignment)

    reason = input("One-line reason for your choices (Enter to skip): ").strip()

    # Reveal un-blinding for the rater's context
    print(f"\n  (After answers: A was {assignment['A']}, B was {assignment['B']}.)")

    entry = {
        "rater_id": rater,
        "position_label": case.get("label", ""),
        "level_key": case.get("level_key", ""),
        "theme": case.get("theme", ""),
        "fen": case["fen"],
        "assignment": assignment,
        "tutor_move_san": report.tutor_move.san,
        "engine_best_san": report.engine_best_move.san,
        "tutor_equals_engine": report.tutor_move.uci == report.engine_best_move.uci,
        "preferences": preferences,
        "reason": reason,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    return entry


def append_entry(entry: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")


def load_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def summarize(path: Path) -> dict:
    entries = load_entries(path)
    summary = {
        "n_comparisons": len(entries),
        "n_raters": len({str(e.get("rater_id", "?")) for e in entries}),
        "raters": sorted({str(e.get("rater_id", "?")) for e in entries}),
        "by_level": {},
        "preference_pct": {
            "clearer": {"tutor": 0, "engine": 0, "tied": 0},
            "more_useful": {"tutor": 0, "engine": 0, "tied": 0},
            "less_overwhelming": {"tutor": 0, "engine": 0, "tied": 0},
        },
        "sample_quotes": [],
    }
    if not entries:
        return summary

    level_counts: dict[str, int] = {}
    for entry in entries:
        level_key = str(entry.get("level_key", "?"))
        level_counts[level_key] = level_counts.get(level_key, 0) + 1
    summary["by_level"] = level_counts

    counts = {field: {"tutor": 0, "engine": 0, "tied": 0} for field, _ in QUESTIONS}
    for entry in entries:
        prefs = entry.get("preferences", {})
        for field, _ in QUESTIONS:
            side = prefs.get(field)
            if side in counts[field]:
                counts[field][side] += 1
    total = len(entries)
    for field in counts:
        summary["preference_pct"][field] = {
            key: round(value / total * 100, 1) for key, value in counts[field].items()
        }

    quotes = []
    for entry in entries:
        reason = str(entry.get("reason", "")).strip()
        if reason:
            quotes.append({
                "rater": entry.get("rater_id", ""),
                "level": entry.get("level_key", ""),
                "position": entry.get("position_label", ""),
                "reason": reason,
            })
    summary["sample_quotes"] = quotes[-6:]
    return summary


def print_summary(path: Path) -> None:
    s = summarize(path)
    print("\n" + "=" * 72)
    print("  A/B feedback summary")
    print("=" * 72)
    print(f"  File         : {path}")
    print(f"  Comparisons  : {s['n_comparisons']}")
    print(f"  Unique raters: {s['n_raters']}  ({', '.join(s['raters']) if s['raters'] else '-'})")
    print(f"  By level     : {s['by_level']}")
    if s["n_comparisons"] > 0:
        print("  Preference distribution (% of comparisons):")
        for field, _ in QUESTIONS:
            dist = s["preference_pct"][field]
            print(
                f"    {field:20s} tutor {dist['tutor']:5.1f}%   "
                f"engine {dist['engine']:5.1f}%   tied {dist['tied']:5.1f}%"
            )
    if s["sample_quotes"]:
        print("  Recent one-line reasons:")
        for quote in s["sample_quotes"]:
            print(f"    [{quote['level']} / {quote['position']}] {quote['rater']}: {quote['reason']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rater",
        default=os.environ.get("USER") or "anon",
        help="Your rater id (e.g., yuhang).",
    )
    parser.add_argument(
        "--positions",
        type=Path,
        default=DEFAULT_POSITIONS_PATH,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Optional cap on the number of comparisons.",
    )
    parser.add_argument(
        "--redo",
        action="store_true",
        help="Also re-rate positions this rater already scored.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional RNG seed for reproducible A/B ordering.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print summary without prompting.",
    )
    args = parser.parse_args()

    if args.summary_only:
        print_summary(args.output)
        return 0

    positions = load_positions(args.positions)
    done = set() if args.redo else already_rated_labels(args.rater, args.output)
    queue = [case for case in positions if case.get("label", "") not in done]
    if args.max is not None:
        queue = queue[: args.max]

    if not queue:
        print(f"No unseen positions for rater '{args.rater}'.")
        print_summary(args.output)
        return 0

    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    print(f"Rater: {args.rater}   Pending comparisons: {len(queue)}")
    print("For each question, type 'a', 'b', or 'tied'. 's' skips a position, 'q' quits.\n")

    service = AnalysisService()
    saved = 0
    try:
        for case in queue:
            board = chess.Board(case["fen"])
            level = LEVELS[case["level_key"]]
            report = service.analyze_position(board, level, candidate_limit=5)
            entry = collect_one(case, args.rater, report, rng)
            if entry is None:
                continue
            append_entry(entry, args.output)
            saved += 1
            print(f"  -> saved ({saved} this session).\n")
    except KeyboardInterrupt:
        print("\nInterrupted. Saving session and exiting.")

    print(f"\nSession recorded {saved} comparisons from {args.rater}.")
    print_summary(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
