from __future__ import annotations

import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.generate_appendix_report import build_appendix_report


def main() -> None:
    payload = build_appendix_report(REPO_ROOT / "analysis" / "results")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
