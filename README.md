# chess_tutor

Teammate: Zhihan Chen

## Overview

This repository contains an interactive chess tutor prototype designed around the project brief shown in class: build a chess teacher that is more helpful for novice-to-intermediate players than a raw chess engine.

The current implementation is a working end-to-end prototype with a web interface, position analysis, a play-against-bot mode, live commentary, and a post-game review. The system is designed around a simple but important idea:

- a strong engine answers "what is best?"
- a tutor should also answer "what is most useful for this player's level?"

This project therefore separates:

- chess rules and board state
- move evaluation and ranking
- tutoring commentary and skill-aware feedback

That separation makes the code easier to understand, easier to test, and easier to improve later.

## Project Goal

The goal of this project is not just to recommend the strongest move. It is to provide advice that is:

- interpretable for the player
- matched to a target ELO level
- actionable during analysis or play
- easier to learn from than a stock engine line dump

To support that goal, the tutor ranks moves in two ways:

- `engine strength`: how good the move is in centipawn terms
- `tutor fit`: how appropriate the move is for a selected rating band

This allows the app to sometimes recommend a move that is slightly weaker than the top engine move if it is much easier to understand and execute for the chosen skill level.

## Implemented Features

This repo now contains a minimal end-to-end chess tutor prototype aimed at the A+ rubric in the project brief:

- Position analyzer where a user can load a FEN and choose a target ELO.
- Play-against-bot mode with live commentary and a post-game review.
- Level-aware move suggestions that are not limited to raw best-engine moves.
- A built-in "engine vs tutor" explanation so you can argue that the tutor is more useful for novice-to-intermediate players.

The app uses `python-chess` for rules, board state, SVG board rendering, PGN export, and optional UCI engine integration. If a Stockfish binary is available through `STOCKFISH_EXECUTABLE` or on the system path, the tutor will use it as the tactical truth layer. If not, it falls back to a heuristic evaluator so the demo still runs cleanly.

## Why This Is More Than A Raw Engine

A raw engine normally gives:

- the best move
- an evaluation
- maybe a top line

That is useful for strong players, but it can be overwhelming for beginners.

This tutor adds a second layer on top of evaluation:

- it rewards safe, teachable moves at lower ratings
- it penalizes overly difficult moves for lower ratings
- it explains moves using themes like development, king safety, center control, and hanging-piece awareness
- it gives a short judgment on user moves such as `Excellent`, `Good practical move`, `Inaccuracy`, or `Blunder risk`

This is the main argument for the report: the tutor does not replace tactical truth, it translates tactical truth into more practical coaching.

## Technology Stack

- `Python`
- `Streamlit` for the web interface
- `python-chess` for board state, move legality, FEN parsing, SAN/UCI parsing, SVG board rendering, and PGN export
- optional `Stockfish` integration through UCI
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

### 4. Optional: connect Stockfish

If you have a Stockfish binary installed, you can point the app to it:

```bash
export STOCKFISH_EXECUTABLE=/path/to/stockfish
python3 -m streamlit run app/main.py
```

If no Stockfish binary is found, the app still works by using the built-in heuristic evaluator.

## Quick Start Demo

If you want the fastest way to show the project in class:

1. Start the app.
2. Go to `Position Analyzer`.
3. Load an example position.
4. Choose `600`, `1000`, `1400`, or `1800` in the sidebar.
5. Click `Analyze Position`.
6. Show that the tutor may recommend a move that is more teachable than the top engine move.
7. Go to `Play Against Bot`.
8. Play a few moves and point out the live commentary.
9. Show the PGN and post-game lessons.

## Interface Overview

The web app has three main tabs.

### 1. Position Analyzer

This tab is designed for the assignment requirement that the user should be able to set up a position and request feedback for a pre-specified ELO.

What you can do:

- paste a FEN
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
- a candidate move table with score, difficulty, and themes
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
- a post-game review
- PGN output for the game

### 3. Evaluation Story

This tab is included to make the grading argument explicit.

It explains that:

- raw engine output optimizes only for strength
- the tutor adds practicality for a target rating
- slightly weaker but easier moves can be more educational
- helpful explanations matter for novice-to-intermediate players

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

### 2. Decision-Making And Move Ranking

Files:

- `app/core/move_engine.py`
- `app/core/levels.py`

Responsibilities:

- detect and use Stockfish when available
- fall back to heuristic analysis when Stockfish is unavailable
- evaluate legal moves
- estimate move difficulty
- assign tags such as development, center, king safety, and initiative
- compute a tutor-aware ranking score

### 3. Tutoring And Commentary

Files:

- `app/core/tutor.py`
- `app/core/commentary.py`
- `app/core/evaluator.py`

Responsibilities:

- turn move analysis into plain-English summaries
- evaluate a user's move against the strongest and tutor-preferred choices
- produce verdicts like `Excellent` or `Blunder risk`
- build simple post-game lessons

### 4. Web Interface

Files:

- `app/main.py`
- `app/ui/streamlit_app.py`

Responsibilities:

- create the Streamlit layout
- manage session state
- connect the tutor logic to the user interface
- display boards, tables, commentary, and PGN output

## Heuristic Evaluation Logic

When Stockfish is not available, the app uses a heuristic evaluator.

The heuristic considers:

- material balance
- piece-square activity
- mobility
- king safety
- center control
- hanging pieces

This is not as strong as Stockfish, but it is enough to support a working demonstration of the tutoring system and interface.

## Tutor Ranking Logic

The most important part of the project is the ranking logic.

For each legal move, the system estimates:

- `score_cp`: how good the move is
- `difficulty`: how hard the move is to find or execute
- `tags`: educational themes attached to the move
- `tutor_score`: how appropriate the move is for the chosen ELO

The tutor score rewards:

- near-best evaluations
- level-appropriate ideas
- practical, easy-to-execute moves

The tutor score penalizes:

- overly difficult tactical sequences at lower ratings
- moves that give away too much evaluation compared with the strongest option

This is how the app creates a difference between "engine best" and "best teaching move."

## Example Use Cases

### Use Case 1: Analyze A Position

1. Paste a FEN into the analyzer.
2. Select a target ELO.
3. Click `Analyze Position`.
4. Read the tutor summary and candidate table.

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
5. Use the post-game summary and PGN for review.

## Current Limitations

This is a prototype, so some features are intentionally simplified.

- Board setup is currently done through FEN input, not drag-and-drop piece placement.
- The human-like behavior is rules-based and level-aware, not trained on Maia or Maia-2.
- No Lichess or Chess.com API integration has been added yet.
- Commentary is template-based rather than generated by an LLM.
- The heuristic fallback is useful for demonstration, but Stockfish is recommended for stronger analysis.

## Suggested Next Steps

If this project is going to be pushed further, the best upgrades would be:

1. Add a visual board editor so users can place pieces directly.
2. Improve post-game review with concrete blunders and missed tactics by move number.
3. Connect a real Stockfish binary by default for stronger tactical truth.
4. Add real human-game data or a Maia-style model for stronger human-like move selection.
5. Add user testing results comparing this tutor against raw engine output.

## Testing

Run the test suite with:

```bash
python3 -m pytest -q
```

The current tests cover:

- FEN loading
- SAN/UCI move parsing
- candidate move generation
- commentary generation

## Files And Structure

```text
app/
  main.py
  core/
    board.py
    commentary.py
    evaluator.py
    levels.py
    move_engine.py
    tutor.py
  ui/
    streamlit_app.py
tests/
  test_board.py
  test_commentary.py
  test_moves.py
requirements.txt
README.md
```

## Report Framing Idea

If you need a short report thesis, you can use something close to this:

> Traditional chess engines optimize for strongest play, but novice and intermediate players benefit more from advice that is understandable, rating-appropriate, and actionable. This project addresses that gap by combining chess evaluation with level-aware move ranking and tutoring commentary.
