"""PROTEUS Job Discovery — Tag-based job search across job boards."""

from __future__ import annotations

import re
from datetime import date
from typing import Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from proteus.models import DiscoveryStatus, JobDiscovery
from proteus.tracker import tracker_db


# Job board search URL templates
SEARCH_URLS = {
    "linkedin": "https://www.linkedin.com/jobs/search/?keywords={query}&location={location}",
    "indeed": "https://www.indeed.com/jobs?q={query}&l={location}",
    "wellfound": "https://wellfound.com/role/l/{query}",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def search_jobs(
    tags: list[str],
    location: str = "",
    sources: list[str] = None,
) -> list[JobDiscovery]:
    """Search job boards using configured tags.

    Args:
        tags: Search tags (e.g., ["Director of Product", "UX Director"]).
        location: Location filter.
        sources: Which job boards to search. Default: all.

    Returns:
        List of JobDiscovery objects (not yet saved to DB).
    """
    if sources is None:
        sources = ["indeed"]  # Start with Indeed (most scrapable)

    discoveries = []

    for tag in tags:
        for source in sources:
            try:
                results = _search_source(tag, location, source)
                for result in results:
                    result.search_tags = tag
                    discoveries.append(result)
            except (requests.RequestException, ValueError, KeyError):
                continue  # Skip failed sources

    return discoveries


def _search_source(
    query: str, location: str, source: str
) -> list[JobDiscovery]:
    """Search a single job board source."""
    url_template = SEARCH_URLS.get(source)
    if not url_template:
        return []

    url = url_template.format(
        query=quote_plus(query),
        location=quote_plus(location or ""),
    )

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    if source == "indeed":
        return _parse_indeed(soup, source)
    elif source == "linkedin":
        return _parse_linkedin(soup, source)
    else:
        return []


def _parse_indeed(soup: BeautifulSoup, source: str) -> list[JobDiscovery]:
    """Parse Indeed search results."""
    results = []
    job_cards = soup.find_all("div", class_=re.compile("job_seen_beacon|cardOutline"))

    for card in job_cards[:20]:  # Limit to 20 results
        title_elem = card.find("h2", class_=re.compile("jobTitle"))
        company_elem = card.find("span", attrs={"data-testid": "company-name"})
        location_elem = card.find("div", attrs={"data-testid": "text-location"})
        link_elem = card.find("a", href=True)

        title = title_elem.get_text(strip=True) if title_elem else ""
        company = company_elem.get_text(strip=True) if company_elem else ""
        location = location_elem.get_text(strip=True) if location_elem else ""
        url = ""
        if link_elem and link_elem.get("href"):
            href = link_elem["href"]
            if href.startswith("/"):
                url = f"https://www.indeed.com{href}"
            else:
                url = href

        if title:
            results.append(JobDiscovery(
                title=title,
                company=company,
                location=location,
                url=url,
                source=source,
                posting_date=date.today(),
            ))

    return results


def _parse_linkedin(soup: BeautifulSoup, source: str) -> list[JobDiscovery]:
    """Parse LinkedIn Jobs search results (public, no auth)."""
    results = []
    job_cards = soup.find_all("div", class_=re.compile("base-card"))

    for card in job_cards[:20]:
        title_elem = card.find("h3", class_=re.compile("base-search-card__title"))
        company_elem = card.find("h4", class_=re.compile("base-search-card__subtitle"))
        location_elem = card.find("span", class_=re.compile("job-search-card__location"))
        link_elem = card.find("a", class_=re.compile("base-card__full-link"))

        title = title_elem.get_text(strip=True) if title_elem else ""
        company = company_elem.get_text(strip=True) if company_elem else ""
        location = location_elem.get_text(strip=True) if location_elem else ""
        url = link_elem["href"] if link_elem and link_elem.get("href") else ""

        if title:
            results.append(JobDiscovery(
                title=title,
                company=company,
                location=location,
                url=url,
                source=source,
                posting_date=date.today(),
            ))

    return results


def save_discoveries(discoveries: list[JobDiscovery]) -> int:
    """Save new discoveries to DB (deduplicates by URL).

    Returns count of newly saved discoveries.
    """
    saved = 0
    for disc in discoveries:
        result = tracker_db.add_discovery(disc)
        if result is not None:
            saved += 1
    return saved


def import_discovery_to_application(discovery_id: int) -> Optional[int]:
    """Import a starred discovery into the applications tracker.

    Returns application ID if created.
    """
    from proteus.models import Application

    discoveries = tracker_db.list_discoveries()
    disc = None
    for d in discoveries:
        if d["id"] == discovery_id:
            disc = d
            break

    if not disc:
        return None

    company_id = tracker_db.get_or_create_company(disc.get("company", "Unknown"))

    app = Application(
        company_id=company_id,
        role_title=disc["title"],
        jd_url=disc.get("url", ""),
        location=disc.get("location", ""),
        salary_range=disc.get("salary_range", ""),
    )

    app_id = tracker_db.add_application(app)

    # Update discovery status
    tracker_db.update_discovery_status(discovery_id, "imported")

    return app_id
