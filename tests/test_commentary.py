import chess

from app.core.commentary import build_move_explanation
from app.core.levels import get_level
from app.core.move_engine import MoveDelta, MoveInsight


def test_build_move_explanation_mentions_style():
    move = MoveInsight(
        move=chess.Move.from_uci("e2e4"),
        san="e4",
        score_cp=40,
        tutor_score=88.0,
        difficulty=0.8,
        tags=["center", "development"],
        reasons=["increases control of the center."],
        priorities_addressed=["development"],
        plan="Primary coaching goal: address development first.",
        delta=MoveDelta(
            material_change_cp=0,
            center_control_change=10,
            safety_change=0,
            development_change=1,
            king_safety_change=0,
            opponent_king_pressure_change=0,
            mobility_change=2,
        ),
    )
    text = build_move_explanation(move, get_level("600"))
    assert "center" in text.lower()
    assert "habit-focused" in text.lower()
    assert "development" in text.lower()
