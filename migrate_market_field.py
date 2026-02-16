"""Migration script to populate market field from location strings.

This fixes the issue where 1066 jobs show as "unknown" market because they were
saved before the market field was properly implemented.
"""

import re
import sqlite3
from pathlib import Path


def infer_market_from_location(location: str) -> str:
    """Infer market code from location string.

    Args:
        location: Location string like "Arhus, Denmark" or "Austin, TX" or "Mexico City, Mexico"

    Returns:
        Market code: "us", "mx", "ca", "uk", "es", "dk", "fr", "de", or "unknown"
    """
    if not location:
        return "unknown"

    location_lower = location.lower()

    # Country patterns (most specific first)
    country_patterns = {
        "denmark": "dk",
        "spain": "es",
        "mexico": "mx",
        "canada": "ca",
        "united kingdom": "uk",
        "united states": "us",  # Handle generic "United States" location
        "france": "fr",
        "germany": "de",
    }

    # Check for explicit country names
    for country, code in country_patterns.items():
        if country in location_lower:
            return code

    # US state patterns (two-letter codes and full names)
    us_states = [
        "al",
        "ak",
        "az",
        "ar",
        "ca",
        "co",
        "ct",
        "de",
        "fl",
        "ga",
        "hi",
        "id",
        "il",
        "in",
        "ia",
        "ks",
        "ky",
        "la",
        "me",
        "md",
        "ma",
        "mi",
        "mn",
        "ms",
        "mo",
        "mt",
        "ne",
        "nv",
        "nh",
        "nj",
        "nm",
        "ny",
        "nc",
        "nd",
        "oh",
        "ok",
        "or",
        "pa",
        "ri",
        "sc",
        "sd",
        "tn",
        "tx",
        "ut",
        "vt",
        "va",
        "wa",
        "wv",
        "wi",
        "wy",
    ]

    us_state_names = [
        "alabama",
        "alaska",
        "arizona",
        "arkansas",
        "california",
        "colorado",
        "connecticut",
        "delaware",
        "florida",
        "georgia",
        "hawaii",
        "idaho",
        "illinois",
        "indiana",
        "iowa",
        "kansas",
        "kentucky",
        "louisiana",
        "maine",
        "maryland",
        "massachusetts",
        "michigan",
        "minnesota",
        "mississippi",
        "missouri",
        "montana",
        "nebraska",
        "nevada",
        "new hampshire",
        "new jersey",
        "new mexico",
        "new york",
        "north carolina",
        "north dakota",
        "ohio",
        "oklahoma",
        "oregon",
        "pennsylvania",
        "rhode island",
        "south carolina",
        "south dakota",
        "tennessee",
        "texas",
        "utah",
        "vermont",
        "virginia",
        "washington",
        "west virginia",
        "wisconsin",
        "wyoming",
    ]

    # Check for full state names
    for state_name in us_state_names:
        if state_name in location_lower:
            return "us"

    # Check for state abbreviations (word boundary required)
    # Pattern: ", TX" or " TX" at end
    for state_code in us_states:
        pattern = rf"[,\s]{state_code}(?:\s|$)"
        if re.search(pattern, location_lower):
            return "us"

    # US city patterns (common US cities)
    us_cities = [
        "new york",
        "los angeles",
        "chicago",
        "houston",
        "phoenix",
        "philadelphia",
        "san antonio",
        "san diego",
        "dallas",
        "san jose",
        "austin",
        "jacksonville",
        "fort worth",
        "columbus",
        "charlotte",
        "san francisco",
        "indianapolis",
        "seattle",
        "denver",
        "washington",
        "boston",
        "nashville",
        "baltimore",
        "detroit",
        "memphis",
        "portland",
        "las vegas",
        "milwaukee",
        "albuquerque",
        "tucson",
        "fresno",
        "sacramento",
        "mesa",
        "kansas city",
        "atlanta",
        "long beach",
        "colorado springs",
        "raleigh",
        "miami",
        "virginia beach",
        "omaha",
        "oakland",
        "minneapolis",
        "tulsa",
        "arlington",
        "alpharetta",
        "remote",
    ]

    for city in us_cities:
        if city in location_lower:
            return "us"

    # Canadian city patterns
    canadian_cities = [
        "toronto",
        "montreal",
        "vancouver",
        "calgary",
        "edmonton",
        "ottawa",
        "winnipeg",
        "quebec",
        "hamilton",
        "kitchener",
    ]

    for city in canadian_cities:
        if city in location_lower:
            return "ca"

    # UK city patterns
    uk_cities = [
        "london",
        "manchester",
        "birmingham",
        "glasgow",
        "liverpool",
        "edinburgh",
        "leeds",
        "sheffield",
        "bristol",
        "cardiff",
    ]

    for city in uk_cities:
        if city in location_lower:
            return "uk"

    # European city patterns
    european_cities = {
        "paris": "fr",
        "marseille": "fr",
        "lyon": "fr",
        "toulouse": "fr",
        "madrid": "es",
        "barcelona": "es",
        "valencia": "es",
        "seville": "es",
        "copenhagen": "dk",
        "aarhus": "dk",
        "arhus": "dk",  # Alternative spelling
        "odense": "dk",
        "berlin": "de",
        "munich": "de",
        "hamburg": "de",
        "frankfurt": "de",
    }

    for city, code in european_cities.items():
        if city in location_lower:
            return code

    # Mexican city patterns
    mexican_cities = [
        "mexico city",
        "guadalajara",
        "monterrey",
        "puebla",
        "tijuana",
        "ciudad",
        "cdmx",
        "cuajimalpa",
        "tlalpan",
    ]

    for city in mexican_cities:
        if city in location_lower:
            return "mx"

    # Default: if no match, return unknown
    return "unknown"


def migrate_market_field():
    """Migrate existing job discoveries to populate market field."""
    db_path = Path("data/jseeker.db")

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Get all jobs with NULL, empty, or unknown market
    rows = c.execute("""
        SELECT id, location FROM job_discoveries
        WHERE market IS NULL OR market = '' OR market = 'unknown'
    """).fetchall()

    print(f"Found {len(rows)} jobs with NULL/empty market field")

    if not rows:
        print("No migration needed - all jobs have market set")
        conn.close()
        return

    # Update each job
    updated = 0
    by_market = {}

    for job_id, location in rows:
        market = infer_market_from_location(location)

        c.execute(
            """
            UPDATE job_discoveries
            SET market = ?
            WHERE id = ?
        """,
            (market, job_id),
        )

        by_market[market] = by_market.get(market, 0) + 1
        updated += 1

    conn.commit()
    conn.close()

    print("\nMigration complete!")
    print(f"Updated {updated} jobs")
    print("\nBreakdown by market:")
    for market, count in sorted(by_market.items(), key=lambda x: -x[1]):
        print(f"  {market}: {count} jobs")


if __name__ == "__main__":
    migrate_market_field()
