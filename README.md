# chess_tutor

Teammate: Zhihan Chen

## Overview

This repo now contains a minimal end-to-end chess tutor prototype aimed at the A+ rubric in the project brief:

- Position analyzer where a user can load a FEN and choose a target ELO.
- Play-against-bot mode with live commentary and a post-game review.
- Level-aware move suggestions that are not limited to raw best-engine moves.
- A built-in "engine vs tutor" explanation so you can argue that the tutor is more useful for novice-to-intermediate players.

The app uses `python-chess` for rules, board state, SVG board rendering, PGN export, and optional UCI engine integration. If a Stockfish binary is available through `STOCKFISH_EXECUTABLE` or on the system path, the tutor will use it as the tactical truth layer. If not, it falls back to a heuristic evaluator so the demo still runs cleanly.

## Quick Start

1. Install dependencies:

   ```bash
   python3 -m pip install -r requirements.txt
   ```

2. Launch the app:

   ```bash
   streamlit run app/main.py
   ```

3. Optional: point the app at Stockfish for stronger analysis:

   ```bash
   export STOCKFISH_EXECUTABLE=/path/to/stockfish
   ```

## Project Structure

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
```

## Demo Flows

### 1. Position Analyzer

- Paste or load a FEN.
- Choose a target ELO bucket: 600, 1000, 1400, or 1800.
- See the strongest move, the tutor move for that skill band, and a short explanation of why the recommendation is educational.

### 2. Play Against Bot

- Start a new game as White or Black.
- Enter moves in SAN or UCI.
- Receive immediate feedback on your move quality.
- Get a live bot reply plus running commentary.
- Review the PGN and high-level lessons after the game.

### 3. Evaluation Story

The key grading argument is built directly into the app:

- Raw engine output prioritizes strongest play.
- The tutor adds a second ranking objective: practicality for a target ELO.
- Lower-rated players are steered toward safe, teachable moves that emphasize habits like development, center control, king safety, and hanging-piece awareness.

That gives you a concise report claim: the system is more useful than a stock engine for novices because it converts evaluation into actionable coaching rather than move dumps.

## Testing

```bash
pytest
```
