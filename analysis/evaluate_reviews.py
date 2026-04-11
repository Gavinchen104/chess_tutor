from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chess

from app.core.levels import LEVELS
from app.core.services import ReviewService
from analysis.eval_utils import load_json, normalize_text, safe_rate, text_mentions_theme


DEFAULT_REVIEW_CASES_PATH = REPO_ROOT / "data" / "benchmarks" / "review_cases.json"
COLOR_MAP = {
    "white": chess.WHITE,
    "black": chess.BLACK,
}


def weakness_detection_pass(review, expected_themes: list[str]) -> bool:
    searchable_text = normalize_text(
        review.recurring_patterns + review.critical_moments + [review.summary]
    )
    return any(text_mentions_theme(searchable_text, theme) for theme in expected_themes)


def next_step_actionability_pass(review, expected_keywords: list[str]) -> bool:
    if not review.next_steps:
        return False
    next_steps_text = normalize_text(review.next_steps)
    return any(keyword.lower() in next_steps_text for keyword in expected_keywords)


def annotation_consistency_pass(review, expected_themes: list[str]) -> bool:
    observed_themes = {move.primary_theme for move in review.annotated_moves}
    return any(theme in observed_themes for theme in expected_themes)


def evaluate_reviews(cases_path: Path = DEFAULT_REVIEW_CASES_PATH) -> dict:
    review_cases = load_json(cases_path)
    review_service = ReviewService()

    weakness_detection_count = 0
    next_step_actionability_count = 0
    annotation_consistency_count = 0
    benchmark_pass_count = 0

    case_results: list[dict] = []

    for case in review_cases:
        label = case["label"]
        try:
            pgn_path = REPO_ROOT / case["pgn_path"]
            pgn_text = pgn_path.read_text(encoding="utf-8")
            level = LEVELS[case["level_key"]]
            player_color = COLOR_MAP[case["player_color"].lower()]

            review = review_service.review_pgn(
                pgn_text,
                level,
                player_color=player_color,
            )

            weakness_ok = weakness_detection_pass(review, case["expected_weakness_themes"])
            next_steps_ok = next_step_actionability_pass(review, case["expected_next_step_keywords"])
            annotation_ok = annotation_consistency_pass(review, case["expected_weakness_themes"])

            passed = weakness_ok and next_steps_ok and annotation_ok

            weakness_detection_count += int(weakness_ok)
            next_step_actionability_count += int(next_steps_ok)
            annotation_consistency_count += int(annotation_ok)
            benchmark_pass_count += int(passed)

            case_results.append(
                {
                    "label": label,
                    "passed": passed,
                    "level_key": case["level_key"],
                    "player_color": case["player_color"],
                    "expected_weakness_themes": case["expected_weakness_themes"],
                    "expected_next_step_keywords": case["expected_next_step_keywords"],
                    "weakness_detection_pass": weakness_ok,
                    "next_step_actionability_pass": next_steps_ok,
                    "annotation_consistency_pass": annotation_ok,
                    "annotated_move_count": len(review.annotated_moves),
                    "annotated_themes": sorted({move.primary_theme for move in review.annotated_moves}),
                    "recurring_patterns": review.recurring_patterns,
                    "critical_moments": review.critical_moments,
                    "next_steps": review.next_steps,
                    "summary": review.summary,
                    "notes": case.get("notes", ""),
                }
            )

        except Exception as exc:
            case_results.append(
                {
                    "label": label,
                    "passed": False,
                    "error": str(exc),
                    "notes": case.get("notes", ""),
                }
            )

    metrics = {
        "weakness_detection_rate": safe_rate(weakness_detection_count, len(review_cases)),
        "next_step_actionability_rate": safe_rate(next_step_actionability_count, len(review_cases)),
        "annotation_consistency_rate": safe_rate(annotation_consistency_count, len(review_cases)),
        "benchmark_pass_rate": safe_rate(benchmark_pass_count, len(review_cases)),
    }

    return {
        "benchmark_count": len(review_cases),
        "metrics": metrics,
        "cases": case_results,
    }


def main() -> None:
    payload = evaluate_reviews()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
