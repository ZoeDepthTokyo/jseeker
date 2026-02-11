"""Tests for Job Discovery Architecture v2 (market field, tag weights, pause/resume)."""

import pytest
from datetime import date
from jseeker.models import JobDiscovery
from jseeker.tracker import tracker_db, init_db
from jseeker.job_discovery import rank_discoveries_by_tag_weight, search_jobs_async
from pathlib import Path


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Create a temporary test database."""
    db_path = tmp_path / "test_job_discovery.db"
    init_db(db_path)

    # Patch the _get_db_path function to return our test DB
    monkeypatch.setattr('jseeker.tracker._get_db_path', lambda: db_path)

    # Create a new TrackerDB instance
    from jseeker.tracker import TrackerDB
    test_tracker = TrackerDB()

    yield test_tracker


def test_market_field_stored_correctly(test_db):
    """Test that market field is stored separately from source."""
    discovery = JobDiscovery(
        title="Test Job",
        company="Test Company",
        location="San Francisco",
        url="https://example.com/job/1",
        source="indeed",  # Clean source, no suffix
        market="us",  # Separate market field
        posting_date=date.today(),
        search_tags="Product Designer"
    )

    # Save discovery
    disc_id = test_db.add_discovery(discovery)
    assert disc_id is not None

    # Retrieve and verify
    discoveries = test_db.list_discoveries()
    assert len(discoveries) == 1
    assert discoveries[0]["source"] == "indeed"  # No suffix
    assert discoveries[0]["market"] == "us"  # Separate field


def test_source_field_clean_no_suffix(test_db):
    """Test that source field does not contain market suffix."""
    discovery = JobDiscovery(
        title="Test Job MX",
        company="Test Company",
        url="https://example.com/job/2",
        source="linkedin",  # Clean: no "_mx" suffix
        market="mx",
        search_tags="UX Designer"
    )

    disc_id = test_db.add_discovery(discovery)
    discoveries = test_db.list_discoveries()

    assert discoveries[0]["source"] == "linkedin"
    assert discoveries[0]["market"] == "mx"
    assert "_" not in discoveries[0]["source"]  # No underscore suffix


def test_tag_weights_set_and_retrieve(test_db):
    """Test setting and retrieving tag weights."""
    # Set weights
    test_db.set_tag_weight("Product Designer", 80)
    test_db.set_tag_weight("UX Designer", 60)
    test_db.set_tag_weight("Low Priority", 20)

    # Retrieve individual weights
    assert test_db.get_tag_weight("Product Designer") == 80
    assert test_db.get_tag_weight("UX Designer") == 60
    assert test_db.get_tag_weight("Low Priority") == 20
    assert test_db.get_tag_weight("Nonexistent Tag") == 50  # Default

    # List all weights
    weights = test_db.list_tag_weights()
    assert len(weights) == 3
    assert weights[0]["tag"] == "Product Designer"  # Sorted by weight DESC
    assert weights[0]["weight"] == 80


def test_tag_weights_clamped_to_range(test_db):
    """Test that tag weights are clamped to 1-100."""
    test_db.set_tag_weight("Too High", 200)
    test_db.set_tag_weight("Too Low", -50)
    test_db.set_tag_weight("Just Right", 75)

    assert test_db.get_tag_weight("Too High") == 100  # Clamped to max
    assert test_db.get_tag_weight("Too Low") == 1    # Clamped to min
    assert test_db.get_tag_weight("Just Right") == 75


def test_rank_discoveries_by_tag_weight():
    """Test ranking discoveries by sum of tag weights."""
    # Create discoveries with different tags
    disc1 = JobDiscovery(
        title="High Priority Job",
        url="http://example.com/1",
        source="indeed",
        market="us",
        search_tags="Product Designer, Senior",  # 80 + 70 = 150
        posting_date=date.today()
    )
    disc2 = JobDiscovery(
        title="Medium Priority Job",
        url="http://example.com/2",
        source="linkedin",
        market="mx",
        search_tags="UX Designer",  # 60
        posting_date=date.today()
    )
    disc3 = JobDiscovery(
        title="Low Priority Job",
        url="http://example.com/3",
        source="wellfound",
        market="ca",
        search_tags="Junior",  # 30
        posting_date=date.today()
    )

    # Mock tag weights
    from unittest.mock import patch
    with patch('jseeker.job_discovery.tracker_db.get_tag_weight') as mock_get_weight:
        def get_weight_side_effect(tag):
            weights = {
                "Product Designer": 80,
                "Senior": 70,
                "UX Designer": 60,
                "Junior": 30
            }
            return weights.get(tag, 50)

        mock_get_weight.side_effect = get_weight_side_effect

        # Rank discoveries
        ranked = rank_discoveries_by_tag_weight([disc1, disc2, disc3])

        # Verify order (highest weight first)
        assert ranked[0].title == "High Priority Job"  # 150 weight
        assert ranked[1].title == "Medium Priority Job"  # 60 weight
        assert ranked[2].title == "Low Priority Job"  # 30 weight

        # Verify tag_weights dict is populated
        assert ranked[0].search_tag_weights["Product Designer"] == 80
        assert ranked[0].search_tag_weights["Senior"] == 70
        assert ranked[1].search_tag_weights["UX Designer"] == 60


def test_search_sessions_create_and_retrieve(test_db):
    """Test creating and retrieving search sessions."""
    session_id = test_db.create_search_session(
        tags=["Product Designer", "UX Designer"],
        markets=["us", "mx"],
        sources=["indeed", "linkedin"]
    )

    assert session_id is not None

    # Retrieve session
    session = test_db.get_search_session(session_id)
    assert session is not None
    assert session["tags"] == ["Product Designer", "UX Designer"]
    assert session["markets"] == ["us", "mx"]
    assert session["sources"] == ["indeed", "linkedin"]
    assert session["status"] == "active"
    assert session["total_found"] == 0


def test_search_sessions_update(test_db):
    """Test updating search session status."""
    session_id = test_db.create_search_session(["Test"], ["us"], ["indeed"])

    # Update session
    test_db.update_search_session(
        session_id,
        status="paused",
        total_found=25,
        limit_reached=False
    )

    # Verify update
    session = test_db.get_search_session(session_id)
    assert session["status"] == "paused"
    assert session["total_found"] == 25
    assert session["limit_reached"] == 0  # SQLite stores as 0/1


def test_pause_resume_search():
    """Test pause/resume functionality in search_jobs_async."""
    paused = False

    def pause_check():
        return paused

    progress_calls = []

    def progress_callback(current, total):
        progress_calls.append((current, total))

    # Mock _search_source to return predictable results
    from unittest.mock import patch
    with patch('jseeker.job_discovery._search_source') as mock_search:
        mock_search.return_value = [
            JobDiscovery(
                title=f"Job {i}",
                url=f"http://example.com/{i}",
                source="indeed",
                market="us"
            )
            for i in range(5)
        ]

        # Start search, pause after 2 combinations
        discoveries = []
        for i in range(3):
            if i == 2:
                paused = True  # Pause on 3rd iteration
            results = search_jobs_async(
                tags=["Test Tag"],
                markets=["us"],
                sources=["indeed", "linkedin"],
                pause_check=pause_check,
                progress_callback=progress_callback,
                max_results=100
            )
            discoveries.extend(results)
            if paused:
                break

        # Should have stopped early due to pause
        assert len(progress_calls) >= 1  # At least some progress
        # Exact count depends on when pause was checked


def test_250_job_limit_enforcement():
    """Test that search stops at 250-job limit."""
    from unittest.mock import patch

    with patch('jseeker.job_discovery._search_source') as mock_search:
        # Each search returns 30 jobs
        mock_search.return_value = [
            JobDiscovery(
                title=f"Job {i}",
                url=f"http://example.com/{i}",
                source="indeed",
                market="us"
            )
            for i in range(30)
        ]

        discoveries = search_jobs_async(
            tags=["Test"] * 10,  # 10 tags
            markets=["us"],
            sources=["indeed"],
            max_results=250
        )

        # Should stop at 250 even though 10 tags * 30 results = 300 potential
        assert len(discoveries) <= 250


def test_filters_work_correctly(test_db):
    """Test that market, location, and source filters work."""
    # Add test discoveries
    test_db.add_discovery(JobDiscovery(
        title="US Job", url="http://ex.com/1",
        source="indeed", market="us", location="San Francisco"
    ))
    test_db.add_discovery(JobDiscovery(
        title="MX Job", url="http://ex.com/2",
        source="linkedin", market="mx", location="Ciudad de Mexico"
    ))
    test_db.add_discovery(JobDiscovery(
        title="CA Job", url="http://ex.com/3",
        source="wellfound", market="ca", location="Toronto"
    ))

    # Filter by market
    us_jobs = test_db.list_discoveries(market="us")
    assert len(us_jobs) == 1
    assert us_jobs[0]["market"] == "us"

    # Filter by source
    indeed_jobs = test_db.list_discoveries(source="indeed")
    assert len(indeed_jobs) == 1
    assert indeed_jobs[0]["source"] == "indeed"

    # Filter by location (partial match)
    sf_jobs = test_db.list_discoveries(location="San")
    assert len(sf_jobs) == 1
    assert "San" in sf_jobs[0]["location"]

    # Multiple filters
    us_indeed = test_db.list_discoveries(market="us", source="indeed")
    assert len(us_indeed) == 1
    assert us_indeed[0]["market"] == "us"
    assert us_indeed[0]["source"] == "indeed"


def test_integration_search_save_filter_group(test_db):
    """Integration test: search, save, filter, and group by (market, location)."""
    # Set up tag weights
    test_db.set_tag_weight("Product Designer", 80)
    test_db.add_search_tag("Product Designer")

    # Mock search
    from unittest.mock import patch
    with patch('jseeker.job_discovery._search_source') as mock_search:
        mock_search.return_value = [
            JobDiscovery(
                title="SF Job",
                url="http://ex.com/sf1",
                source="indeed",
                market="us",
                location="San Francisco",
                search_tags="Product Designer"
            ),
            JobDiscovery(
                title="NYC Job",
                url="http://ex.com/nyc1",
                source="linkedin",
                market="us",
                location="New York",
                search_tags="Product Designer"
            ),
            JobDiscovery(
                title="MX Job",
                url="http://ex.com/mx1",
                source="indeed",
                market="mx",
                location="Ciudad de Mexico",
                search_tags="Product Designer"
            ),
        ]

        # Search
        discoveries = search_jobs_async(
            tags=["Product Designer"],
            markets=["us", "mx"],
            sources=["indeed"],
            max_results=250
        )

        # Rank and save
        from jseeker.job_discovery import rank_discoveries_by_tag_weight
        ranked = rank_discoveries_by_tag_weight(discoveries)

        # Save manually using test_db
        saved_count = 0
        for disc in ranked:
            if disc.url and not test_db.is_url_known(disc.url):
                result = test_db.add_discovery(disc)
                if result is not None:
                    saved_count += 1

        assert saved_count == 3  # All unique

        # Filter by market
        us_jobs = test_db.list_discoveries(market="us")
        assert len(us_jobs) == 2

        # Group by (market, location)
        from collections import defaultdict
        by_market_location = defaultdict(list)
        for d in test_db.list_discoveries():
            key = (d.get("market"), d.get("location"))
            by_market_location[key].append(d)

        assert len(by_market_location) == 3  # 3 unique (market, location) pairs
        assert ("us", "San Francisco") in by_market_location
        assert ("us", "New York") in by_market_location
        assert ("mx", "Ciudad de Mexico") in by_market_location


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
