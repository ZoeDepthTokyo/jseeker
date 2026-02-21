"""Launch autojs automation dashboard on port 8503."""
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    ui_path = Path(__file__).parent / "ui" / "pipeline.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(ui_path),
         "--server.port", "8503", "--server.headless", "true"],
        check=True
    )
