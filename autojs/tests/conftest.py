"""autojs test configuration.

Adds both the autojs package directory and jSeeker repo root to sys.path
so that `import autojs` resolves to autojs/autojs/ and jseeker remains
importable without a formal install.
"""

import sys
from pathlib import Path

# autojs/autojs/ package root (one level up from tests/)
_autojs_pkg_root = Path(__file__).parent.parent
sys.path.insert(0, str(_autojs_pkg_root))

# jSeeker repo root (for jseeker, config, etc.)
_repo_root = _autojs_pkg_root.parent
sys.path.insert(0, str(_repo_root))
