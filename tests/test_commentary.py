import chess

from app.core.commentary import build_move_explanation
from app.core.levels import get_level
from app.core.move_engine import MoveInsight


def test_build_move_explanation_mentions_style():
    move = MoveInsight(
        move=chess.Move.from_uci("e2e4"),
        san="e4",
        score_cp=40,
        tutor_score=88.0,
        difficulty=0.8,
        tags=["center", "development"],
        reasons=["increases control of the center."],
    )
    text = build_move_explanation(move, get_level("600"))
    assert "center" in text.lower()
    assert "habit-focused" in text.lower()
