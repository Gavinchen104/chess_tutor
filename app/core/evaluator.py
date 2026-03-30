from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import chess

from app.core.levels import LevelProfile
from app.core.move_engine import MoveEngine, MoveInsight, PositionAnalysis


@dataclass
class MoveFeedback:
    chosen_san: str
    best_san: str
    tutor_san: str
    score_delta_cp: int
    verdict: str
    lesson: str
    themes: list[str] = field(default_factory=list)
    addressed_priorities: list[str] = field(default_factory=list)
    missed_priority: str | None = None
    coach_note: str = ""


@dataclass
class GameReview:
    pgn: str
    findings: list[str]
    summary: str


def evaluate_player_move(
    engine: MoveEngine,
    board_before: chess.Board,
    move: chess.Move,
    level: LevelProfile,
) -> tuple[MoveFeedback, PositionAnalysis]:
    analysis = engine.analyze(board_before, level)
    chosen_san = board_before.san(move)
    chosen_insight = engine.inspect_move(
        board_before,
        move,
        level,
        best_score_cp=analysis.best_move.score_cp,
        position_snapshot=analysis.snapshot,
        position_needs=analysis.position_needs,
    )
    delta = analysis.best_move.score_cp - chosen_insight.score_cp

    if delta <= 25:
        verdict = "Excellent"
    elif delta <= level.max_eval_loss:
        verdict = "Good practical move"
    elif delta <= level.max_eval_loss * 2:
        verdict = "Inaccuracy"
    else:
        verdict = "Blunder risk"

    lesson, missed_priority, coach_note = build_player_lesson(
        chosen_insight,
        analysis.tutor_move,
        analysis.position_needs,
        verdict,
    )

    feedback = MoveFeedback(
        chosen_san=chosen_san,
        best_san=analysis.best_move.san,
        tutor_san=analysis.tutor_move.san,
        score_delta_cp=delta,
        verdict=verdict,
        lesson=lesson,
        themes=chosen_insight.tags,
        addressed_priorities=chosen_insight.priorities_addressed,
        missed_priority=missed_priority,
        coach_note=coach_note,
    )
    return feedback, analysis


def build_player_lesson(
    chosen_insight: MoveInsight,
    tutor_move: MoveInsight,
    position_needs: list[str],
    verdict: str,
) -> tuple[str, str | None, str]:
    top_priority = position_needs[0] if position_needs else None
    readable_priority = top_priority.replace("_", " ") if top_priority else "the position"

    if verdict == "Excellent":
        lesson = (
            f"You addressed {readable_priority} well. "
            f"Your move follows a practical plan instead of drifting."
        )
        return lesson, None, chosen_insight.plan

    if verdict == "Good practical move":
        if top_priority and top_priority not in chosen_insight.priorities_addressed:
            lesson = (
                f"Your move is playable, but it does not fully solve {readable_priority}. "
                f"The tutor preferred `{tutor_move.san}` because it targets that issue more directly."
            )
            return lesson, top_priority, tutor_move.plan
        lesson = (
            "Your move keeps the position playable and follows a sensible idea. "
            f"The tutor move `{tutor_move.san}` is just a bit cleaner."
        )
        return lesson, None, chosen_insight.plan

    if chosen_insight.delta and chosen_insight.delta.safety_change < 0:
        lesson = (
            "This move increases tactical danger. Before looking for activity, "
            "first check whether any piece becomes loose or under-defended."
        )
        return lesson, "safety", tutor_move.plan

    if top_priority and top_priority not in chosen_insight.priorities_addressed:
        lesson = (
            f"This move misses the most urgent practical issue: {readable_priority}. "
            f"`{tutor_move.san}` was stronger because it dealt with that first."
        )
        return lesson, top_priority, tutor_move.plan

    lesson = (
        "This move gives away too much value for the position. "
        f"Try to compare your idea with a calmer move like `{tutor_move.san}` that keeps more options."
    )
    return lesson, top_priority, tutor_move.plan


def build_review(feedback_items: list[MoveFeedback], pgn: str) -> GameReview:
    if not feedback_items:
        return GameReview(
            pgn=pgn,
            findings=["No moves recorded yet."],
            summary="Play a few moves to generate a review.",
        )

    blunders = sum(1 for item in feedback_items if item.verdict == "Blunder risk")
    inaccuracies = sum(1 for item in feedback_items if item.verdict == "Inaccuracy")
    strong = sum(1 for item in feedback_items if item.verdict in {"Excellent", "Good practical move"})
    missed_priority_counts = Counter(
        item.missed_priority for item in feedback_items if item.missed_priority
    )
    theme_counts = Counter(theme for item in feedback_items for theme in item.themes)

    findings: list[str] = []
    if blunders:
        findings.append(f"{blunders} move(s) created serious risk by ignoring safety or the most urgent board problem.")
    if inaccuracies:
        findings.append(f"{inaccuracies} move(s) were playable but did not solve the position's main practical need.")
    if strong:
        findings.append(f"{strong} move(s) matched the tutor's practical plan reasonably well.")

    if missed_priority_counts:
        top_priority, count = missed_priority_counts.most_common(1)[0]
        findings.append(
            f"The most common missed theme was {top_priority.replace('_', ' ')} on {count} move(s)."
        )

    if theme_counts:
        top_theme, _ = theme_counts.most_common(1)[0]
        findings.append(
            f"Your games most often revolved around {top_theme.replace('_', ' ')}, which is a good area to review deliberately."
        )

    if not findings:
        findings.append("The game stayed balanced with no major evaluation swings.")

    summary = build_review_summary(blunders, inaccuracies, missed_priority_counts)
    return GameReview(pgn=pgn, findings=findings, summary=summary)


def build_review_summary(
    blunders: int,
    inaccuracies: int,
    missed_priority_counts: Counter[str],
) -> str:
    if missed_priority_counts:
        priority, _ = missed_priority_counts.most_common(1)[0]
        readable = priority.replace("_", " ")
        return f"Main lesson: slow down and solve {readable} before looking for ambitious moves."
    if blunders:
        return "Main lesson: safety has to come before activity. Scan for loose pieces every move."
    if inaccuracies:
        return "Main lesson: your moves were often playable, but you can be more systematic about addressing the position's main need first."
    return "Main lesson: keep following practical plans and compare your move with the cleanest improving move in the position."
