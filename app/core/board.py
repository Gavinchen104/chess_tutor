from __future__ import annotations

from dataclasses import dataclass

import chess
import chess.pgn
import chess.svg


START_FEN = chess.STARTING_FEN

STATUS_MESSAGES = (
    (chess.STATUS_NO_WHITE_KING, "White must have exactly one king."),
    (chess.STATUS_NO_BLACK_KING, "Black must have exactly one king."),
    (chess.STATUS_TOO_MANY_KINGS, "The board has too many kings."),
    (chess.STATUS_TOO_MANY_WHITE_PAWNS, "White has too many pawns."),
    (chess.STATUS_TOO_MANY_BLACK_PAWNS, "Black has too many pawns."),
    (chess.STATUS_PAWNS_ON_BACKRANK, "Pawns cannot be placed on the first or eighth rank."),
    (chess.STATUS_TOO_MANY_WHITE_PIECES, "White has too many pieces."),
    (chess.STATUS_TOO_MANY_BLACK_PIECES, "Black has too many pieces."),
    (chess.STATUS_BAD_CASTLING_RIGHTS, "Castling rights do not match the current king and rooks."),
    (chess.STATUS_INVALID_EP_SQUARE, "The en passant square is not legal for this position."),
    (chess.STATUS_OPPOSITE_CHECK, "Both sides cannot be giving check at the same time."),
    (chess.STATUS_EMPTY, "The board cannot be empty."),
)


@dataclass
class ParsedMove:
    move: chess.Move
    san: str


def load_board(fen: str | None = None) -> chess.Board:
    if not fen:
        return chess.Board()
    return chess.Board(fen)


def board_to_editor_state(board: chess.Board) -> dict:
    return {
        "pieces": {
            chess.square_name(square): piece.symbol()
            for square, piece in board.piece_map().items()
        },
        "turn": "white" if board.turn else "black",
        "castling_rights": list(board.castling_xfen()) if board.castling_xfen() != "-" else [],
        "en_passant": chess.square_name(board.ep_square) if board.ep_square is not None else "",
        "halfmove_clock": board.halfmove_clock,
        "fullmove_number": board.fullmove_number,
    }


def build_board_from_editor_state(
    *,
    pieces: dict[str, str],
    turn: str,
    castling_rights: list[str],
    en_passant: str,
    halfmove_clock: int,
    fullmove_number: int,
) -> chess.Board:
    board = chess.Board(None)

    for square_name, symbol in pieces.items():
        if not symbol:
            continue
        board.set_piece_at(chess.parse_square(square_name), chess.Piece.from_symbol(symbol))

    board.turn = chess.WHITE if turn.lower() == "white" else chess.BLACK
    board.set_castling_fen("".join(castling_rights) or "-")
    board.ep_square = chess.parse_square(en_passant) if en_passant else None
    board.halfmove_clock = max(0, int(halfmove_clock))
    board.fullmove_number = max(1, int(fullmove_number))

    validate_board_setup(board)
    return board


def validate_board_setup(board: chess.Board) -> None:
    status = board.status()
    if status == chess.STATUS_VALID:
        return

    errors = [message for flag, message in STATUS_MESSAGES if status & flag]
    detail = " ".join(errors) if errors else "Please check the kings, castling rights, and legality of the position."
    raise ValueError(f"Invalid board setup. {detail}")


def parse_move_text(board: chess.Board, move_text: str) -> ParsedMove:
    candidate = move_text.strip()
    if not candidate:
        raise ValueError("Enter a move in SAN or UCI format.")

    parsers = (
        lambda: board.parse_san(candidate),
        lambda: chess.Move.from_uci(candidate),
    )
    for parser in parsers:
        try:
            move = parser()
        except ValueError:
            continue
        if move in board.legal_moves:
            san = board.san(move)
            return ParsedMove(move=move, san=san)
    raise ValueError(f"'{move_text}' is not a legal move in this position.")


def render_board_svg(
    board: chess.Board,
    *,
    lastmove: chess.Move | None = None,
    orientation: chess.Color = chess.WHITE,
    size: int = 420,
) -> str:
    return chess.svg.board(
        board=board,
        lastmove=lastmove,
        orientation=orientation,
        size=size,
    )


def export_pgn_from_moves(moves: list[chess.Move], headers: dict[str, str] | None = None) -> str:
    game = chess.pgn.Game()
    game.headers["Event"] = "Chess Tutor Session"
    if headers:
        for key, value in headers.items():
            game.headers[key] = value
    node = game
    board = chess.Board()
    for move in moves:
        if move not in board.legal_moves:
            break
        node = node.add_variation(move)
        board.push(move)
    return str(game)


def extract_pgn_movetext(pgn_text: str) -> str:
    parts = pgn_text.strip().split("\n\n", 1)
    if len(parts) == 2:
        return parts[1].strip()
    return ""
