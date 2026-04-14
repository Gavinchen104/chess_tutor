from __future__ import annotations

from pathlib import Path
from typing import cast

import chess
import streamlit as st

from analysis.generate_appendix_report import build_appendix_report
from analysis.user_feedback import (
    DEFAULT_FEEDBACK_PATH,
    FEEDBACK_FIELDS,
    append_feedback_entry,
    load_feedback_entries,
    summarize_feedback,
)
from app.core.board import (
    START_FEN,
    board_to_editor_state,
    build_board_from_editor_state,
    export_pgn_from_moves,
    extract_pgn_movetext,
    load_board,
    parse_move_text,
)
from app.core.adaptation import SessionBayesianAdapter
from app.core.levels import LEVELS, get_level
from app.core.tutor import ChessTutor
from app.ui.chessboard_component import interactive_chessboard


EXAMPLE_FENS = {
    "Starting position": START_FEN,
    "Simple tactics": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/3P1N2/PPP2PPP/RNBQKB1R w KQkq - 2 4",
    "Castling lesson": "r1bq1rk1/pppp1ppp/2n2n2/4p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 6 6",
    "Endgame conversion": "8/5pk1/3p2p1/2pP4/2P1P3/6P1/5P1P/6K1 w - - 0 1",
}

ANALYSIS_RESULTS_DIR = Path(__file__).resolve().parents[2] / "analysis" / "results"
BOARD_EDITOR_SQUARES = [chess.square_name(square) for square in chess.SQUARES]
CASTLING_OPTIONS = ["K", "Q", "k", "q"]
PIECE_CHOICES = [
    ("Empty", ""),
    ("White King", "K"),
    ("White Queen", "Q"),
    ("White Rook", "R"),
    ("White Bishop", "B"),
    ("White Knight", "N"),
    ("White Pawn", "P"),
    ("Black King", "k"),
    ("Black Queen", "q"),
    ("Black Rook", "r"),
    ("Black Bishop", "b"),
    ("Black Knight", "n"),
    ("Black Pawn", "p"),
]
PIECE_LABEL_TO_SYMBOL = dict(PIECE_CHOICES)
PIECE_SYMBOL_TO_LABEL = {symbol: label for label, symbol in PIECE_CHOICES}


def apply_custom_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Spectral:wght@500;600&display=swap');

        :root {
            --bg-soft: #0b1219;
            --surface: #121b25;
            --ink: #e8f1f7;
            --muted: #9bb2c3;
            --accent: #1ec8ab;
            --accent-strong: #149984;
            --line: #273543;
            --gold: #f0b35a;
        }

        .stApp {
            background:
                radial-gradient(circle at 10% 15%, rgba(30, 200, 171, 0.16) 0%, transparent 38%),
                radial-gradient(circle at 90% 10%, rgba(240, 179, 90, 0.14) 0%, transparent 35%),
                linear-gradient(180deg, #0a1118 0%, #0f1722 100%);
            color: var(--ink);
            font-family: 'Space Grotesk', sans-serif;
        }

        .stApp p,
        .stApp label,
        .stApp span,
        .stApp div {
            color: var(--ink);
        }

        h1, h2, h3 {
            font-family: 'Spectral', serif !important;
            color: #f3f8fc;
            letter-spacing: 0.2px;
        }

        .ui-hero {
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 1.2rem 1.4rem 1.1rem 1.4rem;
            background: linear-gradient(120deg, rgba(30,200,171,0.13), rgba(240,179,90,0.12));
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.35);
            margin-bottom: 1rem;
            animation: fadeSlideIn 450ms ease-out;
        }

        .ui-hero h1 {
            margin: 0;
            font-size: 2rem;
            line-height: 1.15;
        }

        .ui-hero p {
            margin: 0.45rem 0 0 0;
            color: var(--muted);
            font-size: 0.98rem;
        }

        .ui-section {
            margin-top: 0.35rem;
            margin-bottom: 0.35rem;
            padding: 0.2rem 0.1rem;
            border-left: 4px solid var(--accent);
            padding-left: 0.7rem;
            animation: fadeSlideIn 500ms ease-out;
        }

        .ui-section .title {
            font-family: 'Spectral', serif;
            font-size: 1.18rem;
            color: #dff2ff;
            margin: 0;
        }

        .ui-section .subtitle {
            margin: 0.15rem 0 0 0;
            font-size: 0.9rem;
            color: var(--muted);
        }

        .stButton > button {
            border-radius: 10px;
            border: 1px solid #2b4b58;
            background: linear-gradient(180deg, #132130 0%, #172838 100%);
            color: #d9edf7;
            font-weight: 600;
            transition: all 180ms ease;
        }

        .stButton > button:hover {
            border-color: var(--accent);
            color: #f0fffb;
            transform: translateY(-1px);
            box-shadow: 0 10px 22px rgba(30, 200, 171, 0.24);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #111a24 0%, #0f1721 100%);
            border-right: 1px solid var(--line);
        }

        [data-testid="stMetricValue"] {
            color: #59e2c7;
            font-weight: 700;
        }

        [data-testid="stMetricLabel"] {
            color: #9cc1d4;
        }

        [data-testid="stDataFrame"] {
            border: 1px solid var(--line);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);
        }

        [data-testid="stCodeBlock"] {
            border-radius: 10px;
            border: 1px solid #304252;
        }

        .stTextInput input,
        .stTextArea textarea,
        .stNumberInput input,
        .stSelectbox div[data-baseweb="select"] > div,
        .stMultiSelect div[data-baseweb="select"] > div {
            background-color: #111b26 !important;
            color: #e6f2fa !important;
            border-color: #2c3f4f !important;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.85rem;
            padding: 0.25rem 0.1rem 0.45rem 0.1rem;
            margin-bottom: 0.35rem;
        }

        .stTabs [data-baseweb="tab"] {
            background: #121d2a;
            border: 1px solid #243646;
            border-radius: 10px 10px 0 0;
            color: #bdd3e2;
            padding: 0.55rem 1.1rem;
            min-width: 220px;
            justify-content: center;
            letter-spacing: 0.2px;
        }

        .stTabs [aria-selected="true"] {
            background: #183347;
            color: #ecf7ff;
            border-bottom-color: #183347;
            box-shadow: 0 10px 18px rgba(0, 0, 0, 0.22);
        }

        .stAlert {
            border-radius: 12px;
        }

        @keyframes fadeSlideIn {
            from {
                opacity: 0;
                transform: translateY(5px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @media (max-width: 900px) {
            .ui-hero h1 {
                font-size: 1.55rem;
            }
            .ui-hero p {
                font-size: 0.9rem;
            }

            .stTabs [data-baseweb="tab-list"] {
                gap: 0.4rem;
                overflow-x: auto;
                padding-bottom: 0.25rem;
            }

            .stTabs [data-baseweb="tab"] {
                min-width: 150px;
                padding: 0.5rem 0.75rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero_header() -> None:
    st.markdown(
        """
        <div class="ui-hero">
            <h1>Chess Tutor</h1>
            <p>Play, analyze, and review with level-aware coaching that favors learnable decisions over raw engine dumps.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title: str, subtitle: str = "") -> None:
    subtitle_html = f"<p class='subtitle'>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f"""
        <div class="ui-section">
            <p class="title">{title}</p>
            {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def run() -> None:
    st.set_page_config(page_title="Chess Tutor", page_icon="♟️", layout="wide")
    apply_custom_theme()
    render_hero_header()
    initialize_state()

    with st.sidebar:
        st.header("Session")
        level_key = st.selectbox("Target ELO", options=list(LEVELS.keys()), format_func=lambda key: LEVELS[key].label)
        level = get_level(level_key)
        adapter = get_session_adapter(level_key)
        tutor = ChessTutor(adapter=adapter)
        st.write(level.description)
        st.write(f"Commentary style: {level.commentary_style}")
        render_live_bayesian_sidebar(adapter, level)
        if st.button("Reset Position Analyzer"):
            st.session_state.analysis_fen = START_FEN
            st.session_state.analysis_last_move = None
        if st.button("New Bot Game"):
            reset_bot_game()
        if st.button("Reset Live Bayesian State"):
            st.session_state.live_bayesian_adapters[level_key] = SessionBayesianAdapter.for_level(level_key)
            adapter = st.session_state.live_bayesian_adapters[level_key]
            tutor = ChessTutor(adapter=adapter)
            st.session_state.analysis_report = None
            st.success("Live Bayesian adaptation reset for this rating band.")

    tab_analysis, tab_play, tab_story = st.tabs(
        ["Position Analyzer", "Play Against Bot", "Evaluation Story"]
    )

    with tab_analysis:
        render_position_analyzer(tutor, level)

    with tab_play:
        render_play_mode(tutor, level)

    with tab_story:
        render_evaluation_story(level, adapter)


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
    st.session_state.setdefault("evaluation_report_bundle", None)
    st.session_state.setdefault("live_bayesian_adapters", {})
    st.session_state.setdefault("analysis_last_drag_event", None)
    st.session_state.setdefault("bot_last_drag_event", None)
    if "editor_pieces" not in st.session_state:
        sync_editor_state_from_fen(START_FEN)


def get_session_adapter(level_key: str) -> SessionBayesianAdapter:
    adapters: dict[str, SessionBayesianAdapter] = st.session_state.live_bayesian_adapters
    if level_key not in adapters:
        adapters[level_key] = SessionBayesianAdapter.for_level(level_key)
    return adapters[level_key]


def render_live_bayesian_sidebar(adapter: SessionBayesianAdapter, level) -> None:
    summary = adapter.summary(level)
    st.subheader("Live Bayesian State")
    st.caption("Session-level posterior updates sit on top of the trained model priors.")
    st.write(f"Inferred practical level: about {summary['estimated_elo']}")
    st.write(f"Current preference trend: {str(summary['preferred_theme']).replace('_', ' ')}")
    st.write(f"Confidence: {summary['confidence']}")
    st.caption(
        f"Observations: {summary['move_observations']} move choices, "
        f"{summary['feedback_observations']} feedback entries"
    )


@st.cache_data(show_spinner=False)
def run_offline_evaluation_suite(output_dir: str) -> dict:
    return build_appendix_report(Path(output_dir))


def maybe_handle_dragged_move(
    payload: dict | None,
    *,
    event_state_key: str,
) -> str | None:
    if not payload or "uci" not in payload or "event_id" not in payload:
        return None
    if st.session_state.get(event_state_key) == payload["event_id"]:
        return None
    st.session_state[event_state_key] = payload["event_id"]
    return str(payload["uci"])


def render_position_analyzer(tutor: ChessTutor, level) -> None:
    render_section_header("Position Analyzer", "Set up any legal position and ask for level-aware coaching.")
    left, right = st.columns([1.3, 1.0], gap="large")

    with left:
        selected_example = st.selectbox("Example positions", options=list(EXAMPLE_FENS.keys()))
        if st.button("Load Example"):
            set_analysis_position(EXAMPLE_FENS[selected_example])

        render_board_editor()

        fen = st.text_area("FEN", value=st.session_state.analysis_fen, height=100) or ""
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
            dragged = interactive_chessboard(
                board,
                key="analysis_drag_board",
                orientation=board.turn,
                last_move_uci=st.session_state.analysis_last_move,
            )
            st.code(f"Side to move: {'White' if board.turn else 'Black'}")
            st.caption("Drag a piece on the interactive board to evaluate that move instantly.")
            dragged_uci = maybe_handle_dragged_move(dragged, event_state_key="analysis_last_drag_event")
            if dragged_uci:
                current_fen = cast(str, st.session_state.analysis_fen)
                evaluate_probe_move(tutor, current_fen, dragged_uci, level)
                st.rerun()
        except ValueError as exc:
            st.error(f"Invalid FEN: {exc}")

    report = st.session_state.analysis_report
    if report:
        render_section_header("Tutor Advice")
        st.write(report["overview"])
        st.info(report["tutor_explanation"])

        candidate_rows = []
        for candidate in report["candidates"]:
            candidate_rows.append(
                {
                    "Move": candidate.san,
                    "Score": candidate.score_cp / 100,
                    "Tutor Fit": round(candidate.tutor_score, 1),
                    "Difficulty": round(candidate.difficulty, 2),
                    "Theme": candidate.primary_theme,
                    "Mistake Class": candidate.mistake_class,
                    "Human Plausibility": round(candidate.human_plausibility_score, 1),
                }
            )
        st.dataframe(candidate_rows, use_container_width=True)
        st.caption(report["evaluation_story"])
        st.caption(f"Analysis source: {report['engine_provider']}")
        render_analysis_feedback_form(report, get_session_adapter(level.key))


def analyze_position(tutor: ChessTutor, fen: str, level) -> None:
    try:
        board = load_board(fen)
        report = tutor.analyze_position(board, level)
    except ValueError as exc:
        st.error(str(exc))
        return

    st.session_state.analysis_report = {
        "board_fen": report.board_fen,
        "level_key": report.level_key,
        "level_label": report.level_label,
        "overview": report.overview,
        "tutor_explanation": report.tutor_explanation,
        "evaluation_story": report.evaluation_story,
        "best_move": report.engine_best_move,
        "tutor_move": report.tutor_move,
        "candidates": report.candidate_moves,
        "engine_provider": report.engine_metadata.provider,
    }


def render_board_editor() -> None:
    with st.expander("Board Setup Editor", expanded=False):
        st.caption("Use the editor to place pieces, choose whose turn it is, and apply the setup without writing FEN.")

        control_cols = st.columns(4)
        with control_cols[0]:
            if st.button("Sync From FEN", use_container_width=True):
                try:
                    sync_editor_state_from_fen(st.session_state.analysis_fen)
                except ValueError as exc:
                    st.error(str(exc))
        with control_cols[1]:
            if st.button("Apply Editor", use_container_width=True):
                apply_editor_position()
        with control_cols[2]:
            if st.button("Clear Board", use_container_width=True):
                clear_editor_board()
        with control_cols[3]:
            if st.button("Start Position", use_container_width=True):
                set_analysis_position(START_FEN)

        placement_cols = st.columns([1, 1.4, 1, 1])
        with placement_cols[0]:
            square_name = st.selectbox("Square", options=BOARD_EDITOR_SQUARES, key="editor_selected_square")
        with placement_cols[1]:
            piece_label = st.selectbox("Piece", options=[label for label, _ in PIECE_CHOICES], key="editor_selected_piece")
        with placement_cols[2]:
            if st.button("Place Piece", use_container_width=True):
                st.session_state.editor_pieces[square_name] = PIECE_LABEL_TO_SYMBOL[piece_label]
        with placement_cols[3]:
            if st.button("Clear Square", use_container_width=True):
                st.session_state.editor_pieces[square_name] = ""

        meta_cols = st.columns(2)
        with meta_cols[0]:
            st.radio(
                "Side to move",
                options=["white", "black"],
                format_func=lambda item: item.title(),
                horizontal=True,
                key="editor_turn",
            )
            st.multiselect(
                "Castling rights",
                options=CASTLING_OPTIONS,
                key="editor_castling_rights",
            )
        with meta_cols[1]:
            st.text_input(
                "En passant square",
                placeholder="Leave blank if none",
                key="editor_en_passant",
            )
            st.number_input(
                "Halfmove clock",
                min_value=0,
                step=1,
                key="editor_halfmove_clock",
            )
            st.number_input(
                "Fullmove number",
                min_value=1,
                step=1,
                key="editor_fullmove_number",
            )

        st.caption("Placed pieces")
        st.dataframe(build_editor_piece_rows(st.session_state.editor_pieces), use_container_width=True, hide_index=True)


def build_editor_piece_rows(pieces: dict[str, str]) -> list[dict[str, str]]:
    rows = [
        {"Square": square_name, "Piece": PIECE_SYMBOL_TO_LABEL[symbol]}
        for square_name, symbol in sorted(pieces.items())
        if symbol
    ]
    return rows or [{"Square": "(empty)", "Piece": "No pieces placed"}]


def clear_editor_board() -> None:
    st.session_state.editor_pieces = {square_name: "" for square_name in BOARD_EDITOR_SQUARES}
    st.session_state.editor_turn = "white"
    st.session_state.editor_castling_rights = []
    st.session_state.editor_en_passant = ""
    st.session_state.editor_halfmove_clock = 0
    st.session_state.editor_fullmove_number = 1
    st.session_state.analysis_report = None
    st.session_state.analysis_last_move = None


def sync_editor_state_from_fen(fen: str) -> None:
    board = load_board(fen)
    editor_state = board_to_editor_state(board)
    st.session_state.editor_pieces = {
        square_name: editor_state["pieces"].get(square_name, "")
        for square_name in BOARD_EDITOR_SQUARES
    }
    st.session_state.editor_turn = editor_state["turn"]
    st.session_state.editor_castling_rights = editor_state["castling_rights"]
    st.session_state.editor_en_passant = editor_state["en_passant"]
    st.session_state.editor_halfmove_clock = editor_state["halfmove_clock"]
    st.session_state.editor_fullmove_number = editor_state["fullmove_number"]


def apply_editor_position() -> None:
    try:
        board = build_board_from_editor_state(
            pieces=st.session_state.editor_pieces,
            turn=st.session_state.editor_turn,
            castling_rights=list(st.session_state.editor_castling_rights),
            en_passant=st.session_state.editor_en_passant.strip(),
            halfmove_clock=int(st.session_state.editor_halfmove_clock),
            fullmove_number=int(st.session_state.editor_fullmove_number),
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    set_analysis_position(board.fen())
    st.success("Board setup applied to the analyzer.")


def set_analysis_position(fen: str) -> None:
    st.session_state.analysis_fen = fen
    st.session_state.analysis_report = None
    st.session_state.analysis_last_move = None
    sync_editor_state_from_fen(fen)


def evaluate_probe_move(tutor: ChessTutor, fen: str, move_text: str, level) -> None:
    try:
        board = load_board(fen)
        parsed = parse_move_text(board, move_text)
        coaching = tutor.coach_player_move(board, parsed.move, level)
        report = tutor.analyze_position(board, level)
    except ValueError as exc:
        st.error(str(exc))
        return

    st.session_state.analysis_last_move = parsed.move.uci()
    st.session_state.analysis_report = {
        "board_fen": report.board_fen,
        "level_key": report.level_key,
        "level_label": report.level_label,
        "overview": f"{coaching.verdict}: {coaching.lesson}",
        "tutor_explanation": (
            f"You played `{coaching.chosen_move.san}`. Strongest move: `{coaching.engine_best_move.san}`. "
            f"Tutor move for this level: `{coaching.tutor_move.san}`."
        ),
        "evaluation_story": report.evaluation_story,
        "best_move": report.engine_best_move,
        "tutor_move": report.tutor_move,
        "candidates": report.candidate_moves,
        "engine_provider": report.engine_metadata.provider,
    }
    get_session_adapter(level.key).observe_move_choice(
        coaching.chosen_move.model_features,
        tutor_features=coaching.tutor_move.model_features,
        eval_gap_cp=coaching.score_delta_cp,
        difficulty=coaching.chosen_move.difficulty,
        tactical_risk_score=coaching.chosen_move.tactical_risk_score,
        mistake_class=coaching.chosen_move.mistake_class,
        level=level,
    )


def render_analysis_feedback_form(report: dict, adapter: SessionBayesianAdapter) -> None:
    render_section_header("Quick Feedback")
    st.caption("Save a short rating for this analysis so the project can collect lightweight usefulness evidence.")

    with st.form(key=f"analysis_feedback_{report['level_key']}"):
        clarity = st.slider("Clarity", min_value=1, max_value=5, value=4, help="Was the advice easy to understand?")
        usefulness = st.slider("Usefulness", min_value=1, max_value=5, value=4, help="Was it more useful than raw engine output?")
        actionability = st.slider("Actionability", min_value=1, max_value=5, value=4, help="Did it suggest something concrete to do?")
        overwhelm_reduction = st.slider(
            "Overwhelm Reduction",
            min_value=1,
            max_value=5,
            value=4,
            help="Did it reduce confusion compared with a raw engine line dump?",
        )
        notes = st.text_area("Optional Notes", placeholder="What felt helpful or unhelpful about this advice?")
        submitted = st.form_submit_button("Save Feedback", use_container_width=True)

    if not submitted:
        return

    append_feedback_entry(
        {
            "source": "position_analyzer",
            "level_key": report["level_key"],
            "level_label": report["level_label"],
            "board_fen": report["board_fen"],
            "engine_provider": report["engine_provider"],
            "engine_move": report["best_move"].san,
            "tutor_move": report["tutor_move"].san,
            "clarity": clarity,
            "usefulness": usefulness,
            "actionability": actionability,
            "overwhelm_reduction": overwhelm_reduction,
            "notes": notes.strip(),
        }
    )
    adapter.observe_feedback(
        report["tutor_move"].model_features,
        {
            "clarity": clarity,
            "usefulness": usefulness,
            "actionability": actionability,
            "overwhelm_reduction": overwhelm_reduction,
        },
    )
    st.success("Feedback saved locally.")


def render_play_mode(tutor: ChessTutor, level) -> None:
    render_section_header("Play Against Bot", "Face a practical bot tuned for your selected ELO profile.")
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
    expected_user_turn = (board.turn == chess.WHITE and st.session_state.bot_user_color == "White") or (
        board.turn == chess.BLACK and st.session_state.bot_user_color == "Black"
    )
    dragged = interactive_chessboard(
        board,
        key="play_drag_board",
        orientation=orientation,
        last_move_uci=st.session_state.bot_last_move_uci,
        disabled=board.is_game_over() or not expected_user_turn,
    )
    st.code("Moves: " + (" ".join(st.session_state.bot_moves) or "(none yet)"))
    st.caption("You can drag a piece on the board or type SAN/UCI below.")

    dragged_uci = maybe_handle_dragged_move(dragged, event_state_key="bot_last_drag_event")
    if dragged_uci:
        submit_player_move(tutor, level, dragged_uci)
        st.rerun()

    if board.is_game_over():
        outcome = board.outcome()
        termination_name = outcome.termination.name if outcome is not None else "UNKNOWN"
        st.success(f"Game over: {board.result()} ({termination_name})")
    else:
        move_text = st.text_input("Your move", key="bot_move_input", placeholder="e.g. e4, Nf3, or e2e4")
        if st.button("Submit Move", use_container_width=True):
            submit_player_move(tutor, level, move_text)

    render_section_header("Live Commentary")
    for line in st.session_state.bot_commentary[-8:]:
        st.write(f"- {line}")

    render_section_header("Post-game Review")
    pgn = export_pgn_from_moves(
        [chess.Move.from_uci(uci) for uci in st.session_state.bot_moves],
        headers={"White": "Human" if st.session_state.bot_user_color == "White" else "Tutor Bot",
                 "Black": "Human" if st.session_state.bot_user_color == "Black" else "Tutor Bot"},
    )
    review = tutor.review_game(st.session_state.bot_feedback, pgn)
    for finding in review.critical_moments:
        st.write(f"- {finding}")
    for finding in review.recurring_patterns:
        st.write(f"- {finding}")
    for strength in review.strengths:
        st.write(f"- {strength}")
    if review.next_steps:
        st.caption("What To Work On Next: " + "; ".join(review.next_steps))
    st.caption(review.summary)
    movetext = extract_pgn_movetext(review.pgn)
    st.code("Moves: " + (movetext or "(no moves yet)"))
    st.text_area("Full PGN", value=review.pgn, height=260)


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
        coaching = tutor.coach_player_move(board, parsed.move, level)
    except ValueError as exc:
        st.error(str(exc))
        return

    board.push(parsed.move)
    st.session_state.bot_moves.append(parsed.move.uci())
    st.session_state.bot_last_move_uci = parsed.move.uci()
    st.session_state.bot_board_fen = board.fen()
    st.session_state.bot_feedback.append(coaching)
    st.session_state.bot_commentary.append(
        f"You played {coaching.chosen_move.san}: {coaching.verdict}. {coaching.lesson}"
    )
    get_session_adapter(level.key).observe_move_choice(
        coaching.chosen_move.model_features,
        tutor_features=coaching.tutor_move.model_features,
        eval_gap_cp=coaching.score_delta_cp,
        difficulty=coaching.chosen_move.difficulty,
        tactical_risk_score=coaching.chosen_move.tactical_risk_score,
        mistake_class=coaching.chosen_move.mistake_class,
        level=level,
    )

    if board.is_game_over():
        st.rerun()
        return

    bot_move = tutor.choose_bot_move(board, level)
    bot_move_obj = chess.Move.from_uci(bot_move.uci)
    board.push(bot_move_obj)
    st.session_state.bot_moves.append(bot_move.uci)
    st.session_state.bot_last_move_uci = bot_move.uci
    st.session_state.bot_board_fen = board.fen()
    st.session_state.bot_commentary.append(
        f"Bot replies with {bot_move.san}: {bot_move.player_friendly_explanation}"
    )
    st.rerun()


def maybe_make_opening_bot_move(tutor: ChessTutor, level) -> None:
    board = load_board(st.session_state.bot_board_fen)
    if board.move_stack:
        return
    bot_is_white = st.session_state.bot_user_color == "Black"
    if not bot_is_white:
        return
    bot_move = tutor.choose_bot_move(board, level)
    bot_move_obj = chess.Move.from_uci(bot_move.uci)
    board.push(bot_move_obj)
    st.session_state.bot_moves.append(bot_move.uci)
    st.session_state.bot_last_move_uci = bot_move.uci
    st.session_state.bot_board_fen = board.fen()
    st.session_state.bot_commentary.append(
        f"Bot opens with {bot_move.san}: {bot_move.player_friendly_explanation}"
    )


def render_evaluation_story(level, adapter: SessionBayesianAdapter) -> None:
    render_section_header("Evaluation Story", "Understand why tutor recommendations differ from pure engine output.")
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

    render_section_header("Offline Evaluation Suite")
    st.write(
        "The app can also surface the offline benchmark suite used in the appendix. "
        "This checks whether tutor recommendations satisfy level-appropriate properties and whether "
        "post-game reviews detect the right weaknesses and next steps."
    )

    if st.button("Run Offline Evaluation Suite", use_container_width=True):
        with st.spinner("Running position and review benchmarks..."):
            st.session_state.evaluation_report_bundle = run_offline_evaluation_suite(str(ANALYSIS_RESULTS_DIR))

    bundle = st.session_state.evaluation_report_bundle
    if not bundle:
        st.caption("Run the suite to load benchmark metrics, case results, and generated appendix files.")
    else:
        summary = bundle["summary"]
        positions_report = bundle["positions_report"]
        reviews_report = bundle["reviews_report"]

        pos_col, review_col = st.columns(2)
        with pos_col:
            st.metric("Position Benchmarks", positions_report["benchmark_count"])
        with review_col:
            st.metric("Review Benchmarks", reviews_report["benchmark_count"])

        render_metric_table("Position Metrics", positions_report["metrics"])
        render_metric_table("Review Metrics", reviews_report["metrics"])

        render_section_header("Position Benchmark Cases")
        st.dataframe(
            [
                {
                    "Label": case["label"],
                    "Passed": case["passed"],
                    "Level": case.get("level_key", ""),
                    "Tutor Move": case.get("tutor_move", ""),
                    "Engine Move": case.get("engine_best_move", ""),
                    "Primary Theme": case.get("primary_theme", ""),
                    "Eval Gap": case.get("eval_gap_cp", ""),
                    "Difficulty": case.get("difficulty", ""),
                    "Explanation OK": case.get("explanation_complete", ""),
                }
                for case in positions_report["cases"]
            ],
            use_container_width=True,
        )

        render_section_header("Review Benchmark Cases")
        st.dataframe(
            [
                {
                    "Label": case["label"],
                    "Passed": case["passed"],
                    "Level": case.get("level_key", ""),
                    "Weakness Detection": case.get("weakness_detection_pass", ""),
                    "Next Step Actionable": case.get("next_step_actionability_pass", ""),
                    "Annotation Consistent": case.get("annotation_consistency_pass", ""),
                    "Annotated Themes": ", ".join(case.get("annotated_themes", [])),
                }
                for case in reviews_report["cases"]
            ],
            use_container_width=True,
        )

        with st.expander("Generated Appendix Files"):
            for label, path in summary["generated_files"].items():
                st.code(f"{label}: {path}")

    render_user_feedback_summary()
    render_live_bayesian_story(adapter, level)


def render_live_bayesian_story(adapter: SessionBayesianAdapter, level) -> None:
    summary = adapter.summary(level)
    render_section_header("Live Bayesian Adaptation")
    st.write(
        "The app starts from the trained Bayesian priors for this ELO band, then maintains a session-level posterior "
        "that updates from your move choices and saved feedback."
    )
    story_rows = [
        {"Signal": "Estimated Practical Level", "Value": summary["estimated_elo"]},
        {"Signal": "Preference Trend", "Value": str(summary["preferred_theme"]).replace("_", " ").title()},
        {"Signal": "Confidence", "Value": summary["confidence"]},
        {"Signal": "Move Observations", "Value": summary["move_observations"]},
        {"Signal": "Feedback Observations", "Value": summary["feedback_observations"]},
        {"Signal": "Adjusted Complexity Weight", "Value": f"{summary['adjusted_complexity_weight']:.2f}"},
        {"Signal": "Adjusted Max Eval Loss", "Value": summary["adjusted_max_eval_loss"]},
    ]
    st.dataframe(story_rows, use_container_width=True, hide_index=True)


def render_metric_table(title: str, metrics: dict[str, float]) -> None:
    st.caption(title)
    st.dataframe(
        [
            {
                "Metric": metric_name.replace("_", " ").title(),
                "Value": format_metric_value(metric_name, value),
            }
            for metric_name, value in metrics.items()
        ],
        use_container_width=True,
        hide_index=True,
    )


def format_metric_value(metric_name: str, value: float) -> str:
    if "rate" in metric_name:
        return f"{value * 100:.1f}%"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"


def render_user_feedback_summary() -> None:
    entries = load_feedback_entries()
    summary = summarize_feedback(entries)

    render_section_header("User Feedback Evidence")
    st.caption(f"Stored at: {DEFAULT_FEEDBACK_PATH}")
    if summary["count"] == 0:
        st.caption("No saved user feedback yet. Submit a few ratings from the Position Analyzer to build anecdotal evidence.")
        return

    count_col, avg_col = st.columns(2)
    with count_col:
        st.metric("Saved Responses", summary["count"])
    with avg_col:
        avg_usefulness = summary["averages"].get("usefulness", 0.0)
        st.metric("Average Usefulness", f"{avg_usefulness:.2f} / 5")

    st.caption("Feedback Averages")
    st.dataframe(
        [
            {"Metric": field.replace("_", " ").title(), "Average": f"{summary['averages'][field]:.2f} / 5"}
            for field in FEEDBACK_FIELDS
            if field in summary["averages"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.caption("Responses By Level")
    st.dataframe(
        [
            {"Level": level_key, "Responses": count}
            for level_key, count in sorted(summary["by_level"].items())
        ],
        use_container_width=True,
        hide_index=True,
    )

    if summary["recent_notes"]:
        st.caption("Recent Notes")
        for note in summary["recent_notes"]:
            st.write(f"- [{note['level_key']}] {note['notes']}")


def reset_bot_game() -> None:
    st.session_state.bot_board_fen = START_FEN
    st.session_state.bot_moves = []
    st.session_state.bot_last_move_uci = None
    st.session_state.bot_commentary = []
    st.session_state.bot_feedback = []
