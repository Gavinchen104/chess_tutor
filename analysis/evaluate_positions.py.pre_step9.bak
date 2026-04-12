from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chess

from app.core.levels import LEVELS
from app.core.services import AnalysisService
from analysis.eval_utils import (
    explanation_is_complete,
    expected_property_passes,
    forbidden_property_violated,
    load_json,
    practical_for_level,
    safe_rate,
)


DEFAULT_POSITIONS_PATH = REPO_ROOT / "data" / "benchmarks" / "positions_v2.json"


def evaluate_positions(positions_path: Path = DEFAULT_POSITIONS_PATH) -> dict:
    benchmark_cases = load_json(positions_path)
    analysis_service = AnalysisService()

    total_expected_checks = 0
    passed_expected_checks = 0

    total_forbidden_checks = 0
    violated_forbidden_checks = 0

    theme_match_count = 0
    level_fit_count = 0
    explanation_ok_count = 0
    benchmark_pass_count = 0

    case_results: list[dict] = []

    for case in benchmark_cases:
        label = case["label"]
        level_key = case["level_key"]

        try:
            board = chess.Board(case["fen"])
            level = LEVELS[level_key]
            report = analysis_service.analyze_position(board, level, candidate_limit=5)
            candidate = report.tutor_move

            property_results = {
                property_name: expected_property_passes(report, candidate, level_key, property_name)
                for property_name in case["expected_tutor_properties"]
            }
            forbidden_results = {
                property_name: forbidden_property_violated(report, candidate, level_key, property_name)
                for property_name in case["forbidden_properties"]
            }

            theme_match = candidate.primary_theme in case["acceptable_primary_themes"]
            level_fit = practical_for_level(candidate, level_key)

            explanation_text = f"{report.tutor_explanation} {candidate.player_friendly_explanation}"
            explanation_ok = explanation_is_complete(
                explanation_text,
                case.get("min_explanation_keywords", []),
            )

            passed = (
                all(property_results.values())
                and not any(forbidden_results.values())
                and theme_match
                and level_fit
                and explanation_ok
            )

            total_expected_checks += len(property_results)
            passed_expected_checks += sum(1 for value in property_results.values() if value)

            total_forbidden_checks += len(forbidden_results)
            violated_forbidden_checks += sum(1 for value in forbidden_results.values() if value)

            theme_match_count += int(theme_match)
            level_fit_count += int(level_fit)
            explanation_ok_count += int(explanation_ok)
            benchmark_pass_count += int(passed)

            case_results.append(
                {
                    "label": label,
                    "passed": passed,
                    "level_key": level_key,
                    "theme": case["theme"],
                    "tutor_move": candidate.san,
                    "engine_best_move": report.engine_best_move.san,
                    "primary_theme": candidate.primary_theme,
                    "eval_gap_cp": candidate.eval_gap_cp,
                    "difficulty": round(candidate.difficulty, 2),
                    "tactical_risk_score": round(candidate.tactical_risk_score, 2),
                    "human_plausibility_score": round(candidate.human_plausibility_score, 2),
                    "mistake_class": candidate.mistake_class,
                    "position_needs": report.position_needs,
                    "property_results": property_results,
                    "forbidden_results": forbidden_results,
                    "theme_match": theme_match,
                    "level_fit": level_fit,
                    "explanation_complete": explanation_ok,
                    "notes": case.get("notes", ""),
                }
            )

        except Exception as exc:
            case_results.append(
                {
                    "label": label,
                    "passed": False,
                    "level_key": level_key,
                    "error": str(exc),
                    "notes": case.get("notes", ""),
                }
            )

    metrics = {
        "property_satisfaction_rate": safe_rate(passed_expected_checks, total_expected_checks),
        "forbidden_property_violation_rate": safe_rate(violated_forbidden_checks, total_forbidden_checks),
        "theme_match_rate": safe_rate(theme_match_count, len(benchmark_cases)),
        "level_fit_rate": safe_rate(level_fit_count, len(benchmark_cases)),
        "explanation_completeness_rate": safe_rate(explanation_ok_count, len(benchmark_cases)),
        "benchmark_pass_rate": safe_rate(benchmark_pass_count, len(benchmark_cases)),
    }

    return {
        "benchmark_count": len(benchmark_cases),
        "metrics": metrics,
        "cases": case_results,
    }


def main() -> None:
    payload = evaluate_positions()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
