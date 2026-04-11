# chess_tutor

Teammate: Zhihan Chen

## Overview

This repository contains an interactive chess tutor backend and demo app designed around the project brief shown in class: build a chess teacher that is more helpful for novice-to-intermediate players than a raw chess engine.

The current implementation is no longer just a UI prototype. It now includes a structured backend for:

- position analysis
- move-by-move coaching
- post-game review
- benchmark-style evaluation

The system is designed around a simple but important idea:

- a strong engine answers "what is best?"
- a tutor should also answer "what is most useful for this player's level?"

This project therefore separates:

- chess rules and board state
- engine-backed move evaluation and candidate generation
- tactical/strategic diagnostics
- tutoring commentary and skill-aware feedback
- review and evaluation reporting

That separation makes the code easier to understand, easier to test, and easier to improve later.

## Project Goal

The goal of this project is not just to recommend the strongest move. It is to provide advice that is:

- interpretable for the player
- matched to a target ELO level
- actionable during analysis or play
- easier to learn from than a stock engine line dump

To support that goal, the tutor ranks moves in multiple ways:

- `engine strength`: how good the move is in centipawn terms
- `tutor fit`: how appropriate the move is for a selected rating band
- `tactical risk`: how likely the move is to create immediate practical problems
- `human plausibility`: how realistic and teachable the move is for the target player

This allows the app to sometimes recommend a move that is slightly weaker than the top engine move if it is much easier to understand and execute for the chosen skill level.

## Implemented Features

This repo now contains an end-to-end chess tutor system aimed at the A+ rubric in the project brief:

- Position analyzer where a user can load a FEN and choose a target ELO.
- Play-against-bot mode with live commentary and a post-game review.
- Level-aware move suggestions that are not limited to raw best-engine moves.
- A built-in "engine vs tutor" explanation so you can argue that the tutor is more useful for novice-to-intermediate players.
- Structured tactical and strategic detectors for move feedback.
- A local benchmark/evaluation harness for comparing tutor behavior across positions and games.

The app uses `python-chess` for rules, board state, SVG board rendering, PGN export, and UCI engine integration. If a Stockfish binary is available through `STOCKFISH_EXECUTABLE` or on the system path, the tutor uses it as the tactical truth layer by default. If not, it falls back to a heuristic evaluator so the demo still runs cleanly.

## Why This Is More Than A Raw Engine

A raw engine normally gives:

- the best move
- an evaluation
- maybe a top line

That is useful for strong players, but it can be overwhelming for beginners.

This tutor adds a second layer on top of evaluation:

- it rewards safe, teachable moves at lower ratings
- it penalizes overly difficult moves for lower ratings
- it explicitly diagnoses issues like hanging pieces, missed free captures, king-safety neglect, development neglect, and complexity mismatch
- it explains moves using themes like development, king safety, center control, safety, initiative, and conversion
- it produces structured coaching outputs instead of only raw move suggestions

This is the main argument for the report: the tutor does not replace tactical truth, it translates tactical truth into more practical coaching.

## Technology Stack

- `Python`
- `Streamlit` for the web interface
- `python-chess` for board state, move legality, FEN parsing, SAN/UCI parsing, SVG board rendering, and PGN export
- `Stockfish` integration through UCI when available
- `pytest` for basic testing

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd chess_tutor
```

### 2. Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

### 3. Launch the app

```bash
python3 -m streamlit run app/main.py
```

Streamlit will print a local URL such as:

```text
http://localhost:8501
```

Open that in your browser.

### 4. Optional but recommended: connect Stockfish

If you have a Stockfish binary installed, you can point the app to it:

```bash
export STOCKFISH_EXECUTABLE=/path/to/stockfish
python3 -m streamlit run app/main.py
```

If no Stockfish binary is found, the app still works by using the built-in heuristic evaluator, but Stockfish is the preferred analysis source for stronger tactical truth.

## Quick Start Demo

If you want the fastest way to show the project in class:

1. Start the app.
2. Go to `Position Analyzer`.
3. Load an example position or use the board setup editor.
4. Choose `600`, `1000`, `1400`, or `1800` in the sidebar.
5. Click `Analyze Position`.
6. Show that the tutor may recommend a move that is more teachable than the top engine move.
7. Go to `Play Against Bot`.
8. Play a few moves and point out the live commentary.
9. Go to `Evaluation Story` and run the offline evaluation suite.
10. Show the PGN, post-game lessons, and saved user feedback evidence.

## Interface Overview

The web app has three main tabs.

### 1. Position Analyzer

This tab is designed for the assignment requirement that the user should be able to set up a position and request feedback for a pre-specified ELO.

What you can do:

- paste a FEN
- set up a position with the board editor
- load a built-in example position
- choose a target ELO in the sidebar
- analyze the position
- enter your own move and ask the tutor to evaluate it

What the app shows:

- the board
- the side to move
- the tutor's recommended move
- the strongest move found
- a short educational explanation
- a candidate move table with score, difficulty, mistake class, primary theme, and human-plausibility score
- a short "engine vs tutor" explanation

### 2. Play Against Bot

This tab lets the user play an interactive game against a level-aware bot.

What you can do:

- choose White or Black
- restart the game
- let the bot make the first move when appropriate
- input moves in SAN or UCI

What the app shows:

- the current board
- move history
- live commentary after your move
- a bot reply chosen from practical candidate moves
- a post-game review with critical moments, recurring patterns, strengths, and next steps
- PGN output for the game

### 3. Evaluation Story

This tab is included to make the grading argument explicit.

It explains that:

- raw engine output optimizes only for strength
- the tutor adds practicality for a target rating
- slightly weaker but easier moves can be more educational
- helpful explanations matter for novice-to-intermediate players
- the offline benchmark suite and saved feedback provide evidence for the report

## ELO Levels

The app currently supports four rating buckets:

- `600 - Foundations`
- `1000 - Improving`
- `1400 - Club Player`
- `1800 - Advanced Club`

Each level changes:

- what move themes are preferred
- how much complexity is tolerated
- how much evaluation loss is acceptable for a more teachable move
- the wording style of commentary

For example:

- `600` focuses more on safety, simple threats, and basic development
- `1000` mixes simple tactics with core opening principles
- `1400` allows stronger tactical choices when still practical
- `1800` stays much closer to the strongest engine move

## Architecture

The code is intentionally organized in three layers.

### 1. Chess Rules And State

Files:

- `app/core/board.py`

Responsibilities:

- load boards from FEN
- parse SAN and UCI moves
- render the board as SVG
- export PGN from played moves

### 2. Decision-Making, Diagnostics, And Move Ranking

Files:

- `app/core/move_engine.py`
- `app/core/levels.py`
- `app/core/diagnostics.py`
- `app/core/reports.py`

Responsibilities:

- detect and use Stockfish when available
- fall back to heuristic analysis when Stockfish is unavailable
- evaluate legal moves
- estimate move difficulty
- assign tactical and strategic findings such as hanging pieces, missed captures, repeated opening tempi, ignored attacked pieces, development, center control, and king safety
- compute tactical risk, strategic fit, and human-plausibility scores
- produce stable report types for analysis, coaching, review, and evaluation

### 3. Tutoring And Commentary

Files:

- `app/core/services.py`
- `app/core/tutor.py`
- `app/core/commentary.py`
- `app/core/evaluator.py`

Responsibilities:

- expose explicit service layers:
  - `AnalysisService`
  - `PlayCoachingService`
  - `ReviewService`
- turn move analysis into plain-English summaries
- generate `PositionAnalysisReport`, `MoveCoachingReport`, and `GameReviewReport`
- build move-by-move coaching and post-game lessons

### 4. Web Interface

Files:

- `app/main.py`
- `app/ui/streamlit_app.py`

Responsibilities:

- create the Streamlit layout
- manage session state
- connect the tutor logic to the user interface
- display boards, tables, commentary, and PGN output

## Backend Report Types

The backend now uses explicit report objects instead of passing around loosely structured dicts.

Main report types:

- `PositionAnalysisReport`
- `CandidateMove`
- `MoveCoachingReport`
- `AnnotatedGameMove`
- `GameReviewReport`
- `TutorEvaluationResult`

These make the project easier to test, easier to extend, and more convincing as a backend engineering project.

## Heuristic Evaluation Logic

When Stockfish is not available, the app uses a heuristic evaluator.

The heuristic considers:

- material balance
- piece-square activity
- mobility
- king safety
- center control
- hanging pieces

This is not as strong as Stockfish, but it is enough to support a working fallback path when Stockfish is unavailable.

## Tutor Ranking And Diagnostic Logic

The most important part of the project is the ranking logic.

For each legal move, the system estimates:

- `score_cp`: how good the move is
- `difficulty`: how hard the move is to find or execute
- `tags`: educational themes attached to the move
- `tactical_risk_score`: how dangerous the move is practically
- `strategic_fit_score`: how well the move addresses the position's needs
- `human_plausibility_score`: how teachable and realistic the move is for the chosen level
- `tutor_score`: how appropriate the move is for the chosen ELO

The tutor also produces explicit tactical and strategic findings such as:

- hanging own piece after move
- missed free capture
- allowed free capture
- direct forcing reply for the opponent
- repeated opening tempo on the same piece
- ignored attacked high-value piece
- development improvement or neglect
- center improvement or neglect
- king-safety improvement or neglect
- conversion when ahead
- complexity mismatch for target ELO

The tutor score rewards:

- near-best evaluations
- level-appropriate ideas
- practical, easy-to-execute moves

The tutor score penalizes:

- overly difficult tactical sequences at lower ratings
- moves that give away too much evaluation compared with the strongest option
- moves that create direct tactical risk

This is how the app creates a difference between "engine best" and "best teaching move."

## Example Use Cases

### Use Case 1: Analyze A Position

1. Paste a FEN into the analyzer.
2. Or build a position with the board editor.
3. Select a target ELO.
4. Click `Analyze Position`.
5. Read the tutor summary and candidate table.

### Use Case 2: Check Your Own Idea

1. Paste a FEN.
2. Enter a move like `Nf3` or `e2e4`.
3. Click `Evaluate My Move`.
4. Read the verdict and compare your move to the strongest and tutor-recommended options.

### Use Case 3: Play A Short Training Game

1. Open `Play Against Bot`.
2. Choose your color.
3. Enter your moves one by one.
4. Read the live commentary after each turn.
5. Use the critical moments, recurring patterns, and PGN for review.

### Use Case 4: Run The Evaluation Harness

1. Run `python3 analysis/evaluate_tutor.py`.
2. Inspect the unified JSON bundle.
3. Use the benchmark metrics, review results, generated appendix files, and feedback summary in the report/demo.

## Current Limitations

This is still a prototype, so some features are intentionally simplified.

- The board editor is form-based rather than drag-and-drop.
- The human-like behavior is level-aware and data-informed, but it is not a full Maia-style imitation model.
- No Lichess or Chess.com API integration has been added yet.
- Commentary is rules/template based rather than generated by an LLM.
- The benchmark dataset is local and small by design.
- User feedback evidence is lightweight and anecdotal, not a formal controlled study.
- On this machine, the current default runtime still falls back to heuristics unless a Stockfish binary is installed.

## Suggested Next Steps

If this project is going to be pushed further, the best upgrades would be:

1. Install and wire a real Stockfish binary on every target machine.
2. Expand the benchmark set and add more level-specific example positions.
3. Add real human-game data or a Maia-style model for stronger human-like move selection.
4. Turn the lightweight feedback logging into a structured user study comparing this tutor against raw engine output.
5. Add a richer drag-and-drop board editor if UI work becomes important later.

## Testing

Run the test suite with:

```bash
python3 -m pytest -q
```

Run the local evaluation harness with:

```bash
python3 analysis/evaluate_tutor.py
```

This command now produces the unified evaluation bundle used by the app and report:

- position benchmark results
- review benchmark results
- user feedback summary
- appendix-ready generated file paths

The current tests cover:

- FEN loading
- SAN/UCI move parsing
- candidate move generation
- commentary generation
- tactical/coaching diagnostics
- offline benchmark and feedback aggregation execution

## Files And Structure

```text
app/
  main.py
  core/
    board.py
    commentary.py
    diagnostics.py
    evaluator.py
    levels.py
    move_engine.py
    reports.py
    services.py
    tutor.py
analysis/
  eval_utils.py
  evaluate_positions.py
  evaluate_reviews.py
  evaluate_tutor.py
  generate_appendix_report.py
  user_feedback.py
data/
  benchmarks/
    positions.json
    positions_v2.json
    review_cases.json
    sample_games.pgn
    review_games/
app/ui/
  streamlit_app.py
tests/
  test_board.py
  test_commentary.py
  test_evaluation_suite.py
  test_evaluator.py
  test_services.py
  test_moves.py
requirements.txt
README.md
```

## Report Framing Idea

If you need a short report thesis, you can use something close to this:

> Traditional chess engines optimize for strongest play, but novice and intermediate players benefit more from advice that is understandable, rating-appropriate, and actionable. This project addresses that gap by combining chess evaluation with level-aware move ranking and tutoring commentary.
## Offline Evaluation Suite

Run the following from the repo root:

```bash
python3 analysis/evaluate_tutor.py
python3 analysis/evaluate_positions.py
python3 analysis/evaluate_reviews.py
python3 analysis/generate_appendix_report.py
```

The new scripts generate reproducible benchmark-based evidence for:

- position-level teaching quality
- post-game review usefulness
- lightweight saved user feedback summaries
- appendix-ready summary metrics

Generated outputs are written to analysis/results/.
