from __future__ import annotations

from dataclasses import dataclass

import chess
import chess.pgn
import chess.svg


START_FEN = chess.STARTING_FEN


@dataclass
class ParsedMove:
    move: chess.Move
    san: str


def load_board(fen: str | None = None) -> chess.Board:
    if not fen:
        return chess.Board()
    return chess.Board(fen)


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
