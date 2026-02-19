"""AutoJS -- jSeeker automation sibling package.

Provides auto-apply orchestration, ATS form runners, answer bank,
verification, and monitoring. Reads shared data/ and DB from parent.

Install: pip install -e X:/projects/jSeeker/autojs
Requires: jseeker (pip install -e X:/projects/jSeeker)
"""

from autojs.auto_apply import AutoApplyEngine
from autojs.answer_bank import AnswerBank, load_answer_bank

__all__ = ["AutoApplyEngine", "AnswerBank", "load_answer_bank"]
