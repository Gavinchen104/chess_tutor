from __future__ import annotations

import chess

from app.core.levels import LevelProfile
from app.core.move_engine import MoveEngine
from app.core.reports import GameReviewReport, MoveCoachingReport
from app.core.services import PlayCoachingService, ReviewService


def evaluate_player_move(
    engine: MoveEngine,
    board_before: chess.Board,
    move: chess.Move,
    level: LevelProfile,
) -> MoveCoachingReport:
    return PlayCoachingService(engine=engine).coach_move(board_before, move, level)


def build_review(coaching_reports: list[MoveCoachingReport], pgn: str) -> GameReviewReport:
    return ReviewService().review_reports(coaching_reports, pgn)
