from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.core.reports import CandidateMove, DiagnosticFinding
from analysis.eval_utils import (
    explanation_is_complete,
    expected_property_passes,
    forbidden_property_violated,
    load_json,
)
from analysis.evaluate_positions import evaluate_positions
from analysis.evaluate_reviews import evaluate_reviews
from analysis.generate_appendix_report import generate_appendix_report


REPO_ROOT = Path(__file__).resolve().parents[1]


def _mock_candidate() -> CandidateMove:
    return CandidateMove(
        san="Nf3",
        uci="g1f3",
        score_cp=35,
        eval_gap_cp=10,
        tutor_score=88.0,
        difficulty=1.1,
        tactical_risk_score=8.0,
        strategic_fit_score=24.0,
        human_plausibility_score=82.0,
        mistake_class="practical",
        primary_theme="development",
        primary_reason="The move improves development.",
        player_friendly_explanation="Remember the development habit and keep improving your pieces.",
        training_habit="Improve undeveloped pieces first.",
        better_alternative_reason="This is already the tutor-preferred move for this level.",
        tags=["development", "center"],
        priorities_addressed=["development"],
        plan="Primary coaching goal: address development first.",
        tactical_findings=[],
        strategic_findings=[
            DiagnosticFinding(
                category="strategic",
                code="development_improved",
                severity="medium",
                direction="positive",
                theme="development",
                summary="The move improves development.",
                training_habit="Improve undeveloped pieces first.",
            )
        ],
    )


def test_positions_v2_schema_has_required_keys():
    cases = load_json(REPO_ROOT / "data" / "benchmarks" / "positions_v2.json")
    required = {
        "label",
        "theme",
        "level_key",
        "fen",
        "expected_tutor_properties",
        "acceptable_primary_themes",
        "forbidden_properties",
        "min_explanation_keywords",
        "notes",
    }
    assert cases
    for case in cases:
        assert required.issubset(case.keys())


def test_property_helpers_work_on_mock_candidate():
    report = SimpleNamespace(position_needs=["development"], tutor_explanation="Remember this development habit.")
    candidate = _mock_candidate()

    assert expected_property_passes(report, candidate, "600", "improves_development")
    assert expected_property_passes(report, candidate, "600", "low_tactical_risk")
    assert not forbidden_property_violated(report, candidate, "600", "hangs_material")
    assert explanation_is_complete("Remember this development habit.", ["development"])


def test_evaluate_positions_returns_expected_top_level_fields():
    result = evaluate_positions(REPO_ROOT / "data" / "benchmarks" / "positions_v2.json")
    assert "benchmark_count" in result
    assert "metrics" in result
    assert "cases" in result
    assert result["benchmark_count"] >= 1


def test_review_cases_schema_has_required_keys():
    cases = load_json(REPO_ROOT / "data" / "benchmarks" / "review_cases.json")
    required = {
        "label",
        "level_key",
        "player_color",
        "pgn_path",
        "expected_weakness_themes",
        "expected_next_step_keywords",
        "notes",
    }
    assert cases
    for case in cases:
        assert required.issubset(case.keys())
        assert (REPO_ROOT / case["pgn_path"]).exists()


def test_evaluate_reviews_returns_expected_top_level_fields():
    result = evaluate_reviews(REPO_ROOT / "data" / "benchmarks" / "review_cases.json")
    assert "benchmark_count" in result
    assert "metrics" in result
    assert "cases" in result
    assert result["benchmark_count"] >= 1


def test_generate_appendix_report_writes_output_files(tmp_path):
    result = generate_appendix_report(output_dir=tmp_path)
    assert "generated_files" in result
    assert (tmp_path / "positions_report.json").exists()
    assert (tmp_path / "reviews_report.json").exists()
    assert (tmp_path / "appendix_summary.json").exists()
