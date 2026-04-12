import chess

from app.core.levels import get_level
from app.core.move_engine import MoveEngine, compute_bot_move_weight, estimate_game_phase


def test_move_engine_returns_candidates():
    board = chess.Board()
    analysis = MoveEngine().analyze(board, get_level("1000"))
    assert analysis.candidates
    assert analysis.best_move.san
    assert analysis.tutor_move.san


def test_move_engine_identifies_opening_priorities():
    board = chess.Board()
    analysis = MoveEngine().analyze(board, get_level("600"))
    assert "development" in analysis.position_needs
    assert analysis.tutor_move.plan


def test_low_level_bot_penalizes_early_queen_moves_more_than_high_level_bot(monkeypatch):
    # Learned move-choice weights can dominate the ratio; this test targets handcrafted bot heuristics.
    monkeypatch.setattr(
        "app.core.move_engine.learned_params.get_move_choice_params",
        lambda _elo: None,
    )
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    engine = MoveEngine()
    phase = estimate_game_phase(board)

    low_level = get_level("600")
    low_analysis = engine.analyze(board, low_level)
    low_queen = engine.inspect_move(
        board,
        board.parse_san("Qh5"),
        low_level,
        best_score_cp=low_analysis.best_move.score_cp,
        position_snapshot=low_analysis.snapshot,
        position_needs=low_analysis.position_needs,
    )
    low_knight = engine.inspect_move(
        board,
        board.parse_san("Nf3"),
        low_level,
        best_score_cp=low_analysis.best_move.score_cp,
        position_snapshot=low_analysis.snapshot,
        position_needs=low_analysis.position_needs,
    )

    high_level = get_level("1800")
    high_analysis = engine.analyze(board, high_level)
    high_queen = engine.inspect_move(
        board,
        board.parse_san("Qh5"),
        high_level,
        best_score_cp=high_analysis.best_move.score_cp,
        position_snapshot=high_analysis.snapshot,
        position_needs=high_analysis.position_needs,
    )
    high_knight = engine.inspect_move(
        board,
        board.parse_san("Nf3"),
        high_level,
        best_score_cp=high_analysis.best_move.score_cp,
        position_snapshot=high_analysis.snapshot,
        position_needs=high_analysis.position_needs,
    )

    low_queen_weight = compute_bot_move_weight(board, low_queen, low_analysis.best_move.score_cp, low_level, phase)
    low_knight_weight = compute_bot_move_weight(board, low_knight, low_analysis.best_move.score_cp, low_level, phase)
    high_queen_weight = compute_bot_move_weight(board, high_queen, high_analysis.best_move.score_cp, high_level, phase)
    high_knight_weight = compute_bot_move_weight(board, high_knight, high_analysis.best_move.score_cp, high_level, phase)

    assert low_knight_weight > low_queen_weight
    assert (high_queen_weight / high_knight_weight) > (low_queen_weight / low_knight_weight)


def test_castling_gets_opening_bonus_for_practical_bot_play():
    board = chess.Board("r1bqk2r/pppp1ppp/2n2n2/4p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R w KQkq - 4 5")
    engine = MoveEngine()
    level = get_level("600")
    analysis = engine.analyze(board, level)
    phase = estimate_game_phase(board)

    castle = engine.inspect_move(
        board,
        board.parse_san("O-O"),
        level,
        best_score_cp=analysis.best_move.score_cp,
        position_snapshot=analysis.snapshot,
        position_needs=analysis.position_needs,
    )
    quiet = engine.inspect_move(
        board,
        board.parse_san("h3"),
        level,
        best_score_cp=analysis.best_move.score_cp,
        position_snapshot=analysis.snapshot,
        position_needs=analysis.position_needs,
    )

    assert compute_bot_move_weight(board, castle, analysis.best_move.score_cp, level, phase) > compute_bot_move_weight(
        board,
        quiet,
        analysis.best_move.score_cp,
        level,
        phase,
    )


def test_estimate_game_phase_identifies_endgame_positions():
    board = chess.Board("8/5pk1/3p2p1/2pP4/2P1P3/6P1/5P1P/6K1 w - - 0 1")
    assert estimate_game_phase(board) == "endgame"
