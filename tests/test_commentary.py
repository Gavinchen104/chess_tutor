from app.core.commentary import build_move_explanation
from app.core.levels import get_level
from app.core.reports import CandidateMove


def test_build_move_explanation_mentions_style():
    move = CandidateMove(
        san="e4",
        uci="e2e4",
        score_cp=40,
        eval_gap_cp=0,
        tutor_score=88.0,
        difficulty=0.8,
        tactical_risk_score=0.0,
        strategic_fit_score=35.0,
        human_plausibility_score=92.0,
        mistake_class="best",
        primary_theme="center",
        primary_reason="Improves control of the center.",
        player_friendly_explanation="Improves control of the center. For 600 - Foundations, remember: improve undeveloped pieces first. At this level, this move balances strength, clarity, and practical execution.",
        training_habit="Improve undeveloped pieces first.",
        better_alternative_reason="This is already the tutor-preferred move for this rating band.",
        tags=["center", "development"],
        priorities_addressed=["development"],
        plan="Primary coaching goal: address development first.",
    )
    text = build_move_explanation(move, get_level("600"))
    assert "center" in text.lower()
    assert "habit-focused" in text.lower()
    assert "development" in text.lower()
