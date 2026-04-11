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
from analysis.generate_appendix_report import build_appendix_report
from analysis.generate_appendix_report import generate_appendix_report
from analysis.user_feedback import append_feedback_entry, load_feedback_entries, summarize_feedback


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


def test_build_appendix_report_returns_reports_and_summary(tmp_path):
    result = build_appendix_report(output_dir=tmp_path)
    assert "positions_report" in result
    assert "reviews_report" in result
    assert "feedback_summary" in result
    assert "summary" in result
    assert result["summary"]["generated_files"]["positions_report"]


def test_user_feedback_round_trip_and_summary(tmp_path):
    feedback_path = tmp_path / "user_feedback.jsonl"
    append_feedback_entry(
        {
            "level_key": "600",
            "clarity": 4,
            "usefulness": 5,
            "actionability": 4,
            "overwhelm_reduction": 5,
            "notes": "Simple and concrete.",
        },
        path=feedback_path,
    )
    append_feedback_entry(
        {
            "level_key": "1000",
            "clarity": 3,
            "usefulness": 4,
            "actionability": 4,
            "overwhelm_reduction": 4,
            "notes": "",
        },
        path=feedback_path,
    )

    entries = load_feedback_entries(path=feedback_path)
    summary = summarize_feedback(entries)

    assert len(entries) == 2
    assert summary["count"] == 2
    assert summary["averages"]["usefulness"] == 4.5
    assert summary["by_level"]["600"] == 1
    assert summary["recent_notes"][0]["notes"] == "Simple and concrete."
