from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.levels import LEVELS
from app.core.services import EvaluationService


def main() -> None:
    positions_path = REPO_ROOT / "data" / "benchmarks" / "positions.json"
    games_path = REPO_ROOT / "data" / "benchmarks" / "sample_games.pgn"

    result = EvaluationService().evaluate_local_benchmarks(
        positions_path=positions_path,
        games_path=games_path,
        levels=LEVELS,
    )

    payload = {
        "engine_available": result.engine_available,
        "benchmark_count": result.benchmark_count,
        "game_count": result.game_count,
        "metrics": result.metrics,
        "position_examples": [asdict(example) for example in result.position_examples],
        "game_summaries": result.game_summaries,
        "user_feedback_rubric": result.user_feedback_rubric,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
