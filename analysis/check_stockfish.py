from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chess

from app.core.move_engine import MoveEngine, find_stockfish_path


def main() -> None:
    detected = find_stockfish_path()
    print(f"Detected Stockfish path: {detected}")

    engine = MoveEngine()
    print(f"Engine stockfish_path before probe: {engine.stockfish_path}")

    board = chess.Board()
    score = engine.evaluate_position_for_side(board, chess.WHITE)

    provider = "Stockfish" if engine.stockfish_path else "Heuristic Tutor Engine"
    print(f"Provider after probe: {provider}")
    print(f"Start position eval from White POV: {score} cp")

    if not engine.stockfish_path:
        raise SystemExit("Stockfish was not detected successfully. Check your .env path or installation.")

    print("Stockfish setup looks good.")


if __name__ == "__main__":
    main()
