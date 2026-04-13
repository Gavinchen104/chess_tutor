from __future__ import annotations

from dataclasses import dataclass, field
import os
import random
import shutil

import chess
import chess.engine

from app.core.adaptation import SessionBayesianAdapter
from app.core.learned_params import learned_params
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
BOT_RANDOMNESS_BY_LEVEL = {
    "600": 0.28,
    "1000": 0.2,
    "1400": 0.12,
    "1800": 0.06,
}
BOT_POOL_SIZE_BY_LEVEL = {
    "600": 8,
    "1000": 7,
    "1400": 6,
    "1800": 5,
}
BOT_EVAL_GAP_MULTIPLIERS = {
    "opening": {
        "600": 2.8,
        "1000": 2.3,
        "1400": 1.9,
        "1800": 1.4,
    },
    "middlegame": {
        "600": 2.4,
        "1000": 2.0,
        "1400": 1.6,
        "1800": 1.3,
    },
    "endgame": {
        "600": 2.0,
        "1000": 1.7,
        "1400": 1.5,
        "1800": 1.2,
    },
}


@dataclass
class PositionSnapshot:
    material_balance_cp: int
    center_control_balance: int
    own_hanging_value: int
    enemy_hanging_value: int
    developed_minor_pieces: int
    opponent_developed_minor_pieces: int
    own_king_safety: int
    opponent_king_safety: int
    legal_moves: int
    opponent_legal_moves: int
    has_castled: bool
    opponent_has_castled: bool


@dataclass
class MoveDelta:
    material_change_cp: int
    center_control_change: int
    safety_change: int
    development_change: int
    king_safety_change: int
    opponent_king_pressure_change: int
    mobility_change: int


@dataclass
class MoveInsight:
    move: chess.Move
    san: str
    score_cp: int
    tutor_score: float
    difficulty: float
    tags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    priorities_addressed: list[str] = field(default_factory=list)
    plan: str = ""
    snapshot: PositionSnapshot | None = None
    delta: MoveDelta | None = None
    model_features: dict[str, float] = field(default_factory=dict)


@dataclass
class PositionAnalysis:
    best_move: MoveInsight
    tutor_move: MoveInsight
    candidates: list[MoveInsight]
    evaluation_cp: int
    engine_name: str
    position_needs: list[str] = field(default_factory=list)
    snapshot: PositionSnapshot | None = None


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
    def __init__(self, adapter: SessionBayesianAdapter | None = None) -> None:
        self.stockfish_path = find_stockfish_path()
        self.adapter = adapter

    def analyze(self, board: chess.Board, level: LevelProfile) -> PositionAnalysis:
        candidates = self._get_candidates(board)
        if not candidates:
            raise ValueError("No legal moves available in this position.")

        position_snapshot = build_position_snapshot(board, board.turn)
        position_needs = identify_position_needs(position_snapshot)
        best_score_cp = max(candidate.score_cp for candidate in candidates)

        enriched_candidates = [
            self.inspect_move(
                board,
                candidate.move,
                level,
                score_cp=candidate.score_cp,
                best_score_cp=best_score_cp,
                position_snapshot=position_snapshot,
                position_needs=position_needs,
            )
            for candidate in candidates
        ]

        enriched_candidates.sort(key=lambda item: item.score_cp, reverse=True)
        best_move = enriched_candidates[0]
        tutor_move = max(enriched_candidates, key=lambda item: item.tutor_score)
        evaluation_cp = best_move.score_cp
        engine_name = "Stockfish" if self.stockfish_path else "Heuristic Tutor Engine"
        return PositionAnalysis(
            best_move=best_move,
            tutor_move=tutor_move,
            candidates=enriched_candidates,
            evaluation_cp=evaluation_cp,
            engine_name=engine_name,
            position_needs=position_needs,
            snapshot=position_snapshot,
        )

    def choose_bot_move(self, board: chess.Board, level: LevelProfile) -> MoveInsight:
        analysis = self.analyze(board, level)
        phase = estimate_game_phase(board)
        pool = build_bot_candidate_pool(analysis, board, level, phase, adaptation=self.adapter)
        weights = []
        for candidate in pool:
            weight = compute_bot_move_weight(
                board,
                candidate,
                analysis.best_move.score_cp,
                level,
                phase,
                adaptation=self.adapter,
            )
            jitter = 1.0 + random.uniform(-BOT_RANDOMNESS_BY_LEVEL[level.key], BOT_RANDOMNESS_BY_LEVEL[level.key])
            weights.append((candidate, max(0.05, weight * jitter)))
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
        return self.evaluate_position_for_side(next_board, board.turn)

    def inspect_move(
        self,
        board: chess.Board,
        move: chess.Move,
        level: LevelProfile,
        *,
        score_cp: int | None = None,
        best_score_cp: int | None = None,
        position_snapshot: PositionSnapshot | None = None,
        position_needs: list[str] | None = None,
    ) -> MoveInsight:
        before = position_snapshot or build_position_snapshot(board, board.turn)
        needs = position_needs or identify_position_needs(before)
        next_board = board.copy(stack=False)
        next_board.push(move)
        after = build_position_snapshot(next_board, board.turn)
        delta = build_move_delta(before, after)
        score = score_cp if score_cp is not None else self.evaluate_position_for_side(next_board, board.turn)
        baseline = best_score_cp if best_score_cp is not None else score
        tags, reasons, warnings, priorities_addressed = describe_move_features(board, move, before, after, needs)
        difficulty = estimate_difficulty(board, move, score, baseline, delta)
        model_features = build_model_features(
            board,
            move,
            level,
            score_cp=score,
            best_score_cp=baseline,
            difficulty=difficulty,
            tags=tags,
            priorities_addressed=priorities_addressed,
            delta=delta,
        )
        tutor_score = compute_tutor_score(
            score,
            baseline,
            level,
            tags,
            difficulty,
            priorities_addressed,
            delta,
            model_features=model_features,
            adaptation=self.adapter,
        )
        return MoveInsight(
            move=move,
            san=board.san(move),
            score_cp=score,
            tutor_score=tutor_score,
            difficulty=difficulty,
            tags=tags,
            reasons=reasons,
            warnings=warnings,
            priorities_addressed=priorities_addressed,
            plan=build_move_plan(tags, priorities_addressed, delta),
            snapshot=after,
            delta=delta,
            model_features=model_features,
        )

    def evaluate_position_for_side(self, board: chess.Board, perspective: chess.Color) -> int:
        if self.stockfish_path:
            try:
                with chess.engine.SimpleEngine.popen_uci(self.stockfish_path) as engine:
                    info = engine.analyse(board, chess.engine.Limit(depth=11))
                return _score_to_cp(info["score"].pov(perspective))
            except (chess.engine.EngineError, FileNotFoundError):
                self.stockfish_path = None
        return evaluate_position(board, perspective)

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
        return candidates[:10]


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
    own_mobility = legal_move_count(board, perspective)
    enemy_mobility = legal_move_count(board, not perspective)
    return (own_mobility - enemy_mobility) * 3


def legal_move_count(board: chess.Board, color: chess.Color) -> int:
    turn = board.turn
    board.turn = color
    count = board.legal_moves.count()
    board.turn = turn
    return count


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
    own_hanging = hanging_piece_value(board, perspective)
    enemy_hanging = hanging_piece_value(board, not perspective)
    return enemy_hanging - own_hanging


def hanging_piece_value(board: chess.Board, color: chess.Color) -> int:
    score = 0
    for square, piece in board.piece_map().items():
        if piece.color != color:
            continue
        attackers = len(board.attackers(not piece.color, square))
        defenders = len(board.attackers(piece.color, square))
        if attackers and defenders == 0:
            score += PIECE_VALUES[piece.piece_type]
    return score


def build_position_snapshot(board: chess.Board, perspective: chess.Color) -> PositionSnapshot:
    return PositionSnapshot(
        material_balance_cp=material_balance(board, perspective),
        center_control_balance=center_control_score(board, perspective),
        own_hanging_value=hanging_piece_value(board, perspective),
        enemy_hanging_value=hanging_piece_value(board, not perspective),
        developed_minor_pieces=count_developed_minor_pieces(board, perspective),
        opponent_developed_minor_pieces=count_developed_minor_pieces(board, not perspective),
        own_king_safety=king_ring_safety(board, perspective),
        opponent_king_safety=king_ring_safety(board, not perspective),
        legal_moves=legal_move_count(board, perspective),
        opponent_legal_moves=legal_move_count(board, not perspective),
        has_castled=has_castled(board, perspective),
        opponent_has_castled=has_castled(board, not perspective),
    )


def build_move_delta(before: PositionSnapshot, after: PositionSnapshot) -> MoveDelta:
    return MoveDelta(
        material_change_cp=after.material_balance_cp - before.material_balance_cp,
        center_control_change=after.center_control_balance - before.center_control_balance,
        safety_change=(before.own_hanging_value - after.own_hanging_value)
        + (after.enemy_hanging_value - before.enemy_hanging_value),
        development_change=after.developed_minor_pieces - before.developed_minor_pieces,
        king_safety_change=after.own_king_safety - before.own_king_safety,
        opponent_king_pressure_change=before.opponent_king_safety - after.opponent_king_safety,
        mobility_change=after.legal_moves - before.legal_moves,
    )


def identify_position_needs(snapshot: PositionSnapshot) -> list[str]:
    priorities: list[str] = []
    if snapshot.own_hanging_value >= 100:
        priorities.append("safety")
    if snapshot.developed_minor_pieces < 2:
        priorities.append("development")
    if not snapshot.has_castled and snapshot.own_king_safety < 14:
        priorities.append("king_safety")
    if snapshot.center_control_balance < 0:
        priorities.append("center")
    if snapshot.legal_moves + 3 < snapshot.opponent_legal_moves:
        priorities.append("activity")
    if snapshot.material_balance_cp > 150:
        priorities.append("conversion")
    if not priorities:
        priorities.append("activity")
    return priorities


def material_balance(board: chess.Board, perspective: chess.Color) -> int:
    score = 0
    for piece in board.piece_map().values():
        value = PIECE_VALUES[piece.piece_type]
        score += value if piece.color == perspective else -value
    return score


def count_developed_minor_pieces(board: chess.Board, color: chess.Color) -> int:
    total = 0
    home_squares = {
        chess.WHITE: {chess.B1, chess.G1, chess.C1, chess.F1},
        chess.BLACK: {chess.B8, chess.G8, chess.C8, chess.F8},
    }
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type not in (chess.KNIGHT, chess.BISHOP):
            continue
        if square not in home_squares[color]:
            total += 1
    return total


def has_castled(board: chess.Board, color: chess.Color) -> bool:
    king_square = board.king(color)
    if king_square is None:
        return False
    return king_square in (
        chess.G1 if color == chess.WHITE else chess.G8,
        chess.C1 if color == chess.WHITE else chess.C8,
    )


def king_ring_safety(board: chess.Board, color: chess.Color) -> int:
    king_square = board.king(color)
    if king_square is None:
        return 0
    attackers = len(board.attackers(not color, king_square))
    defenders = len(board.attackers(color, king_square))
    bonus = 6 if has_castled(board, color) else 0
    return defenders * 6 - attackers * 10 + bonus


def describe_move_features(
    board: chess.Board,
    move: chess.Move,
    before: PositionSnapshot,
    after: PositionSnapshot,
    position_needs: list[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    tags: list[str] = []
    reasons: list[str] = []
    warnings: list[str] = []
    priorities_addressed: list[str] = []
    piece = board.piece_at(move.from_square)
    if piece is None:
        return tags, reasons, warnings, priorities_addressed

    delta = build_move_delta(before, after)

    if board.is_capture(move):
        captured = board.piece_at(move.to_square)
        if captured:
            if PIECE_VALUES[captured.piece_type] >= PIECE_VALUES[piece.piece_type]:
                tags.append("safety")
            else:
                tags.append("initiative")
            reasons.append(f"changes the material balance by taking a {chess.piece_name(captured.piece_type)}.")
        else:
            tags.append("initiative")
            reasons.append("removes pressure with a capture.")

    if board.gives_check(move):
        tags.append("initiative")
        reasons.append("creates a forcing check.")

    if board.is_castling(move):
        tags.extend(["king_safety", "development"])
        priorities_addressed.append("king_safety")
        reasons.append("improves king safety by castling.")

    if delta.development_change > 0:
        tags.append("development")
        priorities_addressed.append("development")
        reasons.append("brings another minor piece into the game.")

    if delta.center_control_change >= 10 or move.to_square in (chess.D4, chess.E4, chess.D5, chess.E5):
        tags.append("center")
        priorities_addressed.append("center")
        reasons.append("improves control of the center.")

    if delta.safety_change > 0:
        tags.append("safety")
        priorities_addressed.append("safety")
        reasons.append("reduces tactical risk by improving piece safety.")
    elif delta.safety_change < -80:
        warnings.append("This move increases tactical risk and may leave something loose.")

    if delta.king_safety_change > 0:
        tags.append("king_safety")
        priorities_addressed.append("king_safety")
        reasons.append("makes your king harder to attack.")
    elif delta.king_safety_change < -6:
        warnings.append("Your king becomes a little easier to target after this move.")

    if delta.opponent_king_pressure_change > 0:
        tags.append("initiative")
        reasons.append("asks the opponent to solve king-safety problems.")

    if delta.mobility_change > 2 and "development" not in tags:
        tags.append("activity")
        priorities_addressed.append("activity")
        reasons.append("improves the activity of your pieces.")

    if before.material_balance_cp > 150 and board.is_capture(move):
        tags.append("conversion")
        priorities_addressed.append("conversion")
        reasons.append("helps simplify while you are already ahead.")

    if not tags:
        tags.append("activity")
        reasons.append("keeps the position stable while improving coordination.")

    priorities_addressed = [priority for priority in dict.fromkeys(priorities_addressed) if priority in position_needs]
    tags = list(dict.fromkeys(tags))
    reasons = list(dict.fromkeys(reasons))
    warnings = list(dict.fromkeys(warnings))
    return tags, reasons, warnings, priorities_addressed


def build_move_plan(tags: list[str], priorities_addressed: list[str], delta: MoveDelta) -> str:
    if priorities_addressed:
        priority = priorities_addressed[0].replace("_", " ")
        return f"Primary coaching goal: address {priority} first."
    if "initiative" in tags and delta.opponent_king_pressure_change > 0:
        return "Primary coaching goal: keep the initiative and make the opponent answer threats."
    if "activity" in tags:
        return "Primary coaching goal: improve your worst-placed piece."
    return "Primary coaching goal: keep improving pieces without creating new weaknesses."


def estimate_difficulty(
    board: chess.Board,
    move: chess.Move,
    score_cp: int,
    best_score_cp: int,
    delta: MoveDelta,
) -> float:
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
        if victim and PIECE_VALUES[piece.piece_type] > PIECE_VALUES[victim.piece_type]:
            difficulty += 1.4
    if board.is_castling(move):
        difficulty -= 0.4
    if delta.opponent_king_pressure_change > 0:
        difficulty += 0.4
    if delta.safety_change > 0:
        difficulty -= 0.2

    gap = max(0, best_score_cp - score_cp)
    difficulty += min(2.5, gap / 150.0)
    if move.to_square in (chess.D4, chess.E4, chess.D5, chess.E5):
        difficulty -= 0.2
    return max(0.4, difficulty)


def build_model_features(
    board: chess.Board,
    move: chess.Move,
    level: LevelProfile,
    *,
    score_cp: int,
    best_score_cp: int,
    difficulty: float,
    tags: list[str],
    priorities_addressed: list[str],
    delta: MoveDelta,
) -> dict[str, float]:
    return {
        "eval_gap": float(max(0, best_score_cp - score_cp)),
        "difficulty": float(difficulty),
        "safety_change": float(delta.safety_change),
        "center_change": float(delta.center_control_change),
        "king_safety_change": float(delta.king_safety_change),
        "development_change": float(delta.development_change),
        "mobility_change": float(delta.mobility_change),
        "material_change": float(delta.material_change_cp),
        "opponent_pressure_change": float(delta.opponent_king_pressure_change),
        "is_capture": float(board.is_capture(move)),
        "is_check": float(board.gives_check(move)),
        "is_castling": float(board.is_castling(move)),
        "num_preferred_tags": float(sum(1 for tag in tags if tag in level.preferred_tags)),
        "num_priorities": float(len(priorities_addressed)),
    }


def estimate_game_phase(board: chess.Board) -> str:
    non_pawn_material = sum(
        PIECE_VALUES[piece.piece_type]
        for piece in board.piece_map().values()
        if piece.piece_type not in (chess.KING, chess.PAWN)
    )
    if board.fullmove_number <= 10 and len(board.piece_map()) >= 24:
        return "opening"
    if non_pawn_material <= 2600:
        return "endgame"
    return "middlegame"


def allowed_bot_eval_gap(level: LevelProfile, phase: str) -> int:
    multiplier = BOT_EVAL_GAP_MULTIPLIERS.get(phase, BOT_EVAL_GAP_MULTIPLIERS["middlegame"]).get(level.key, 1.5)
    return max(level.max_eval_loss, int(level.max_eval_loss * multiplier))


def build_bot_candidate_pool(
    analysis: PositionAnalysis,
    board: chess.Board,
    level: LevelProfile,
    phase: str,
    adaptation: SessionBayesianAdapter | None = None,
) -> list[MoveInsight]:
    allowed_gap = allowed_bot_eval_gap(level, phase)
    pool_size = BOT_POOL_SIZE_BY_LEVEL[level.key]
    shortlisted = [
        candidate
        for candidate in analysis.candidates
        if analysis.best_move.score_cp - candidate.score_cp <= allowed_gap
    ]
    if analysis.tutor_move.move.uci() not in {candidate.move.uci() for candidate in shortlisted}:
        shortlisted.append(analysis.tutor_move)
    if analysis.best_move.move.uci() not in {candidate.move.uci() for candidate in shortlisted}:
        shortlisted.append(analysis.best_move)

    deduped: dict[str, MoveInsight] = {}
    for candidate in shortlisted:
        deduped[candidate.move.uci()] = candidate

    ranked = sorted(
        deduped.values(),
        key=lambda candidate: compute_bot_move_weight(
            board,
            candidate,
            analysis.best_move.score_cp,
            level,
            phase,
            adaptation=adaptation,
        ),
        reverse=True,
    )
    return ranked[: max(3, min(pool_size, len(ranked)))]


def compute_bot_move_weight(
    board: chess.Board,
    candidate: MoveInsight,
    best_score_cp: int,
    level: LevelProfile,
    phase: str,
    adaptation: SessionBayesianAdapter | None = None,
) -> float:
    human_weight = compute_human_move_choice_weight(
        board,
        candidate,
        best_score_cp,
        level,
        phase,
        model_features=candidate.model_features,
        adaptation=adaptation,
    )
    gap = max(0, best_score_cp - candidate.score_cp)
    allowed_gap = allowed_bot_eval_gap(level, phase)
    gap_ratio = gap / max(1.0, float(allowed_gap))
    practicality = max(0.08, 1.35 - gap_ratio)

    preferred_tags = sum(1 for tag in candidate.tags if tag in level.preferred_tags)
    tutor_alignment = 1.0 + min(1.5, max(-0.5, candidate.tutor_score / 120.0))
    weight = human_weight * practicality * tutor_alignment
    weight *= 1.0 + preferred_tags * 0.08

    if candidate.delta is not None and candidate.delta.safety_change < -80:
        weight *= 0.4
    if candidate.delta is not None and candidate.delta.development_change > 0 and phase == "opening":
        weight *= 1.12
    if board.is_castling(candidate.move):
        weight *= 1.2 if phase == "opening" else 1.08
    if board.gives_check(candidate.move) and level.key in {"600", "1000"}:
        weight *= 1.1
    if is_early_queen_move(board, candidate.move) and level.key in {"600", "1000"}:
        weight *= 0.45
    if candidate.difficulty > difficulty_cap_for_bot(level, phase):
        weight *= 0.5
    return max(0.05, weight)


def compute_human_move_choice_weight(
    board: chess.Board,
    candidate: MoveInsight,
    best_score_cp: int,
    level: LevelProfile,
    phase: str,
    *,
    model_features: dict[str, float] | None = None,
    adaptation: SessionBayesianAdapter | None = None,
) -> float:
    delta = candidate.delta or MoveDelta(
        material_change_cp=0,
        center_control_change=0,
        safety_change=0,
        development_change=0,
        king_safety_change=0,
        opponent_king_pressure_change=0,
        mobility_change=0,
    )
    features = model_features or build_model_features(
        board,
        candidate.move,
        level,
        score_cp=candidate.score_cp,
        best_score_cp=best_score_cp,
        difficulty=candidate.difficulty,
        tags=candidate.tags,
        priorities_addressed=candidate.priorities_addressed,
        delta=delta,
    )
    eval_gap = int(features["eval_gap"])
    num_preferred = int(features["num_preferred_tags"])
    params = learned_params.get_move_choice_params(level.key)

    if params is not None:
        coeff = params.coefficients
        raw_score = params.intercept
        raw_score += coeff.get("eval_gap", 0.0) * features["eval_gap"]
        raw_score += coeff.get("difficulty", 0.0) * features["difficulty"]
        raw_score += coeff.get("safety_change", 0.0) * features["safety_change"]
        raw_score += coeff.get("center_change", 0.0) * features["center_change"]
        raw_score += coeff.get("king_safety_change", 0.0) * features["king_safety_change"]
        raw_score += coeff.get("development_change", 0.0) * features["development_change"]
        raw_score += coeff.get("mobility_change", 0.0) * features["mobility_change"]
        raw_score += coeff.get("material_change", 0.0) * features["material_change"]
        raw_score += coeff.get("opponent_pressure_change", 0.0) * features["opponent_pressure_change"]
        raw_score += coeff.get("is_capture", 0.0) * features["is_capture"]
        raw_score += coeff.get("is_check", 0.0) * features["is_check"]
        raw_score += coeff.get("is_castling", 0.0) * features["is_castling"]
        raw_score += coeff.get("num_preferred_tags", 0.0) * features["num_preferred_tags"]
        raw_score += coeff.get("num_priorities", 0.0) * features["num_priorities"]
    else:
        raw_score = 0.0
        raw_score += 1.1 * features["is_capture"]
        raw_score += 1.5 * features["is_check"]
        raw_score += 1.2 * features["is_castling"]
        raw_score += 0.6 * features["development_change"]
        raw_score += 0.02 * features["safety_change"]
        raw_score += 0.01 * features["center_change"]
        raw_score += 0.03 * features["king_safety_change"]
        raw_score += 0.2 * num_preferred
        raw_score -= candidate.difficulty * max(0.18, level.complexity_weight / 80.0)
        raw_score -= eval_gap / 180.0

    if adaptation is not None:
        raw_score += adaptation.move_choice_adjustment(features)

    if phase == "opening":
        raw_score += 0.35 * delta.development_change
        raw_score += 0.45 * float(board.is_castling(candidate.move))
    if phase == "endgame" and "conversion" in candidate.tags:
        raw_score += 0.3
    if is_early_queen_move(board, candidate.move):
        raw_score -= 1.0 if level.key in {"600", "1000"} else 0.35

    return max(0.05, pow(2.718281828, max(-4.0, min(4.0, raw_score))))


def difficulty_cap_for_bot(level: LevelProfile, phase: str) -> float:
    base_caps = {
        "600": 1.7,
        "1000": 2.1,
        "1400": 2.7,
        "1800": 3.2,
    }
    phase_bonus = 0.2 if phase == "endgame" else 0.0
    return base_caps.get(level.key, 2.1) + phase_bonus


def is_early_queen_move(board: chess.Board, move: chess.Move) -> bool:
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.QUEEN:
        return False
    return board.fullmove_number <= 6 and not board.is_capture(move)


def compute_tutor_score(
    score_cp: int,
    best_score_cp: int,
    level: LevelProfile,
    tags: list[str],
    difficulty: float,
    priorities_addressed: list[str],
    delta: MoveDelta,
    *,
    model_features: dict[str, float] | None = None,
    adaptation: SessionBayesianAdapter | None = None,
) -> float:
    """
    Compute the teaching value of a move for a given skill level.

    Uses Bayesian-learned weights when available (Model B posterior means),
    falling back to handcrafted heuristic weights otherwise.
    """
    eval_gap = max(0, best_score_cp - score_cp)
    num_preferred = sum(1 for tag in tags if tag in level.preferred_tags)
    features = model_features or {
        "eval_gap": float(eval_gap),
        "num_preferred_tags": float(num_preferred),
        "num_priorities": float(len(priorities_addressed)),
        "safety_change": float(delta.safety_change),
        "king_safety_change": float(delta.king_safety_change),
        "center_change": float(delta.center_control_change),
        "opponent_pressure_change": float(delta.opponent_king_pressure_change),
        "difficulty": float(difficulty),
    }

    params = learned_params.get_tutor_score_params(level.key)
    if params is not None:
        # Use learned weights from Bayesian model
        w = params.weights
        score = params.intercept
        score += w.get("eval_gap", 0.0) * features["eval_gap"]
        score += w.get("num_preferred_tags", 0.0) * features["num_preferred_tags"]
        score += w.get("num_priorities", 0.0) * features["num_priorities"]
        score += w.get("safety_change", 0.0) * features["safety_change"]
        score += w.get("king_safety_change", 0.0) * features["king_safety_change"]
        score += w.get("center_change", 0.0) * features["center_change"]
        score += w.get("opponent_pressure_change", 0.0) * features["opponent_pressure_change"]
        score += w.get("difficulty", 0.0) * features["difficulty"]
        if adaptation is not None:
            score += 0.3 * adaptation.tutor_score_adjustment(features)
        # Scale to comparable range as heuristic (~0-200)
        return score * 100.0

    # Heuristic fallback (original hardcoded weights)
    eval_credit = max(0.0, 150.0 - float(eval_gap))
    preferred_bonus = sum(8.0 for tag in tags if tag in level.preferred_tags)
    priority_bonus = 12.0 * len(priorities_addressed)
    safety_bonus = max(0.0, delta.safety_change / 12.0)
    king_safety_bonus = max(0.0, delta.king_safety_change * 1.8)
    center_bonus = max(0.0, delta.center_control_change / 6.0)
    pressure_bonus = max(0.0, delta.opponent_king_pressure_change)
    complexity_penalty = difficulty * level.complexity_weight
    tactical_risk_penalty = max(0.0, -delta.safety_change / 8.0)
    king_risk_penalty = max(0.0, -delta.king_safety_change * 3.0)
    score = (
        eval_credit
        + preferred_bonus
        + priority_bonus
        + safety_bonus
        + king_safety_bonus
        + center_bonus
        + pressure_bonus
        - complexity_penalty
        - tactical_risk_penalty
        - king_risk_penalty
    )
    if adaptation is not None:
        score += 25.0 * adaptation.tutor_score_adjustment(features)
    return score
