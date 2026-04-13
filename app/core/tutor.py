from __future__ import annotations

import chess

from app.core.adaptation import SessionBayesianAdapter
from app.core.levels import LevelProfile
from app.core.move_engine import MoveEngine
from app.core.reports import GameReviewReport, MoveCoachingReport, PositionAnalysisReport
from app.core.services import AnalysisService, PlayCoachingService, ReviewService, finalize_candidate


class ChessTutor:
    def __init__(
        self,
        engine: MoveEngine | None = None,
        adapter: SessionBayesianAdapter | None = None,
    ) -> None:
        self.engine = engine or MoveEngine(adapter=adapter)
        self.analysis_service = AnalysisService(self.engine)
        self.play_service = PlayCoachingService(self.engine, self.analysis_service)
        self.review_service = ReviewService()

    def analyze_position(self, board: chess.Board, level: LevelProfile) -> PositionAnalysisReport:
        return self.analysis_service.analyze_position(board, level)

    def coach_player_move(
        self,
        board_before: chess.Board,
        move: chess.Move,
        level: LevelProfile,
    ) -> MoveCoachingReport:
        return self.play_service.coach_move(board_before, move, level)

    def choose_bot_move(self, board: chess.Board, level: LevelProfile):
        effective_level = self.engine.adapter.adapt_level(level) if self.engine.adapter is not None else level
        analysis = self.engine.analyze(board, effective_level)
        chosen = self.engine.choose_bot_move(board, effective_level)
        return finalize_candidate(
            self.analysis_service._build_candidate(board, chosen, analysis, effective_level),
            self.analysis_service._build_candidate(board, analysis.tutor_move, analysis, effective_level),
            effective_level,
        )

    def review_game(self, coaching_reports: list[MoveCoachingReport], pgn: str) -> GameReviewReport:
        return self.review_service.review_reports(coaching_reports, pgn)
