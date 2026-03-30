from __future__ import annotations

from dataclasses import asdict

import chess
import streamlit as st

from app.core.board import START_FEN, export_pgn_from_moves, load_board, parse_move_text, render_board_svg
from app.core.levels import LEVELS, get_level
from app.core.tutor import ChessTutor


EXAMPLE_FENS = {
    "Starting position": START_FEN,
    "Simple tactics": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/3P1N2/PPP2PPP/RNBQKB1R w KQkq - 2 4",
    "Castling lesson": "r1bq1rk1/pppp1ppp/2n2n2/4p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 6 6",
    "Endgame conversion": "8/5pk1/3p2p1/2pP4/2P1P3/6P1/5P1P/6K1 w - - 0 1",
}


def run() -> None:
    st.set_page_config(page_title="Chess Tutor", page_icon="♟️", layout="wide")
    st.title("Chess Tutor")
    st.caption("Skill-aware chess feedback built for novice-to-intermediate players.")

    tutor = ChessTutor()
    initialize_state()

    with st.sidebar:
        st.header("Session")
        level_key = st.selectbox("Target ELO", options=list(LEVELS.keys()), format_func=lambda key: LEVELS[key].label)
        level = get_level(level_key)
        st.write(level.description)
        st.write(f"Commentary style: {level.commentary_style}")
        if st.button("Reset Position Analyzer"):
            st.session_state.analysis_fen = START_FEN
            st.session_state.analysis_last_move = None
        if st.button("New Bot Game"):
            reset_bot_game()

    tab_analysis, tab_play, tab_story = st.tabs(
        ["Position Analyzer", "Play Against Bot", "Evaluation Story"]
    )

    with tab_analysis:
        render_position_analyzer(tutor, level)

    with tab_play:
        render_play_mode(tutor, level)

    with tab_story:
        render_evaluation_story(level)


def initialize_state() -> None:
    st.session_state.setdefault("analysis_fen", START_FEN)
    st.session_state.setdefault("analysis_last_move", None)
    st.session_state.setdefault("analysis_report", None)
    st.session_state.setdefault("bot_board_fen", START_FEN)
    st.session_state.setdefault("bot_moves", [])
    st.session_state.setdefault("bot_last_move_uci", None)
    st.session_state.setdefault("bot_commentary", [])
    st.session_state.setdefault("bot_feedback", [])
    st.session_state.setdefault("bot_user_color", "White")


def render_board(board: chess.Board, last_move_uci: str | None, orientation: chess.Color) -> None:
    last_move = chess.Move.from_uci(last_move_uci) if last_move_uci else None
    svg = render_board_svg(board, lastmove=last_move, orientation=orientation)
    st.markdown(svg, unsafe_allow_html=True)


def render_position_analyzer(tutor: ChessTutor, level) -> None:
    st.subheader("Set up a position")
    left, right = st.columns([1.3, 1.0], gap="large")

    with left:
        selected_example = st.selectbox("Example positions", options=list(EXAMPLE_FENS.keys()))
        if st.button("Load Example"):
            st.session_state.analysis_fen = EXAMPLE_FENS[selected_example]
            st.session_state.analysis_report = None
            st.session_state.analysis_last_move = None

        fen = st.text_area("FEN", value=st.session_state.analysis_fen, height=100)
        st.session_state.analysis_fen = fen

        move_probe = st.text_input("Optional: test a move in SAN or UCI", placeholder="e.g. Nf3 or e2e4")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Analyze Position", use_container_width=True):
                analyze_position(tutor, fen, level)
        with col_b:
            if st.button("Evaluate My Move", use_container_width=True):
                evaluate_probe_move(tutor, fen, move_probe, level)

    with right:
        try:
            board = load_board(st.session_state.analysis_fen)
            render_board(board, st.session_state.analysis_last_move, board.turn)
            st.code(f"Side to move: {'White' if board.turn else 'Black'}")
        except ValueError as exc:
            st.error(f"Invalid FEN: {exc}")

    report = st.session_state.analysis_report
    if report:
        st.subheader("Tutor Advice")
        st.write(report["overview"])
        st.info(report["tutor_explanation"])

        candidate_rows = []
        for candidate in report["candidates"]:
            candidate_rows.append(
                {
                    "Move": candidate["san"],
                    "Score": candidate["score_cp"] / 100,
                    "Tutor Fit": round(candidate["tutor_score"], 1),
                    "Difficulty": round(candidate["difficulty"], 2),
                    "Themes": ", ".join(candidate["tags"]),
                }
            )
        st.dataframe(candidate_rows, use_container_width=True)
        st.caption(report["evaluation_story"])


def analyze_position(tutor: ChessTutor, fen: str, level) -> None:
    try:
        board = load_board(fen)
        report = tutor.analyze_position(board, level)
    except ValueError as exc:
        st.error(str(exc))
        return

    st.session_state.analysis_report = {
        "overview": report.overview,
        "tutor_explanation": report.tutor_explanation,
        "evaluation_story": report.evaluation_story,
        "best_move": asdict(report.analysis.best_move),
        "tutor_move": asdict(report.analysis.tutor_move),
        "candidates": [asdict(item) for item in report.analysis.candidates],
    }


def evaluate_probe_move(tutor: ChessTutor, fen: str, move_text: str, level) -> None:
    try:
        board = load_board(fen)
        parsed = parse_move_text(board, move_text)
        feedback, report = tutor.coach_player_move(board, parsed.move, level)
    except ValueError as exc:
        st.error(str(exc))
        return

    st.session_state.analysis_last_move = parsed.move.uci()
    st.session_state.analysis_report = {
        "overview": f"{feedback.verdict}: {feedback.lesson}",
        "tutor_explanation": (
            f"You played `{feedback.chosen_san}`. Strongest move: `{feedback.best_san}`. "
            f"Tutor move for this level: `{feedback.tutor_san}`."
        ),
        "evaluation_story": report.evaluation_story,
        "best_move": asdict(report.analysis.best_move),
        "tutor_move": asdict(report.analysis.tutor_move),
        "candidates": [asdict(item) for item in report.analysis.candidates],
    }


def render_play_mode(tutor: ChessTutor, level) -> None:
    st.subheader("Play against a level-aware bot")
    controls = st.columns([1, 1, 1])
    with controls[0]:
        st.session_state.bot_user_color = st.selectbox("Play as", options=["White", "Black"], key="bot_color_select")
    with controls[1]:
        if st.button("Restart Game", use_container_width=True):
            reset_bot_game()
    with controls[2]:
        if st.button("Bot Makes First Move", use_container_width=True):
            maybe_make_opening_bot_move(tutor, level)

    board = load_board(st.session_state.bot_board_fen)
    orientation = chess.WHITE if st.session_state.bot_user_color == "White" else chess.BLACK
    render_board(board, st.session_state.bot_last_move_uci, orientation)
    st.code("Moves: " + (" ".join(st.session_state.bot_moves) or "(none yet)"))

    if board.is_game_over():
        st.success(f"Game over: {board.result()} ({board.outcome().termination.name})")
    else:
        move_text = st.text_input("Your move", key="bot_move_input", placeholder="e.g. e4, Nf3, or e2e4")
        if st.button("Submit Move", use_container_width=True):
            submit_player_move(tutor, level, move_text)

    st.subheader("Live Commentary")
    for line in st.session_state.bot_commentary[-8:]:
        st.write(f"- {line}")

    st.subheader("Post-game Review")
    pgn = export_pgn_from_moves(
        [chess.Move.from_uci(uci) for uci in st.session_state.bot_moves],
        headers={"White": "Human" if st.session_state.bot_user_color == "White" else "Tutor Bot",
                 "Black": "Human" if st.session_state.bot_user_color == "Black" else "Tutor Bot"},
    )
    review = tutor.review_game(st.session_state.bot_feedback, pgn)
    for finding in review.findings:
        st.write(f"- {finding}")
    st.caption(review.summary)
    st.text_area("PGN", value=review.pgn, height=180)


def submit_player_move(tutor: ChessTutor, level, move_text: str) -> None:
    board = load_board(st.session_state.bot_board_fen)
    expected_user_turn = (board.turn == chess.WHITE and st.session_state.bot_user_color == "White") or (
        board.turn == chess.BLACK and st.session_state.bot_user_color == "Black"
    )
    if not expected_user_turn:
        st.warning("It is the bot's turn.")
        return

    try:
        parsed = parse_move_text(board, move_text)
        feedback, report = tutor.coach_player_move(board, parsed.move, level)
    except ValueError as exc:
        st.error(str(exc))
        return

    board.push(parsed.move)
    st.session_state.bot_moves.append(parsed.move.uci())
    st.session_state.bot_last_move_uci = parsed.move.uci()
    st.session_state.bot_board_fen = board.fen()
    st.session_state.bot_feedback.append(feedback)
    st.session_state.bot_commentary.append(
        f"You played {feedback.chosen_san}: {feedback.verdict}. {feedback.lesson}"
    )

    if board.is_game_over():
        return

    bot_move = tutor.choose_bot_move(board, level)
    board.push(bot_move.move)
    st.session_state.bot_moves.append(bot_move.move.uci())
    st.session_state.bot_last_move_uci = bot_move.move.uci()
    st.session_state.bot_board_fen = board.fen()
    st.session_state.bot_commentary.append(
        f"Bot replies with {bot_move.san}: {' '.join(bot_move.reasons[:2])}"
    )


def maybe_make_opening_bot_move(tutor: ChessTutor, level) -> None:
    board = load_board(st.session_state.bot_board_fen)
    if board.move_stack:
        return
    bot_is_white = st.session_state.bot_user_color == "Black"
    if not bot_is_white:
        return
    bot_move = tutor.choose_bot_move(board, level)
    board.push(bot_move.move)
    st.session_state.bot_moves.append(bot_move.move.uci())
    st.session_state.bot_last_move_uci = bot_move.move.uci()
    st.session_state.bot_board_fen = board.fen()
    st.session_state.bot_commentary.append(
        f"Bot opens with {bot_move.san}: {' '.join(bot_move.reasons[:2])}"
    )


def render_evaluation_story(level) -> None:
    st.subheader("Why this is more useful than raw engine output")
    st.write(
        "A raw engine answers 'what is strongest?' This tutor adds a second question: "
        f"'what is strongest that a {level.elo}-level player can actually learn from and execute?'"
    )
    st.write(
        "The app ranks legal moves twice: once by evaluation and once by tutor fit. Tutor fit rewards practical "
        "themes like development, safety, center control, and king safety, while penalizing lines that demand "
        "heavy calculation at lower ratings."
    )
    st.write(
        "That gives you a compact demo story for the report: the tutor does not replace tactical truth, "
        "it filters truth into advice that is more actionable for novice-to-intermediate players."
    )


def reset_bot_game() -> None:
    st.session_state.bot_board_fen = START_FEN
    st.session_state.bot_moves = []
    st.session_state.bot_last_move_uci = None
    st.session_state.bot_commentary = []
    st.session_state.bot_feedback = []
