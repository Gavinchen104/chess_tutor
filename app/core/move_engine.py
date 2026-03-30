from __future__ import annotations

from dataclasses import dataclass, field
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
    def __init__(self) -> None:
        self.stockfish_path = find_stockfish_path()

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
        short_list = analysis.candidates[: max(3, min(6, len(analysis.candidates)))]
        weights = []
        for candidate in short_list:
            gap = analysis.best_move.score_cp - candidate.score_cp
            if gap > level.max_eval_loss * 2:
                continue
            weight = max(0.5, candidate.tutor_score)
            if "safety" in candidate.tags:
                weight += 6.0
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
        tutor_score = compute_tutor_score(
            score,
            baseline,
            level,
            tags,
            difficulty,
            priorities_addressed,
            delta,
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


def compute_tutor_score(
    score_cp: int,
    best_score_cp: int,
    level: LevelProfile,
    tags: list[str],
    difficulty: float,
    priorities_addressed: list[str],
    delta: MoveDelta,
) -> float:
    eval_gap = max(0, best_score_cp - score_cp)
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
    return (
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
