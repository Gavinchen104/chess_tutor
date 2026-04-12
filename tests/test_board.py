import chess

from app.core.board import (
    board_to_editor_state,
    board_to_piece_map,
    build_board_from_editor_state,
    legal_move_uci_list,
    load_board,
    parse_move_text,
)


def test_load_board_from_fen():
    board = load_board("8/8/8/8/8/8/8/K6k w - - 0 1")
    assert board.piece_at(chess.A1).symbol() == "K"
    assert board.turn is chess.WHITE


def test_parse_move_text_accepts_san_and_uci():
    board = chess.Board()
    assert parse_move_text(board, "e4").move == chess.Move.from_uci("e2e4")
    assert parse_move_text(board, "g1f3").move == chess.Move.from_uci("g1f3")


def test_board_editor_state_round_trip_preserves_position_metadata():
    board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R b KQkq e3 4 12")
    editor_state = board_to_editor_state(board)

    rebuilt = build_board_from_editor_state(
        pieces=editor_state["pieces"],
        turn=editor_state["turn"],
        castling_rights=editor_state["castling_rights"],
        en_passant=editor_state["en_passant"],
        halfmove_clock=editor_state["halfmove_clock"],
        fullmove_number=editor_state["fullmove_number"],
    )

    assert rebuilt.fen() == board.fen()


def test_board_editor_rejects_invalid_positions():
    try:
        build_board_from_editor_state(
            pieces={"e1": "K"},
            turn="white",
            castling_rights=[],
            en_passant="",
            halfmove_clock=0,
            fullmove_number=1,
        )
    except ValueError as exc:
        assert "Invalid board setup" in str(exc)
    else:
        raise AssertionError("Expected invalid board setup to raise ValueError.")


def test_board_piece_map_and_legal_moves_helpers():
    board = chess.Board()
    piece_map = board_to_piece_map(board)
    legal_moves = legal_move_uci_list(board)

    assert piece_map["e1"] == "K"
    assert piece_map["d8"] == "q"
    assert "e2e4" in legal_moves
    assert "g1f3" in legal_moves
