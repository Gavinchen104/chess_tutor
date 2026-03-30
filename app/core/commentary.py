from __future__ import annotations

from app.core.levels import LevelProfile
from app.core.move_engine import MoveInsight, PositionAnalysis


def format_cp(score_cp: int) -> str:
    if abs(score_cp) >= 90000:
        return "winning by force" if score_cp > 0 else "losing by force"
    return f"{score_cp / 100:.1f}"


def build_position_summary(analysis: PositionAnalysis, level: LevelProfile) -> str:
    tutor = analysis.tutor_move
    best = analysis.best_move
    needs_text = ", ".join(priority.replace("_", " ") for priority in analysis.position_needs[:2])
    if tutor.move == best.move:
        return (
            f"For {level.label}, `{tutor.san}` is both the strongest move I found and the cleanest teaching move. "
            f"It keeps the position around {format_cp(tutor.score_cp)} and leans on "
            f"{', '.join(tutor.tags[:2]) or 'solid principles'}. "
            f"Right now the main coaching focus is {needs_text or 'steady piece improvement'}."
        )
    return (
        f"The engine-style top move is `{best.san}` at {format_cp(best.score_cp)}, but for {level.label} "
        f"I recommend `{tutor.san}` instead. It stays within a practical margin while emphasizing "
        f"{', '.join(tutor.tags[:2]) or 'playable ideas'} over calculation-heavy play. "
        f"The move also helps with {needs_text or 'the most urgent practical issue in the position'}."
    )


def build_move_explanation(move: MoveInsight, level: LevelProfile) -> str:
    reasons = " ".join(reason.capitalize() for reason in move.reasons[:2])
    if not reasons:
        reasons = "It keeps your pieces coordinated and avoids unnecessary risk."
    priorities = ""
    if move.priorities_addressed:
        readable = ", ".join(priority.replace("_", " ") for priority in move.priorities_addressed[:2])
        priorities = f" It directly addresses {readable}."
    complexity = (
        "This is an easy-to-execute move for this level."
        if move.difficulty < 1.2
        else "It asks for some calculation, but the idea is still practical."
        if move.difficulty < 2.0
        else "This is stronger tactically, but it may be harder to execute consistently."
    )
    warning = f" Watch out: {move.warnings[0]}" if move.warnings else ""
    return f"{reasons}{priorities} {complexity} {move.plan} {level.commentary_style}{warning}"


def build_engine_vs_tutor_story(analysis: PositionAnalysis, level: LevelProfile) -> str:
    tutor = analysis.tutor_move
    best = analysis.best_move
    if tutor.move == best.move:
        return (
            "In this position the tutor and engine agree, which is useful evidence that the tutoring layer "
            "is not inventing weaker moves just to sound friendly."
        )
    gap = max(0, best.score_cp - tutor.score_cp)
    return (
        f"The tutor accepts about {gap / 100:.1f} pawns of theoretical loss to make the move more teachable "
        f"for {level.label}. The tradeoff is intentional: the tutor is trying to solve the position's main practical needs "
        f"({', '.join(priority.replace('_', ' ') for priority in analysis.position_needs[:2]) or 'piece coordination'}) "
        f"instead of only maximizing engine score."
    )
