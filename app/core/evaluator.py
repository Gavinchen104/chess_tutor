from __future__ import annotations

from dataclasses import dataclass

import chess

from app.core.levels import LevelProfile
from app.core.move_engine import MoveEngine, PositionAnalysis


@dataclass
class MoveFeedback:
    chosen_san: str
    best_san: str
    tutor_san: str
    score_delta_cp: int
    verdict: str
    lesson: str


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
    score_cp = engine.evaluate_move(board_before, move)
    delta = analysis.best_move.score_cp - score_cp

    if delta <= 25:
        verdict = "Excellent"
        lesson = "You matched the strongest practical move in the position."
    elif delta <= level.max_eval_loss:
        verdict = "Good practical move"
        lesson = "Your move is playable and fits the position, even if there was a slightly cleaner option."
    elif delta <= level.max_eval_loss * 2:
        verdict = "Inaccuracy"
        lesson = "You gave away some value here. Check safety first, then look for active squares."
    else:
        verdict = "Blunder risk"
        lesson = "This move likely misses a tactical or safety issue. Slow down and scan for hanging pieces."

    feedback = MoveFeedback(
        chosen_san=chosen_san,
        best_san=analysis.best_move.san,
        tutor_san=analysis.tutor_move.san,
        score_delta_cp=delta,
        verdict=verdict,
        lesson=lesson,
    )
    return feedback, analysis


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

    findings: list[str] = []
    if blunders:
        findings.append(f"{blunders} move(s) dropped significant value because of missed tactics or hanging pieces.")
    if inaccuracies:
        findings.append(f"{inaccuracies} move(s) were playable but could be improved with cleaner piece placement.")
    if strong:
        findings.append(f"{strong} move(s) followed the tutor's practical goals well.")
    if not findings:
        findings.append("The game stayed balanced with no major evaluation swings.")

    summary = (
        "Main lesson: check safety before ambition, then choose moves that improve development, center control, "
        "or king safety without demanding perfect calculation."
    )
    return GameReview(pgn=pgn, findings=findings, summary=summary)
