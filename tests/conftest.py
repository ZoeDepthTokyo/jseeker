"""PROTEUS test configuration and fixtures."""

import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def sample_jd_text():
    """Sample JD text for testing."""
    return """
    Director of Product Design
    Company: TechCorp
    Location: San Francisco, CA (Hybrid)
    Salary: $200,000 - $260,000

    We are looking for a Director of Product Design to lead our design team.

    Requirements:
    - 10+ years of product design experience
    - Experience leading teams of 10+ designers
    - Strong background in AI/ML user experiences
    - Experience with design systems at scale
    - Track record of improving user retention and engagement
    - Experience with autonomous vehicle or mobility products preferred
    - Strong stakeholder communication skills

    Skills:
    - Product Design, UX Design, AI UX, Design Systems
    - Team Leadership, Cross-functional Collaboration
    - Agile methodologies, User Research

    We are an equal opportunity employer.
    Benefits include health insurance, 401k, unlimited PTO.
    """


@pytest.fixture
def sample_jd_url():
    return "https://boards.greenhouse.io/techcorp/jobs/12345"


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_proteus.db"
    from proteus.tracker import init_db
    init_db(db_path)
    return db_path
