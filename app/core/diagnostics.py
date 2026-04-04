from __future__ import annotations

from dataclasses import dataclass

import chess

from app.core.levels import LevelProfile
from app.core.move_engine import (
    MoveInsight,
    PIECE_VALUES,
    PositionAnalysis,
    PositionSnapshot,
    build_move_delta,
    count_developed_minor_pieces,
    has_castled,
)
from app.core.learned_params import learned_params
from app.core.reports import DiagnosticFinding


THEME_HABITS = {
    "safety": "Before moving, scan for loose pieces and undefended squares.",
    "development": "In the opening, improve undeveloped pieces before chasing side ideas.",
    "king_safety": "When the center can open, prioritize king safety before activity.",
    "center": "Ask which move improves control of e4, d4, e5, or d5.",
    "activity": "If nothing tactical works, improve your worst-placed piece.",
    "initiative": "When you have the initiative, choose forcing moves the opponent must answer.",
    "conversion": "When ahead, simplify only if the resulting position stays easy to win.",
    "tactics": "After every move, check captures, checks, and immediate threats for both sides.",
}

SEVERITY_SCORES = {
    "low": 10.0,
    "medium": 22.0,
    "high": 38.0,
}


@dataclass
class CaptureOpportunity:
    move: chess.Move
    captured_value: int
    moving_value: int
    undefended_target: bool
    favorable_trade: bool


@dataclass
class MoveDiagnostics:
    tactical_findings: list[DiagnosticFinding]
    strategic_findings: list[DiagnosticFinding]
    tactical_risk_score: float
    strategic_fit_score: float
    human_plausibility_score: float
    mistake_class: str
    primary_theme: str
    primary_reason: str
    training_habit: str


def analyze_move_diagnostics(
    board: chess.Board,
    insight: MoveInsight,
    analysis: PositionAnalysis,
    level: LevelProfile,
) -> MoveDiagnostics:
    before = analysis.snapshot or PositionSnapshot(
        material_balance_cp=0,
        center_control_balance=0,
        own_hanging_value=0,
        enemy_hanging_value=0,
        developed_minor_pieces=0,
        opponent_developed_minor_pieces=0,
        own_king_safety=0,
        opponent_king_safety=0,
        legal_moves=0,
        opponent_legal_moves=0,
        has_castled=False,
        opponent_has_castled=False,
    )
    next_board = board.copy(stack=False)
    next_board.push(insight.move)
    after = insight.snapshot or before
    delta = insight.delta or build_move_delta(before, after)

    tactical_findings = detect_tactical_findings(board, next_board, insight, analysis)
    strategic_findings = detect_strategic_findings(board, next_board, insight, analysis, level)

    tactical_risk_score = compute_directional_score(tactical_findings, direction="negative")
    strategic_fit_score = compute_directional_score(strategic_findings, direction="positive")
    if insight.priorities_addressed:
        strategic_fit_score += 8.0 * len(insight.priorities_addressed)
    if delta.safety_change > 0:
        strategic_fit_score += min(18.0, delta.safety_change / 10.0)

    eval_gap = max(0, analysis.best_move.score_cp - insight.score_cp)
    human_plausibility_score = compute_human_plausibility(
        eval_gap,
        insight.difficulty,
        tactical_risk_score,
        strategic_fit_score,
        level,
    )
    mistake_class = classify_move(eval_gap, tactical_risk_score, insight, analysis, level)
    primary_theme, primary_reason = pick_primary_message(
        tactical_findings,
        strategic_findings,
        insight,
        analysis,
    )
    training_habit = THEME_HABITS.get(primary_theme, THEME_HABITS["activity"])
    return MoveDiagnostics(
        tactical_findings=tactical_findings,
        strategic_findings=strategic_findings,
        tactical_risk_score=tactical_risk_score,
        strategic_fit_score=strategic_fit_score,
        human_plausibility_score=human_plausibility_score,
        mistake_class=mistake_class,
        primary_theme=primary_theme,
        primary_reason=primary_reason,
        training_habit=training_habit,
    )


def detect_tactical_findings(
    board: chess.Board,
    next_board: chess.Board,
    insight: MoveInsight,
    analysis: PositionAnalysis,
) -> list[DiagnosticFinding]:
    findings: list[DiagnosticFinding] = []
    before = analysis.snapshot
    after = insight.snapshot
    delta = insight.delta or (build_move_delta(before, after) if before and after else None)
    if before is None or after is None or delta is None:
        return findings

    player = board.turn
    best = analysis.best_move

    if after.own_hanging_value > before.own_hanging_value:
        findings.append(
            make_finding(
                category="tactical",
                code="hanging_own_piece",
                severity="high" if after.own_hanging_value - before.own_hanging_value >= 300 else "medium",
                direction="negative",
                theme="safety",
                summary="The move leaves more material hanging than before.",
            )
        )

    missed_capture = find_best_free_capture(board, player)
    if missed_capture and insight.move != missed_capture.move:
        findings.append(
            make_finding(
                category="tactical",
                code="missed_free_capture",
                severity="medium",
                direction="negative",
                theme="tactics",
                summary="A simpler free or favorable capture was available.",
            )
        )

    allowed_capture = find_best_free_capture(next_board, not player)
    if allowed_capture:
        findings.append(
            make_finding(
                category="tactical",
                code="allowed_free_capture",
                severity="high" if allowed_capture.captured_value >= PIECE_VALUES[chess.ROOK] else "medium",
                direction="negative",
                theme="safety",
                summary="The reply may allow the opponent to win material cleanly.",
            )
        )

    if best.score_cp >= 90000 and insight.score_cp < 90000:
        findings.append(
            make_finding(
                category="tactical",
                code="missed_forced_win",
                severity="high",
                direction="negative",
                theme="tactics",
                summary="A forcing winning line was available but not chosen.",
            )
        )
    elif board.gives_check(best.move) and not board.gives_check(insight.move) and best.score_cp - insight.score_cp >= 60:
        findings.append(
            make_finding(
                category="tactical",
                code="missed_forcing_check",
                severity="medium",
                direction="negative",
                theme="initiative",
                summary="A more forcing move was available and likely easier to play.",
            )
        )

    if opponent_has_forcing_reply(next_board, player):
        findings.append(
            make_finding(
                category="tactical",
                code="allowed_direct_threat",
                severity="medium",
                direction="negative",
                theme="safety",
                summary="The move gives the opponent an immediate forcing response.",
            )
        )

    if moved_same_opening_piece_too_often(board, insight.move):
        findings.append(
            make_finding(
                category="tactical",
                code="repeated_opening_piece",
                severity="low",
                direction="negative",
                theme="development",
                summary="The move spends another tempo on the same opening piece.",
            )
        )

    if before.own_king_safety < 10 and delta.king_safety_change <= 0 and not board.is_castling(insight.move):
        findings.append(
            make_finding(
                category="tactical",
                code="failed_to_address_king_danger",
                severity="medium",
                direction="negative",
                theme="king_safety",
                summary="The king was still under pressure and the move did not make it safer.",
            )
        )

    if attacked_high_value_piece_ignored(board, next_board, player, insight.move):
        findings.append(
            make_finding(
                category="tactical",
                code="ignored_attacked_high_value_piece",
                severity="medium",
                direction="negative",
                theme="safety",
                summary="A high-value piece was under pressure and not fully addressed.",
            )
        )

    if any(item.direction == "negative" for item in findings):
        return findings

    if board.is_capture(insight.move) and before.material_balance_cp > 150:
        findings.append(
            make_finding(
                category="tactical",
                code="simplified_while_winning",
                severity="low",
                direction="positive",
                theme="conversion",
                summary="The move simplifies the position while you are already ahead.",
            )
        )
    elif board.gives_check(insight.move):
        findings.append(
            make_finding(
                category="tactical",
                code="forcing_move",
                severity="low",
                direction="positive",
                theme="initiative",
                summary="The move keeps the initiative with a forcing idea.",
            )
        )

    return findings


def detect_strategic_findings(
    board: chess.Board,
    next_board: chess.Board,
    insight: MoveInsight,
    analysis: PositionAnalysis,
    level: LevelProfile,
) -> list[DiagnosticFinding]:
    findings: list[DiagnosticFinding] = []
    before = analysis.snapshot
    after = insight.snapshot
    delta = insight.delta or (build_move_delta(before, after) if before and after else None)
    if before is None or after is None or delta is None:
        return findings

    if delta.development_change > 0:
        findings.append(make_finding("strategic", "development_improved", "medium", "positive", "development", "The move improves development."))
    elif "development" in analysis.position_needs:
        findings.append(make_finding("strategic", "development_neglected", "low", "negative", "development", "The move does not solve the development problem yet."))

    if delta.center_control_change > 0:
        findings.append(make_finding("strategic", "center_improved", "medium", "positive", "center", "The move increases control of important central squares."))
    elif "center" in analysis.position_needs:
        findings.append(make_finding("strategic", "center_neglected", "low", "negative", "center", "The move leaves the center issue mostly unchanged."))

    if delta.king_safety_change > 0 or (not before.has_castled and has_castled(next_board, board.turn)):
        findings.append(make_finding("strategic", "king_safety_improved", "medium", "positive", "king_safety", "The move makes the king safer."))
    elif "king_safety" in analysis.position_needs:
        findings.append(make_finding("strategic", "king_safety_neglected", "medium", "negative", "king_safety", "The move delays king safety when it is still a priority."))

    if delta.mobility_change > 0:
        findings.append(make_finding("strategic", "activity_improved", "low", "positive", "activity", "The move improves piece activity and available options."))
    elif "activity" in analysis.position_needs:
        findings.append(make_finding("strategic", "activity_neglected", "low", "negative", "activity", "The move does not improve the worst-placed piece."))

    if before.material_balance_cp > 150 and reduces_non_pawn_material(board, next_board):
        findings.append(make_finding("strategic", "conversion", "low", "positive", "conversion", "The move simplifies in a way that is practical when ahead."))

    if move_complexity_mismatch(insight, level=level):
        findings.append(make_finding("strategic", "complexity_mismatch", "medium", "negative", "activity", "The move may be stronger than it is practical for the target rating to execute."))

    if worsened_endgame_structure(board, next_board, board.turn):
        findings.append(make_finding("strategic", "worse_endgame_structure", "medium", "negative", "conversion", "The trade leaves a less comfortable pawn structure for a simplified position."))

    return findings


def compute_directional_score(findings: list[DiagnosticFinding], direction: str) -> float:
    total = 0.0
    for finding in findings:
        if finding.direction == direction:
            total += SEVERITY_SCORES[finding.severity]
    return total


def compute_human_plausibility(
    eval_gap: int,
    difficulty: float,
    tactical_risk: float,
    strategic_fit: float,
    level: LevelProfile,
) -> float:
    """
    Estimate how likely a human at this level would play this move.

    Uses Bayesian-learned coefficients when available (Model A posterior means),
    falling back to handcrafted heuristic weights otherwise.
    """
    params = learned_params.get_move_choice_params(level.key)
    if params is not None:
        # Use learned coefficients from Bayesian model
        coeff = params.coefficients
        score = 100.0 + params.intercept
        score += coeff.get("eval_gap", 0.0) * eval_gap
        score += coeff.get("difficulty", 0.0) * difficulty
        # Map tactical_risk and strategic_fit to the closest learned features
        score += coeff.get("safety_change", 0.0) * (-tactical_risk)
        score += coeff.get("center_change", 0.0) * strategic_fit
        return max(0.0, min(100.0, score))

    # Heuristic fallback (original hardcoded weights)
    complexity_tolerance = {
        "600": 24.0,
        "1000": 18.0,
        "1400": 13.0,
        "1800": 9.0,
    }.get(level.key, 18.0)
    score = 100.0
    score -= min(45.0, eval_gap / 6.0)
    score -= max(0.0, difficulty * complexity_tolerance)
    score -= tactical_risk * 0.6
    score += strategic_fit * 0.35
    return max(0.0, min(100.0, score))


def classify_move(
    eval_gap: int,
    tactical_risk: float,
    insight: MoveInsight,
    analysis: PositionAnalysis,
    level: LevelProfile,
) -> str:
    if insight.move == analysis.best_move.move or eval_gap <= 15:
        return "best"
    if tactical_risk >= 55.0 or eval_gap > max(220, level.max_eval_loss * 3):
        return "blunder"
    if tactical_risk >= 30.0 or eval_gap > level.max_eval_loss * 2:
        return "mistake"
    if eval_gap > level.max_eval_loss:
        return "inaccuracy"
    return "practical"


def pick_primary_message(
    tactical_findings: list[DiagnosticFinding],
    strategic_findings: list[DiagnosticFinding],
    insight: MoveInsight,
    analysis: PositionAnalysis,
) -> tuple[str, str]:
    negative = [item for item in tactical_findings + strategic_findings if item.direction == "negative"]
    theme_priority = {"safety": 0, "king_safety": 1, "tactics": 2}
    negative.sort(
        key=lambda item: (
            theme_priority.get(item.theme, 3),
            -SEVERITY_SCORES[item.severity],
        )
    )
    if negative:
        return negative[0].theme, negative[0].summary
    if insight.priorities_addressed:
        theme = insight.priorities_addressed[0]
        for finding in strategic_findings:
            if finding.theme == theme and finding.direction == "positive":
                return theme, finding.summary
        return theme, f"The move directly improves {theme.replace('_', ' ')}."
    ranked = [item for item in tactical_findings + strategic_findings if item.direction == "positive"]
    ranked.sort(key=lambda item: (-SEVERITY_SCORES[item.severity], theme_priority.get(item.theme, 3)))
    if ranked:
        return ranked[0].theme, ranked[0].summary
    if insight.tags:
        theme = insight.tags[0]
        return theme, f"The move mainly supports {theme.replace('_', ' ')}."
    if analysis.position_needs:
        theme = analysis.position_needs[0]
        return theme, f"The move relates to {theme.replace('_', ' ')}."
    return "activity", "The move keeps the position playable."


def make_finding(
    category: str,
    code: str,
    severity: str,
    direction: str,
    theme: str,
    summary: str,
) -> DiagnosticFinding:
    return DiagnosticFinding(
        category=category,
        code=code,
        severity=severity,
        direction=direction,
        theme=theme,
        summary=summary,
        training_habit=THEME_HABITS.get(theme, THEME_HABITS["activity"]),
    )


def find_best_free_capture(board: chess.Board, color: chess.Color) -> CaptureOpportunity | None:
    opportunities = free_capture_opportunities(board, color)
    if not opportunities:
        return None
    opportunities.sort(
        key=lambda item: (
            item.captured_value - item.moving_value,
            item.undefended_target,
            item.captured_value,
        ),
        reverse=True,
    )
    return opportunities[0]


def free_capture_opportunities(board: chess.Board, color: chess.Color) -> list[CaptureOpportunity]:
    turn = board.turn
    board.turn = color
    try:
        legal_moves = list(board.legal_moves)
    finally:
        board.turn = turn

    opportunities: list[CaptureOpportunity] = []
    for move in legal_moves:
        if not board.is_capture(move):
            continue
        piece = board.piece_at(move.from_square)
        captured = board.piece_at(move.to_square)
        if piece is None or captured is None:
            continue
        defenders = len(board.attackers(not color, move.to_square))
        undefended = defenders == 0
        favorable = PIECE_VALUES[captured.piece_type] >= PIECE_VALUES[piece.piece_type]
        if undefended or favorable:
            opportunities.append(
                CaptureOpportunity(
                    move=move,
                    captured_value=PIECE_VALUES[captured.piece_type],
                    moving_value=PIECE_VALUES[piece.piece_type],
                    undefended_target=undefended,
                    favorable_trade=favorable,
                )
            )
    return opportunities


def opponent_has_forcing_reply(next_board: chess.Board, player_color: chess.Color) -> bool:
    opponent = not player_color
    turn = next_board.turn
    next_board.turn = opponent
    try:
        for reply in list(next_board.legal_moves):
            if next_board.gives_check(reply):
                return True
            if next_board.is_capture(reply):
                captured = next_board.piece_at(reply.to_square)
                if captured and PIECE_VALUES[captured.piece_type] >= PIECE_VALUES[chess.KNIGHT]:
                    return True
    finally:
        next_board.turn = turn
    return False


def moved_same_opening_piece_too_often(board: chess.Board, move: chess.Move) -> bool:
    piece = board.piece_at(move.from_square)
    if piece is None:
        return False
    if board.fullmove_number > 6:
        return False
    if piece.piece_type not in (chess.KNIGHT, chess.BISHOP, chess.QUEEN):
        return False
    if count_developed_minor_pieces(board, piece.color) >= 2:
        return False
    home_squares = {
        chess.WHITE: {chess.B1, chess.G1, chess.C1, chess.F1, chess.D1},
        chess.BLACK: {chess.B8, chess.G8, chess.C8, chess.F8, chess.D8},
    }
    return move.from_square not in home_squares[piece.color]


def attacked_high_value_piece_ignored(
    board: chess.Board,
    next_board: chess.Board,
    color: chess.Color,
    move: chess.Move,
) -> bool:
    targets_before = threatened_high_value_pieces(board, color)
    if not targets_before:
        return False
    targets_after = threatened_high_value_pieces(next_board, color)
    moved_from = move.from_square
    moved_to = move.to_square
    for square in targets_before:
        if square == moved_from and square not in targets_after:
            return False
        if square == moved_to and square not in targets_after:
            return False
    return bool(targets_after)


def threatened_high_value_pieces(board: chess.Board, color: chess.Color) -> list[chess.Square]:
    threatened: list[chess.Square] = []
    for square, piece in board.piece_map().items():
        if piece.color != color:
            continue
        if PIECE_VALUES[piece.piece_type] < PIECE_VALUES[chess.KNIGHT]:
            continue
        attackers = len(board.attackers(not color, square))
        defenders = len(board.attackers(color, square))
        if attackers and defenders <= attackers:
            threatened.append(square)
    return threatened


def reduces_non_pawn_material(board: chess.Board, next_board: chess.Board) -> bool:
    return non_pawn_material(next_board) < non_pawn_material(board)


def non_pawn_material(board: chess.Board) -> int:
    total = 0
    for piece in board.piece_map().values():
        if piece.piece_type != chess.PAWN:
            total += PIECE_VALUES[piece.piece_type]
    return total


def pawn_structure_score(board: chess.Board, color: chess.Color) -> int:
    files = {file_index: 0 for file_index in range(8)}
    pawns: list[chess.Square] = []
    for square, piece in board.piece_map().items():
        if piece.color == color and piece.piece_type == chess.PAWN:
            pawns.append(square)
            files[chess.square_file(square)] += 1

    score = 0
    for file_index, count in files.items():
        if count > 1:
            score -= (count - 1) * 12
    for square in pawns:
        file_index = chess.square_file(square)
        left = files.get(file_index - 1, 0)
        right = files.get(file_index + 1, 0)
        if left == 0 and right == 0:
            score -= 8
    return score


def worsened_endgame_structure(board: chess.Board, next_board: chess.Board, color: chess.Color) -> bool:
    if not reduces_non_pawn_material(board, next_board):
        return False
    return pawn_structure_score(next_board, color) + 14 < pawn_structure_score(board, color)


def move_complexity_mismatch(insight: MoveInsight, level: LevelProfile) -> bool:
    if level.elo <= 600:
        return insight.difficulty >= 2.0
    if level.elo <= 1000:
        return insight.difficulty >= 2.4
    if level.elo <= 1400:
        return insight.difficulty >= 2.8
    return insight.difficulty >= 3.2
