import chess

from app.core.board import load_board, parse_move_text


def test_load_board_from_fen():
    board = load_board("8/8/8/8/8/8/8/K6k w - - 0 1")
    assert board.piece_at(chess.A1).symbol() == "K"
    assert board.turn is chess.WHITE


def test_parse_move_text_accepts_san_and_uci():
    board = chess.Board()
    assert parse_move_text(board, "e4").move == chess.Move.from_uci("e2e4")
    assert parse_move_text(board, "g1f3").move == chess.Move.from_uci("g1f3")
