"""jSeeker Job Discovery — Tag-based job search across job boards."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from jseeker.models import DiscoveryStatus, JobDiscovery
from jseeker.tracker import tracker_db

logger = logging.getLogger(__name__)


# Job board search URL templates
SEARCH_URLS = {
    "linkedin": "https://www.linkedin.com/jobs/search/?keywords={query}&location={location}&sortBy=DD&f_TPR=r604800",
    "indeed": "https://www.indeed.com/jobs?q={query}&l={location}&sort=date&fromage=14",
    "wellfound": "https://wellfound.com/role/l/{query}",
}

# International market configuration
MARKET_CONFIG = {
    "us": {
        "name": "United States",
        "indeed_url": "https://www.indeed.com/jobs?q={query}&l={location}&sort=date&fromage=14",
        "linkedin_location": "United States",
        "language_filter": None,  # No filter needed - English by default
        "location": "",  # Empty - let Indeed return national results
    },
    "mx": {
        "name": "Mexico",
        "indeed_url": "https://www.indeed.com.mx/jobs?q={query}&l={location}&sort=date&fromage=14",
        "linkedin_location": "Mexico",
        "language_filter": "en",  # English JDs only
        "location": "Ciudad de Mexico",
    },
    "ca": {
        "name": "Canada",
        "indeed_url": "https://ca.indeed.com/jobs?q={query}&l={location}&sort=date&fromage=14",
        "linkedin_location": "Canada",
        "language_filter": None,  # English by default
        "location": "Toronto",
    },
    "uk": {
        "name": "United Kingdom",
        "indeed_url": "https://www.indeed.co.uk/jobs?q={query}&l={location}&sort=date&fromage=14",
        "linkedin_location": "United Kingdom",
        "language_filter": "en",
        "location": "London",
    },
    "es": {
        "name": "Spain",
        "indeed_url": "https://www.indeed.es/jobs?q={query}&l={location}&sort=date&fromage=14",
        "linkedin_location": "Spain",
        "language_filter": "en",
        "location": "Madrid",
    },
    "dk": {
        "name": "Denmark",
        "indeed_url": "https://dk.indeed.com/jobs?q={query}&l={location}&sort=date&fromage=14",
        "linkedin_location": "Denmark",
        "language_filter": "en",
        "location": "Copenhagen",
    },
    "fr": {
        "name": "France",
        "indeed_url": "https://www.indeed.fr/jobs?q={query}&l={location}&sort=date&fromage=14",
        "linkedin_location": "France",
        "language_filter": "en",
        "location": "Paris",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def search_jobs(
    tags: list[str],
    location: str = "",
    sources: list[str] = None,
    markets: list[str] = None,
) -> list[JobDiscovery]:
    """Search job boards using configured tags.

    Args:
        tags: Search tags (e.g., ["Director of Product", "UX Director"]).
        location: Location filter.
        sources: Which job boards to search. Default: ["indeed"].
        markets: Which markets to search. Default: ["us"].

    Returns:
        List of JobDiscovery objects (not yet saved to DB), deduplicated by URL.
    """
    if sources is None:
        sources = ["indeed"]  # Start with Indeed (most scrapable)
    if markets is None:
        markets = ["us"]

    discoveries = []

    for tag in tags:
        for market in markets:
            for source in sources:
                try:
                    logger.info("Searching tag=%s market=%s source=%s", tag, market, source)
                    # Use market-specific location default
                    market_location = MARKET_CONFIG.get(market, {}).get("location", "")
                    results = _search_source(tag, market_location, source, market)
                    logger.info("Found %d results for tag=%s market=%s source=%s", len(results), tag, market, source)
                    for result in results:
                        result.search_tags = tag
                        discoveries.append(result)
                except (requests.RequestException, ValueError, KeyError):
                    logger.exception(
                        "search_jobs failed for source=%s market=%s tag=%s",
                        source,
                        market,
                        tag,
                    )
                    continue  # Skip failed sources

    # Dedup by URL, prefer LinkedIn source
    seen_urls = {}
    for disc in discoveries:
        if not disc.url:
            continue
        # Normalize URL (strip tracking params)
        clean_url = disc.url.split("?")[0]
        if clean_url in seen_urls:
            # Prefer LinkedIn over other sources
            if disc.source == "linkedin" and seen_urls[clean_url].source != "linkedin":
                seen_urls[clean_url] = disc
        else:
            seen_urls[clean_url] = disc

    deduped = list(seen_urls.values())
    # Add entries without URLs
    deduped.extend(d for d in discoveries if not d.url)

    logger.info("Total: %d discoveries, %d after dedup", len(discoveries), len(deduped))

    return deduped


def _search_source(
    query: str, location: str, source: str, market: str = "us"
) -> list[JobDiscovery]:
    """Search a single job board source.

    Args:
        query: Search query/tag
        location: Location filter
        source: Job board source (indeed, linkedin, wellfound)
        market: Market code (us, mx, ca, uk, es, dk, fr)

    Returns:
        List of JobDiscovery objects
    """
    market_config = MARKET_CONFIG.get(market, MARKET_CONFIG["us"])

    # Apply language filter only for Indeed on non-English markets
    search_query = query
    if source == "indeed" and market_config.get("language_filter") == "en":
        search_query = f"{query} english"

    # Use market-specific Indeed URL
    if source == "indeed":
        # Extract Indeed base URL for proper international link construction
        indeed_base = market_config["indeed_url"].split("/jobs")[0]  # e.g. "https://www.indeed.com.mx"
        url = market_config["indeed_url"].format(
            query=quote_plus(search_query),
            location=quote_plus(location or ""),
        )
    elif source == "linkedin":
        # Use market-specific LinkedIn location
        linkedin_loc = market_config.get("linkedin_location", location or "")
        url = SEARCH_URLS["linkedin"].format(
            query=quote_plus(query),
            location=quote_plus(linkedin_loc),
        )
    else:
        # For other sources, use default URL template
        url_template = SEARCH_URLS.get(source)
        if not url_template:
            return []
        url = url_template.format(
            query=quote_plus(query),
            location=quote_plus(location or ""),
        )

    logger.info("Fetching URL: %s", url)

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        logger.info("Response status: %d, content length: %d", response.status_code, len(response.text))
    except requests.HTTPError as e:
        # Gracefully handle 403 Forbidden (anti-bot protection)
        if response.status_code == 403:
            logger.debug("403 blocked by %s (anti-bot) for market=%s", source, market)
            return []
        # Re-raise other HTTP errors
        logger.exception("HTTP error for URL: %s", url)
        return []
    except requests.RequestException:
        logger.exception("Request failed for URL: %s", url)
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    # Parse results with clean source and separate market
    if source == "indeed":
        results = _parse_indeed(soup, source, indeed_base=indeed_base)
    elif source == "linkedin":
        results = _parse_linkedin(soup, source)
    elif source == "wellfound":
        results = _parse_wellfound(soup, source)
    else:
        results = []

    # Set market field on all results
    for result in results:
        result.market = market

    return results


def _parse_indeed(soup: BeautifulSoup, source: str, indeed_base: str = "https://www.indeed.com") -> list[JobDiscovery]:
    """Parse Indeed search results.

    Args:
        soup: BeautifulSoup object of the Indeed search results page
        source: Source identifier (clean: "indeed", not "indeed_us")
        indeed_base: Base URL for Indeed (e.g., "https://www.indeed.com.mx")

    Returns:
        List of JobDiscovery objects (market field set by caller)
    """
    results = []

    # Try multiple card selectors
    job_cards = soup.find_all("div", class_=re.compile("job_seen_beacon|cardOutline"))
    if not job_cards:
        job_cards = soup.find_all("div", attrs={"data-jk": True})
    if not job_cards:
        job_cards = soup.find_all("li", class_=re.compile("css-"))
    if not job_cards:
        job_cards = soup.find_all("div", class_=re.compile("result"))

    logger.info("Indeed parser: found %d job cards", len(job_cards))

    for card in job_cards[:20]:  # Limit to 20 results
        # Title - try multiple selectors
        title_elem = card.find("h2", class_=re.compile("jobTitle"))
        if not title_elem:
            title_elem = card.find("a", class_=re.compile("jcs-JobTitle"))
        if not title_elem:
            # Look for span with id starting with jobTitle
            title_elem = card.find("span", id=re.compile("^jobTitle"))

        # Company - try multiple selectors
        company_elem = card.find("span", attrs={"data-testid": "company-name"})
        if not company_elem:
            company_elem = card.find("span", class_=re.compile("companyName"))
        if not company_elem:
            company_elem = card.find("span", class_=re.compile("css-1h7lukg"))

        # Location - try multiple selectors
        location_elem = card.find("div", attrs={"data-testid": "text-location"})
        if not location_elem:
            location_elem = card.find("div", class_=re.compile("companyLocation"))

        # Link - try data-jk attribute first, then any href
        link_elem = card.find("a", attrs={"data-jk": True})
        if not link_elem:
            link_elem = card.find("a", href=True)

        # Date - try multiple selectors
        date_elem = card.find("span", class_=re.compile("date"))
        if not date_elem:
            date_elem = card.find("span", attrs={"data-testid": "myJobsStateDate"})

        title = title_elem.get_text(strip=True) if title_elem else ""
        company = company_elem.get_text(strip=True) if company_elem else ""
        location = location_elem.get_text(strip=True) if location_elem else ""
        posting_date = _parse_relative_date(date_elem.get_text(strip=True)) if date_elem else date.today()
        url = ""
        if link_elem and link_elem.get("href"):
            href = link_elem["href"]
            if href.startswith("/"):
                url = f"{indeed_base}{href}"
            else:
                url = href

        if title:
            results.append(JobDiscovery(
                title=title,
                company=company,
                location=location,
                url=url,
                source=source,
                posting_date=posting_date,
            ))

    # Fallback parser for markup changes.
    if not results:
        seen_urls = set()
        anchors = soup.find_all("a", href=re.compile(r"/viewjob|/rc/clk"))
        for anchor in anchors:
            title = anchor.get_text(strip=True)
            if not title:
                continue
            href = anchor.get("href", "")
            if href.startswith("/"):
                url = f"{indeed_base}{href}"
            else:
                url = href
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append(
                JobDiscovery(
                    title=title,
                    company="",
                    location="",
                    url=url,
                    source=source,
                    posting_date=date.today(),
                )
            )
            if len(results) >= 20:
                break

    return results


def _parse_linkedin(soup: BeautifulSoup, source: str) -> list[JobDiscovery]:
    """Parse LinkedIn Jobs search results (public, no auth).

    Args:
        soup: BeautifulSoup object of the LinkedIn search results page
        source: Source identifier (clean: "linkedin", not "linkedin_us")

    Returns:
        List of JobDiscovery objects (market field set by caller)
    """
    results = []

    # Try multiple card selectors
    job_cards = soup.find_all("div", class_=re.compile("base-card"))
    if not job_cards:
        job_cards = soup.find_all("li", class_=re.compile("result-card"))
    if not job_cards:
        job_cards = soup.find_all("div", class_=re.compile("job-search-card"))

    logger.info("LinkedIn parser: found %d job cards", len(job_cards))

    for card in job_cards[:20]:
        # Title - try multiple selectors
        title_elem = card.find("h3", class_=re.compile("base-search-card__title"))
        if not title_elem:
            title_elem = card.find("h3", class_=re.compile("job-search-card__title"))

        # Company - try multiple selectors
        company_elem = card.find("h4", class_=re.compile("base-search-card__subtitle"))
        if not company_elem:
            company_elem = card.find("a", class_=re.compile("job-search-card__subtitle-link"))
        if not company_elem:
            company_elem = card.find("h4", class_=re.compile("job-search-card__subtitle"))

        # Location - try multiple selectors
        location_elem = card.find("span", class_=re.compile("job-search-card__location"))
        if not location_elem:
            location_elem = card.find("span", class_=re.compile("base-search-card__metadata"))

        # Link - try multiple selectors
        link_elem = card.find("a", class_=re.compile("base-card__full-link"))
        if not link_elem:
            # Look for any anchor with href containing /jobs/view/
            link_elem = card.find("a", href=re.compile("/jobs/view/"))
        if not link_elem:
            link_elem = card.find("a", href=True)

        # Date
        date_elem = card.find("time", attrs={"datetime": True})

        title = title_elem.get_text(strip=True) if title_elem else ""
        company = company_elem.get_text(strip=True) if company_elem else ""
        location = location_elem.get_text(strip=True) if location_elem else ""
        url = link_elem["href"] if link_elem and link_elem.get("href") else ""
        posting_date = _parse_relative_date(date_elem.get_text(strip=True)) if date_elem else date.today()

        if title:
            results.append(JobDiscovery(
                title=title,
                company=company,
                location=location,
                url=url,
                source=source,
                posting_date=posting_date,
            ))

    return results


def _parse_wellfound(soup: BeautifulSoup, source: str) -> list[JobDiscovery]:
    """Parse Wellfound jobs from generic anchor-based markup.

    Args:
        soup: BeautifulSoup object of the Wellfound search results page
        source: Source identifier (clean: "wellfound", not "wellfound_us")

    Returns:
        List of JobDiscovery objects (market field set by caller)
    """
    results = []
    seen_urls = set()

    all_anchors = soup.find_all("a", href=True)
    logger.info("Wellfound parser: checking %d anchors", len(all_anchors))

    for link in all_anchors:
        href = link.get("href", "")
        if "/jobs/" not in href:
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        url = href if href.startswith("http") else f"https://wellfound.com{href}"
        if url in seen_urls:
            continue
        seen_urls.add(url)

        results.append(
            JobDiscovery(
                title=title,
                company="",
                location="",
                url=url,
                source=source,
                posting_date=date.today(),
            )
        )

        if len(results) >= 20:
            break

    return results


def _parse_relative_date(text: str) -> date:
    """Parse relative dates like '3 days ago', 'Just posted', 'Today'.

    Args:
        text: Date text from job board (e.g., "3 days ago", "Just posted")

    Returns:
        Parsed date object, defaults to today if unable to parse
    """
    text = text.lower().strip()

    # Handle "just posted" or "today"
    if "just" in text or "today" in text or "hoy" in text:
        return date.today()

    # Handle "X days ago"
    match = re.search(r"(\d+)\s*day", text)
    if match:
        days = int(match.group(1))
        return date.today() - timedelta(days=days)
    match = re.search(r"hace\s*(\d+)\s*d[ií]a", text)
    if match:
        days = int(match.group(1))
        return date.today() - timedelta(days=days)

    # Handle "X hours ago" (treat as today)
    match = re.search(r"(\d+)\s*hour", text)
    if match:
        return date.today()
    if "ayer" in text:
        return date.today() - timedelta(days=1)

    # Handle "X weeks ago"
    match = re.search(r"(\d+)\s*week", text)
    if match:
        weeks = int(match.group(1))
        return date.today() - timedelta(weeks=weeks)
    match = re.search(r"hace\s*(\d+)\s*semana", text)
    if match:
        weeks = int(match.group(1))
        return date.today() - timedelta(weeks=weeks)

    # Handle "X months ago" (approximate as 30 days)
    match = re.search(r"(\d+)\s*month", text)
    if match:
        months = int(match.group(1))
        return date.today() - timedelta(days=months * 30)

    # Default to today if unparseable
    return date.today()


def rank_discoveries_by_tag_weight(discoveries: list[JobDiscovery | dict]) -> list[JobDiscovery | dict]:
    """Rank discoveries by sum of tag weights from their search_tags.

    Args:
        discoveries: List of JobDiscovery objects or dicts with search_tags field

    Returns:
        Sorted list of discoveries (highest weight first)
    """
    for disc in discoveries:
        total_weight = 0
        # Handle both dict and object formats
        search_tags = disc.get("search_tags") if isinstance(disc, dict) else disc.search_tags
        tags = [t.strip() for t in (search_tags or "").split(",") if t.strip()]
        tag_weights = {}

        for tag in tags:
            weight = tracker_db.get_tag_weight(tag)
            tag_weights[tag] = weight
            total_weight += weight

        if isinstance(disc, dict):
            disc["search_tag_weights"] = tag_weights
        else:
            disc.search_tag_weights = tag_weights

    # Sort by total weight (descending), then by posting_date (descending)
    sorted_discoveries = sorted(
        discoveries,
        key=lambda d: (
            sum(d.get("search_tag_weights", {}).values() if isinstance(d, dict) else d.search_tag_weights.values()),
            (d.get("posting_date") if isinstance(d, dict) else d.posting_date) or date.min
        ),
        reverse=True
    )

    return sorted_discoveries


def search_jobs_async(
    tags: list[str],
    location: str = "",
    sources: list[str] = None,
    markets: list[str] = None,
    pause_check: callable = None,
    progress_callback: callable = None,
    max_results: int = 250
) -> list[JobDiscovery]:
    """Search jobs with pause/resume support and result limit.

    Args:
        tags: List of search tags
        location: Location filter
        sources: List of sources to search (indeed, linkedin, wellfound)
        markets: List of markets to search (us, mx, ca, uk, es, de)
        pause_check: Callback that returns True if search should pause
        progress_callback: Callback(current_count, total_found) for progress updates
        max_results: Maximum number of results to find (default 250)

    Returns:
        List of JobDiscovery objects (may be paused before completion)
    """
    sources = sources or ["indeed", "linkedin"]
    markets = markets or ["us"]

    all_discoveries = []
    total_combinations = len(tags) * len(sources) * len(markets)
    current = 0

    for tag in tags:
        for source in sources:
            for market in markets:
                # Check for pause
                if pause_check and pause_check():
                    logger.info("Search paused at %d/%d combinations", current, total_combinations)
                    return all_discoveries

                # Check result limit BEFORE searching
                if len(all_discoveries) >= max_results:
                    logger.info("Search limit reached: %d results", len(all_discoveries))
                    return all_discoveries

                # Perform search
                results = _search_source(tag, location, source, market)

                # Add results but respect limit
                for result in results:
                    if len(all_discoveries) >= max_results:
                        break
                    all_discoveries.append(result)

                current += 1

                # Progress callback
                if progress_callback:
                    progress_callback(current, len(all_discoveries))

                logger.debug(
                    "Search progress: %d/%d combinations, %d total results",
                    current, total_combinations, len(all_discoveries)
                )

                # Check limit again after adding results
                if len(all_discoveries) >= max_results:
                    logger.info("Search limit reached: %d results", len(all_discoveries))
                    return all_discoveries

    logger.info("Search completed: %d total results from %d combinations", len(all_discoveries), total_combinations)
    return all_discoveries


def save_discoveries(discoveries: list[JobDiscovery]) -> int:
    """Save new discoveries to DB, dedup against both discoveries AND applications tables.

    Args:
        discoveries: List of JobDiscovery objects to save

    Returns:
        Count of newly saved discoveries
    """
    saved = 0
    for disc in discoveries:
        # Check if URL already known in either table
        if disc.url and tracker_db.is_url_known(disc.url):
            continue
        result = tracker_db.add_discovery(disc)
        if result is not None:
            saved += 1
    return saved


def import_discovery_to_application(discovery_id: int) -> Optional[int]:
    """Import a starred discovery into the applications tracker with ALL data.

    Returns application ID if created.
    """
    from jseeker.models import Application
    from jseeker.jd_parser import process_jd

    discoveries = tracker_db.list_discoveries()
    disc = None
    for d in discoveries:
        if d["id"] == discovery_id:
            disc = d
            break

    if not disc:
        return None

    company_id = tracker_db.get_or_create_company(disc.get("company", "Unknown"))

    # If we have a URL, fetch and parse the full JD
    jd_text = ""
    jd_data = None
    if disc.get("url"):
        try:
            from jseeker.jd_parser import extract_jd_from_url
            jd_text, metadata = extract_jd_from_url(disc["url"])

            if jd_text:
                # Parse JD to extract salary, skills, etc.
                jd_data = process_jd(
                    jd_text=jd_text,
                    jd_url=disc["url"],
                    role_title=disc["title"],
                    company_name=disc.get("company", "")
                )
        except Exception as e:
            logger.warning(f"Could not fetch/parse JD for import: {e}")

    # Build application with all available data
    app = Application(
        company_id=company_id,
        role_title=disc["title"],
        jd_text=jd_data.jd_text if jd_data else jd_text,
        jd_url=disc.get("url", ""),
        location=jd_data.location if jd_data else disc.get("location", ""),
        salary_range=jd_data.salary_range if jd_data else disc.get("salary_range", ""),
        salary_min=jd_data.salary_min if jd_data else None,
        salary_max=jd_data.salary_max if jd_data else None,
        salary_currency=jd_data.salary_currency if jd_data else None,
        remote_policy=jd_data.remote_policy if jd_data else None,
        relevance_score=jd_data.relevance_score if jd_data else None,
    )

    app_id = tracker_db.add_application(app)

    # Update discovery status
    tracker_db.update_discovery_status(discovery_id, "imported")

    return app_id
