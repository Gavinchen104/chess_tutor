import chess

from app.core.levels import get_level
from app.core.services import AnalysisService, PlayCoachingService


def test_coaching_report_flags_ignored_pressure():
    board = chess.Board("4k3/8/8/8/4q3/8/4R2P/4K3 w - - 0 1")
    report = PlayCoachingService().coach_move(board, chess.Move.from_uci("h2h3"), get_level("600"))
    assert report.chosen_move.primary_theme == "safety"
    assert any(finding.code == "ignored_attacked_high_value_piece" for finding in report.chosen_move.tactical_findings)


def test_analysis_service_returns_engine_metadata():
    board = chess.Board()
    report = AnalysisService().analyze_position(board, get_level("1000"))
    assert report.engine_metadata.provider
    assert report.candidate_moves
