from __future__ import annotations

from app.core.levels import LevelProfile
from app.core.reports import CandidateMove, PositionAnalysisReport


def _theme_label(theme: str) -> str:
    return theme.replace("_", " ")


def format_cp(score_cp: int) -> str:
    if abs(score_cp) >= 90000:
        return "winning by force" if score_cp > 0 else "losing by force"
    return f"{score_cp / 100:.1f}"


def build_position_summary(analysis: PositionAnalysisReport, level: LevelProfile) -> str:
    tutor = analysis.tutor_move
    best = analysis.engine_best_move
    needs_text = ", ".join(priority.replace("_", " ") for priority in analysis.position_needs[:2])
    if tutor.uci == best.uci:
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


def build_move_explanation(move: CandidateMove, level: LevelProfile) -> str:
    theme_sentence = f"Primary teaching theme: {_theme_label(move.primary_theme)}."

    supporting_sentence = ""
    if move.priorities_addressed:
        readable = ", ".join(_theme_label(priority) for priority in move.priorities_addressed[:2])
        supporting_sentence = f"Supporting teaching themes: {readable}."
    elif move.tags:
        extras = [tag for tag in move.tags if tag != move.primary_theme]
        if extras:
            readable = ", ".join(_theme_label(tag) for tag in extras[:2])
            supporting_sentence = f"Supporting teaching themes: {readable}."

    complexity = (
        "This should be easy to execute at this rating."
        if move.difficulty < 1.2
        else "This asks for some calculation, but the main idea is still practical."
        if move.difficulty < 2.0
        else "This is sharper and needs more accuracy to execute well."
    )
    style_sentence = level.commentary_style

    return " ".join(
        part.strip()
        for part in (
            move.player_friendly_explanation,
            theme_sentence,
            supporting_sentence,
            complexity,
            style_sentence,
        )
        if part.strip()
    )


def build_engine_vs_tutor_story(analysis: PositionAnalysisReport, level: LevelProfile) -> str:
    tutor = analysis.tutor_move
    best = analysis.engine_best_move
    if tutor.uci == best.uci:
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
