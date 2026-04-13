import sys
from pathlib import Path

# Streamlit sets sys.path to this file's directory; ensure repo root is importable as "app".
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.ui.streamlit_app import run


if __name__ == "__main__":
    run()
