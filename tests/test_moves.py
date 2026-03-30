import chess

from app.core.levels import get_level
from app.core.move_engine import MoveEngine


def test_move_engine_returns_candidates():
    board = chess.Board()
    analysis = MoveEngine().analyze(board, get_level("1000"))
    assert analysis.candidates
    assert analysis.best_move.san
    assert analysis.tutor_move.san


def test_move_engine_identifies_opening_priorities():
    board = chess.Board()
    analysis = MoveEngine().analyze(board, get_level("600"))
    assert "development" in analysis.position_needs
    assert analysis.tutor_move.plan
