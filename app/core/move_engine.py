from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
import random
import shutil

import chess
import chess.engine

from app.core.levels import LevelProfile


PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

PIECE_SQUARE_TABLES = {
    chess.PAWN: (
        0, 0, 0, 0, 0, 0, 0, 0,
        50, 50, 50, 50, 50, 50, 50, 50,
        10, 10, 20, 30, 30, 20, 10, 10,
        5, 5, 10, 25, 25, 10, 5, 5,
        0, 0, 0, 20, 20, 0, 0, 0,
        5, -5, -10, 0, 0, -10, -5, 5,
        5, 10, 10, -20, -20, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0,
    ),
    chess.KNIGHT: (
        -50, -40, -30, -30, -30, -30, -40, -50,
        -40, -20, 0, 5, 5, 0, -20, -40,
        -30, 5, 10, 15, 15, 10, 5, -30,
        -30, 0, 15, 20, 20, 15, 0, -30,
        -30, 5, 15, 20, 20, 15, 5, -30,
        -30, 0, 10, 15, 15, 10, 0, -30,
        -40, -20, 0, 0, 0, 0, -20, -40,
        -50, -40, -30, -30, -30, -30, -40, -50,
    ),
    chess.BISHOP: (
        -20, -10, -10, -10, -10, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 10, 10, 5, 0, -10,
        -10, 5, 5, 10, 10, 5, 5, -10,
        -10, 0, 10, 10, 10, 10, 0, -10,
        -10, 10, 10, 10, 10, 10, 10, -10,
        -10, 5, 0, 0, 0, 0, 5, -10,
        -20, -10, -10, -10, -10, -10, -10, -20,
    ),
    chess.ROOK: (
        0, 0, 5, 10, 10, 5, 0, 0,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        5, 10, 10, 10, 10, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0,
    ),
    chess.QUEEN: (
        -20, -10, -10, -5, -5, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 5, 5, 5, 0, -10,
        -5, 0, 5, 5, 5, 5, 0, -5,
        0, 0, 5, 5, 5, 5, 0, -5,
        -10, 5, 5, 5, 5, 5, 0, -10,
        -10, 0, 5, 0, 0, 0, 0, -10,
        -20, -10, -10, -5, -5, -10, -10, -20,
    ),
    chess.KING: (
        20, 30, 10, 0, 0, 10, 30, 20,
        20, 20, 0, 0, 0, 0, 20, 20,
        -10, -20, -20, -20, -20, -20, -20, -10,
        -20, -30, -30, -40, -40, -30, -30, -20,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
    ),
}

DEFAULT_ENGINE_CANDIDATES = 5


@dataclass
class MoveInsight:
    move: chess.Move
    san: str
    score_cp: int
    tutor_score: float
    difficulty: float
    tags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass
class PositionAnalysis:
    best_move: MoveInsight
    tutor_move: MoveInsight
    candidates: list[MoveInsight]
    evaluation_cp: int
    engine_name: str


def find_stockfish_path() -> str | None:
    env_path = os.getenv("STOCKFISH_EXECUTABLE")
    if env_path and os.path.exists(env_path):
        return env_path
    common_names = ("stockfish", "stockfish-ubuntu-x86-64", "stockfish-macos")
    for name in common_names:
        discovered = shutil.which(name)
        if discovered:
            return discovered
    return None


class MoveEngine:
    def __init__(self) -> None:
        self.stockfish_path = find_stockfish_path()

    def analyze(self, board: chess.Board, level: LevelProfile) -> PositionAnalysis:
        candidates = self._get_candidates(board)
        if not candidates:
            raise ValueError("No legal moves available in this position.")

        for move in candidates:
            move.tags, move.reasons = describe_move_features(board, move.move)
            move.difficulty = estimate_difficulty(board, move.move, move.score_cp, candidates[0].score_cp)
            move.tutor_score = compute_tutor_score(move, candidates[0].score_cp, level)

        candidates.sort(key=lambda item: item.score_cp, reverse=True)
        best_move = candidates[0]
        tutor_move = max(candidates, key=lambda item: item.tutor_score)
        evaluation_cp = candidates[0].score_cp
        engine_name = "Stockfish" if self.stockfish_path else "Heuristic Tutor Engine"
        return PositionAnalysis(
            best_move=best_move,
            tutor_move=tutor_move,
            candidates=candidates,
            evaluation_cp=evaluation_cp,
            engine_name=engine_name,
        )

    def choose_bot_move(self, board: chess.Board, level: LevelProfile) -> MoveInsight:
        analysis = self.analyze(board, level)
        short_list = analysis.candidates[: max(3, min(6, len(analysis.candidates)))]
        weights = []
        for candidate in short_list:
            gap = analysis.best_move.score_cp - candidate.score_cp
            if gap > level.max_eval_loss * 2:
                continue
            weight = max(0.5, candidate.tutor_score)
            weights.append((candidate, weight))
        if not weights:
            return analysis.tutor_move
        total = sum(weight for _, weight in weights)
        pick = random.uniform(0, total)
        running = 0.0
        for candidate, weight in weights:
            running += weight
            if running >= pick:
                return candidate
        return weights[-1][0]

    def evaluate_move(self, board: chess.Board, move: chess.Move) -> int:
        next_board = board.copy(stack=False)
        next_board.push(move)
        return evaluate_position(next_board, board.turn)

    def _get_candidates(self, board: chess.Board, multipv: int = DEFAULT_ENGINE_CANDIDATES) -> list[MoveInsight]:
        if self.stockfish_path:
            try:
                return self._analyze_with_stockfish(board, multipv)
            except (chess.engine.EngineError, FileNotFoundError):
                self.stockfish_path = None
        return self._analyze_heuristically(board)

    def _analyze_with_stockfish(self, board: chess.Board, multipv: int) -> list[MoveInsight]:
        limit = chess.engine.Limit(depth=12)
        perspective = board.turn
        with chess.engine.SimpleEngine.popen_uci(self.stockfish_path) as engine:
            info = engine.analyse(board, limit, multipv=multipv)
        results = []
        for line in info:
            principal = line.get("pv")
            if not principal:
                continue
            move = principal[0]
            score = line["score"].pov(perspective)
            cp = _score_to_cp(score)
            results.append(
                MoveInsight(
                    move=move,
                    san=board.san(move),
                    score_cp=cp,
                    tutor_score=0.0,
                    difficulty=0.0,
                )
            )
        return results or self._analyze_heuristically(board)

    def _analyze_heuristically(self, board: chess.Board) -> list[MoveInsight]:
        perspective = board.turn
        candidates: list[MoveInsight] = []
        for move in board.legal_moves:
            next_board = board.copy(stack=False)
            next_board.push(move)
            score = evaluate_position(next_board, perspective)
            candidates.append(
                MoveInsight(
                    move=move,
                    san=board.san(move),
                    score_cp=score,
                    tutor_score=0.0,
                    difficulty=0.0,
                )
            )
        candidates.sort(key=lambda item: item.score_cp, reverse=True)
        return candidates[:8]


def _score_to_cp(score: chess.engine.PovScore) -> int:
    mate = score.mate()
    if mate is not None:
        sign = 1 if mate > 0 else -1
        return sign * (100000 - abs(mate) * 1000)
    return score.score(mate_score=100000) or 0


def evaluate_position(board: chess.Board, perspective: chess.Color) -> int:
    if board.is_checkmate():
        return -100000 if board.turn == perspective else 100000
    if board.is_stalemate() or board.is_insufficient_material() or board.is_seventyfive_moves():
        return 0

    score = 0
    for square, piece in board.piece_map().items():
        multiplier = 1 if piece.color == perspective else -1
        table = PIECE_SQUARE_TABLES[piece.piece_type]
        table_index = square if piece.color == chess.WHITE else chess.square_mirror(square)
        score += multiplier * (PIECE_VALUES[piece.piece_type] + table[table_index])

    score += mobility_score(board, perspective)
    score += king_safety_score(board, perspective)
    score += center_control_score(board, perspective)
    score += hanging_piece_score(board, perspective)
    return int(score)


def mobility_score(board: chess.Board, perspective: chess.Color) -> int:
    turn = board.turn
    board.turn = perspective
    own_mobility = board.legal_moves.count()
    board.turn = not perspective
    enemy_mobility = board.legal_moves.count()
    board.turn = turn
    return (own_mobility - enemy_mobility) * 3


def king_safety_score(board: chess.Board, perspective: chess.Color) -> int:
    score = 0
    for color, multiplier in ((perspective, 1), (not perspective, -1)):
        king_square = board.king(color)
        if king_square is None:
            continue
        if board.has_kingside_castling_rights(color) or board.has_queenside_castling_rights(color):
            score -= multiplier * 12
        rank = chess.square_rank(king_square)
        if color == chess.WHITE and rank <= 1:
            score += multiplier * 10
        if color == chess.BLACK and rank >= 6:
            score += multiplier * 10
        attackers = len(board.attackers(not color, king_square))
        defenders = len(board.attackers(color, king_square))
        score += multiplier * (defenders - attackers) * 8
    return score


def center_control_score(board: chess.Board, perspective: chess.Color) -> int:
    center = (chess.D4, chess.E4, chess.D5, chess.E5)
    score = 0
    for square in center:
        score += len(board.attackers(perspective, square)) * 5
        score -= len(board.attackers(not perspective, square)) * 5
    return score


def hanging_piece_score(board: chess.Board, perspective: chess.Color) -> int:
    score = 0
    for square, piece in board.piece_map().items():
        value = PIECE_VALUES[piece.piece_type]
        attackers = len(board.attackers(not piece.color, square))
        defenders = len(board.attackers(piece.color, square))
        if attackers and defenders == 0:
            if piece.color == perspective:
                score -= value // 2
            else:
                score += value // 2
    return score


def describe_move_features(board: chess.Board, move: chess.Move) -> tuple[list[str], list[str]]:
    tags: list[str] = []
    reasons: list[str] = []
    piece = board.piece_at(move.from_square)
    if piece is None:
        return tags, reasons

    if board.is_capture(move):
        tags.append("safety")
        captured = board.piece_at(move.to_square)
        if captured:
            reasons.append(f"wins material by taking a {chess.piece_name(captured.piece_type)}.")
        else:
            reasons.append("removes pressure with a capture.")

    if board.gives_check(move):
        tags.append("initiative")
        reasons.append("creates a forcing check.")

    if board.is_castling(move):
        tags.extend(["king_safety", "development"])
        reasons.append("improves king safety by castling.")

    from_rank = chess.square_rank(move.from_square)
    to_rank = chess.square_rank(move.to_square)
    if piece.piece_type in (chess.KNIGHT, chess.BISHOP):
        if (piece.color == chess.WHITE and from_rank == 0 and to_rank >= 2) or (
            piece.color == chess.BLACK and from_rank == 7 and to_rank <= 5
        ):
            tags.append("development")
            reasons.append("develops a minor piece to a more useful square.")

    if move.to_square in (chess.D4, chess.E4, chess.D5, chess.E5):
        tags.append("center")
        reasons.append("increases control of the center.")

    next_board = board.copy(stack=False)
    next_board.push(move)
    if hanging_piece_score(next_board, board.turn) > hanging_piece_score(board, board.turn):
        tags.append("safety")
        reasons.append("reduces the chance of leaving a piece hanging.")

    if not tags:
        tags.append("activity")
        reasons.append("improves piece activity without creating new weaknesses.")

    unique_tags = list(dict.fromkeys(tags))
    unique_reasons = list(dict.fromkeys(reasons))
    return unique_tags, unique_reasons


def estimate_difficulty(board: chess.Board, move: chess.Move, score_cp: int, best_score_cp: int) -> float:
    difficulty = 1.0
    piece = board.piece_at(move.from_square)
    if piece is None:
        return difficulty

    if board.gives_check(move):
        difficulty += 0.9
    if move.promotion:
        difficulty += 1.5
    if board.is_capture(move):
        victim = board.piece_at(move.to_square)
        if victim and piece and PIECE_VALUES[piece.piece_type] > PIECE_VALUES[victim.piece_type]:
            difficulty += 1.4
    if board.is_castling(move):
        difficulty -= 0.4

    gap = max(0, best_score_cp - score_cp)
    difficulty += min(2.5, gap / 150.0)
    if move.to_square in (chess.D4, chess.E4, chess.D5, chess.E5):
        difficulty -= 0.2
    return max(0.4, difficulty)


def compute_tutor_score(candidate: MoveInsight, best_score_cp: int, level: LevelProfile) -> float:
    eval_gap = max(0, best_score_cp - candidate.score_cp)
    eval_credit = max(0.0, 140.0 - float(eval_gap))
    preferred_bonus = sum(8.0 for tag in candidate.tags if tag in level.preferred_tags)
    complexity_penalty = candidate.difficulty * level.complexity_weight
    return eval_credit + preferred_bonus - complexity_penalty
