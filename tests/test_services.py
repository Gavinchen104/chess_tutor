import chess
from pathlib import Path

from app.core.levels import LEVELS, get_level
from app.core.services import AnalysisService, EvaluationService, PlayCoachingService


def test_coaching_report_flags_ignored_pressure():
    board = chess.Board("4k3/8/8/8/4q3/8/4R2P/4K3 w - - 0 1")
    report = PlayCoachingService().coach_move(board, chess.Move.from_uci("h2h3"), get_level("600"))
    assert report.chosen_move.primary_theme == "safety"
    assert any(finding.code == "ignored_attacked_high_value_piece" for finding in report.chosen_move.tactical_findings)


def test_evaluation_service_runs_local_benchmarks():
    repo_root = Path(__file__).resolve().parents[1]
    result = EvaluationService().evaluate_local_benchmarks(
        positions_path=repo_root / "data" / "benchmarks" / "positions.json",
        games_path=repo_root / "data" / "benchmarks" / "sample_games.pgn",
        levels=LEVELS,
    )
    assert result.benchmark_count >= 10
    assert "pct_tutor_differs_from_engine" in result.metrics


def test_analysis_service_returns_engine_metadata():
    board = chess.Board()
    report = AnalysisService().analyze_position(board, get_level("1000"))
    assert report.engine_metadata.provider
    assert report.candidate_moves
