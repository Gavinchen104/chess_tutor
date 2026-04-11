from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.evaluate_positions import evaluate_positions
from analysis.evaluate_reviews import evaluate_reviews
from analysis.user_feedback import load_feedback_entries, summarize_feedback


DEFAULT_OUTPUT_DIR = REPO_ROOT / "analysis" / "results"


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_appendix_report(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    positions_report = evaluate_positions()
    reviews_report = evaluate_reviews()
    feedback_summary = summarize_feedback(load_feedback_entries())

    positions_path = output_dir / "positions_report.json"
    reviews_path = output_dir / "reviews_report.json"

    write_json(positions_path, positions_report)
    write_json(reviews_path, reviews_report)

    summary = {
        "position_benchmark_count": positions_report["benchmark_count"],
        "review_benchmark_count": reviews_report["benchmark_count"],
        "position_metrics": positions_report["metrics"],
        "review_metrics": reviews_report["metrics"],
        "user_feedback_summary": feedback_summary,
        "generated_files": {
            "positions_report": str(positions_path),
            "reviews_report": str(reviews_path),
        },
    }

    summary_path = output_dir / "appendix_summary.json"
    write_json(summary_path, summary)
    summary["generated_files"]["appendix_summary"] = str(summary_path)
    return {
        "positions_report": positions_report,
        "reviews_report": reviews_report,
        "feedback_summary": feedback_summary,
        "summary": summary,
    }


def generate_appendix_report(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict:
    bundle = build_appendix_report(output_dir=output_dir)
    return bundle["summary"]


def main() -> None:
    payload = generate_appendix_report()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
