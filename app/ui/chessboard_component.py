from __future__ import annotations

from pathlib import Path

import chess
import streamlit.components.v1 as components

from app.core.board import board_to_piece_map, legal_move_uci_list


_COMPONENT_DIR = Path(__file__).resolve().parent / "components" / "drag_board"
_drag_board = components.declare_component("drag_board", path=str(_COMPONENT_DIR))


def interactive_chessboard(
    board: chess.Board,
    *,
    key: str,
    orientation: chess.Color = chess.WHITE,
    last_move_uci: str | None = None,
    disabled: bool = False,
    board_size: int = 420,
    height: int = 470,
) -> dict | None:
    return _drag_board(
        pieces=board_to_piece_map(board),
        legal_moves=legal_move_uci_list(board),
        orientation="white" if orientation else "black",
        last_move_uci=last_move_uci,
        disabled=disabled,
        board_size=board_size,
        height=height,
        key=key,
        default=None,
    )
