from __future__ import annotations

from dataclasses import dataclass

import chess

from app.core.commentary import (
    build_engine_vs_tutor_story,
    build_move_explanation,
    build_position_summary,
)
from app.core.evaluator import MoveFeedback, build_review, evaluate_player_move
from app.core.levels import LevelProfile
from app.core.move_engine import MoveEngine, MoveInsight, PositionAnalysis


@dataclass
class TutorReport:
    analysis: PositionAnalysis
    overview: str
    tutor_explanation: str
    evaluation_story: str


class ChessTutor:
    def __init__(self, engine: MoveEngine | None = None) -> None:
        self.engine = engine or MoveEngine()

    def analyze_position(self, board: chess.Board, level: LevelProfile) -> TutorReport:
        analysis = self.engine.analyze(board, level)
        overview = build_position_summary(analysis, level)
        tutor_explanation = build_move_explanation(analysis.tutor_move, level)
        evaluation_story = build_engine_vs_tutor_story(analysis, level)
        return TutorReport(
            analysis=analysis,
            overview=overview,
            tutor_explanation=tutor_explanation,
            evaluation_story=evaluation_story,
        )

    def coach_player_move(
        self,
        board_before: chess.Board,
        move: chess.Move,
        level: LevelProfile,
    ) -> tuple[MoveFeedback, TutorReport]:
        feedback, analysis = evaluate_player_move(self.engine, board_before, move, level)
        report = TutorReport(
            analysis=analysis,
            overview=build_position_summary(analysis, level),
            tutor_explanation=build_move_explanation(analysis.tutor_move, level),
            evaluation_story=build_engine_vs_tutor_story(analysis, level),
        )
        return feedback, report

    def choose_bot_move(self, board: chess.Board, level: LevelProfile) -> MoveInsight:
        return self.engine.choose_bot_move(board, level)

    def review_game(self, feedback_items: list[MoveFeedback], pgn: str):
        return build_review(feedback_items, pgn)
