"""
Resilient API clients for academic metadata retrieval.

Implements three API clients — Crossref, DataCite, and OpenAlex — with
shared resilience features: exponential backoff retry, timeout handling,
rate-limit awareness (HTTP 429), and standardized output via GroundTruth.
"""

import logging
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import (
    CROSSREF_API_BASE,
    CROSSREF_MAILTO,
    DATACITE_API_BASE,
    DATACITE_DOI_PREFIXES,
    GroundTruth,
    MAX_RETRIES,
    OPENALEX_API_BASE,
    OPENALEX_MAILTO,
    RATE_LIMIT_429_WAIT,
    RATE_LIMIT_DELAY,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF_FACTOR,
    USER_AGENT,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Shared Session Factory
# ─────────────────────────────────────────────────────────────────────

def _create_session() -> requests.Session:
    """
    Create an HTTP session with connection pooling and automatic retry.

    Retry policy:
        - 3 attempts with exponential backoff (1s, 2s, 4s)
        - Retries on 429 (rate limit), 500, 502, 503, 504
        - Respects Retry-After header on 429 responses

    Returns:
        Configured requests.Session instance.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })

    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=10,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


# ─────────────────────────────────────────────────────────────────────
# Crossref Client
# ─────────────────────────────────────────────────────────────────────

class CrossrefClient:
    """
    Client for the Crossref REST API.

    Handles journal/conference DOIs (the majority of academic DOIs).
    Uses the polite pool via mailto for better service quality.
    """

    def __init__(self):
        self.session = _create_session()
        self.base_url = CROSSREF_API_BASE
        self._last_request_time = 0.0

    def _rate_limit(self):
        """Enforce minimum delay between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def fetch_by_doi(self, doi: str) -> Optional[GroundTruth]:
        """
        Retrieve metadata for a DOI from Crossref.

        Args:
            doi: A DOI string (e.g., "10.1145/3397271.3401075").

        Returns:
            GroundTruth object with extracted metadata, or None on failure.
        """
        url = f"{self.base_url}/{doi}"
        params = {"mailto": CROSSREF_MAILTO}
        self._rate_limit()

        try:
            resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 404:
                logger.info("Crossref: DOI not found: %s", doi)
                return None

            if resp.status_code == 429:
                logger.warning("Crossref: Rate limited. Waiting %ss...", RATE_LIMIT_429_WAIT)
                time.sleep(RATE_LIMIT_429_WAIT)
                resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)

            resp.raise_for_status()
            data = resp.json().get("message", {})

            return GroundTruth(
                doi=data.get("DOI", doi),
                title=self._extract_title(data),
                authors=self._extract_authors(data),
                year=self._extract_year(data),
                source_journal=self._extract_journal(data),
                api_source="Crossref",
                is_retracted=self._check_retracted(data),
            )

        except requests.exceptions.RequestException as e:
            logger.error("Crossref API error for DOI %s: %s", doi, e)
            return None

    def search_by_title(self, title: str, rows: int = 3) -> Optional[GroundTruth]:
        """
        Search Crossref by bibliographic query (title-based).

        Args:
            title: Title string to search for.
            rows: Number of results to retrieve (default 3).

        Returns:
            Best-matching GroundTruth, or None.
        """
        params = {
            "query.bibliographic": title,
            "rows": rows,
            "mailto": CROSSREF_MAILTO,
        }
        self._rate_limit()

        try:
            resp = self.session.get(self.base_url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            items = resp.json().get("message", {}).get("items", [])

            if not items:
                return None

            # Return the top result (Crossref ranks by relevance)
            best = items[0]
            return GroundTruth(
                doi=best.get("DOI"),
                title=self._extract_title(best),
                authors=self._extract_authors(best),
                year=self._extract_year(best),
                source_journal=self._extract_journal(best),
                api_source="Crossref",
            )

        except requests.exceptions.RequestException as e:
            logger.error("Crossref search error: %s", e)
            return None

    @staticmethod
    def _extract_title(data: dict) -> Optional[str]:
        titles = data.get("title", [])
        return titles[0] if titles else None

    @staticmethod
    def _extract_authors(data: dict) -> list:
        authors = []
        for author in data.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            if family:
                authors.append(f"{given} {family}".strip())
        return authors

    @staticmethod
    def _extract_year(data: dict) -> Optional[int]:
        # Try published-print, then published-online, then issued
        for key in ("published-print", "published-online", "issued"):
            date_parts = data.get(key, {}).get("date-parts", [[]])
            if date_parts and date_parts[0]:
                try:
                    return int(date_parts[0][0])
                except (ValueError, IndexError):
                    continue
        return None

    @staticmethod
    def _extract_journal(data: dict) -> Optional[str]:
        names = data.get("container-title", [])
        return names[0] if names else None

    @staticmethod
    def _check_retracted(data: dict) -> bool:
        """
        Check if a Crossref work has been retracted.

        Uses three detection methods:
        1. 'update-to' field with type 'retraction' or 'withdrawal'
        2. 'relation' field containing retraction references
        3. Title prefix: publishers often prepend 'RETRACTED:' to the title
        """
        # Method 1: update-to field
        for update in data.get("update-to", []):
            update_type = update.get("type", "").lower()
            if update_type in ("retraction", "withdrawal"):
                return True

        # Method 2: relation field (used by some publishers)
        for rel_type, rels in data.get("relation", {}).items():
            if "retract" in rel_type.lower():
                return True

        # Method 3: title prefix (Lancet, Springer, Elsevier convention)
        titles = data.get("title", [])
        if titles:
            title_lower = titles[0].lower()
            if title_lower.startswith(("retracted:", "retracted ", "withdrawn:")):
                return True

        return False


# ─────────────────────────────────────────────────────────────────────
# DataCite Client
# ─────────────────────────────────────────────────────────────────────

class DataCiteClient:
    """
    Client for the DataCite REST API.

    Handles arXiv DOIs (10.48550/arXiv.*) and dataset DOIs that
    Crossref does not index.
    """

    def __init__(self):
        self.session = _create_session()
        self.base_url = DATACITE_API_BASE
        self._last_request_time = 0.0

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def fetch_by_doi(self, doi: str) -> Optional[GroundTruth]:
        """
        Retrieve metadata for a DOI from DataCite.

        Args:
            doi: A DOI string (e.g., "10.48550/arXiv.2005.11401").

        Returns:
            GroundTruth object, or None on failure.
        """
        url = f"{self.base_url}/{doi}"
        self._rate_limit()

        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 404:
                logger.info("DataCite: DOI not found: %s", doi)
                return None

            if resp.status_code == 429:
                logger.warning("DataCite: Rate limited. Waiting %ss...", RATE_LIMIT_429_WAIT)
                time.sleep(RATE_LIMIT_429_WAIT)
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)

            resp.raise_for_status()
            data = resp.json().get("data", {}).get("attributes", {})

            return GroundTruth(
                doi=doi,
                title=self._extract_title(data),
                authors=self._extract_authors(data),
                year=self._extract_year(data),
                source_journal=None,  # DataCite rarely has journal info
                api_source="DataCite",
            )

        except requests.exceptions.RequestException as e:
            logger.error("DataCite API error for DOI %s: %s", doi, e)
            return None

    @staticmethod
    def _extract_title(data: dict) -> Optional[str]:
        titles = data.get("titles", [])
        if titles:
            return titles[0].get("title")
        return None

    @staticmethod
    def _extract_authors(data: dict) -> list:
        authors = []
        for creator in data.get("creators", []):
            name = creator.get("name", "")
            if not name:
                given = creator.get("givenName", "")
                family = creator.get("familyName", "")
                name = f"{given} {family}".strip()
            if name:
                authors.append(name)
        return authors

    @staticmethod
    def _extract_year(data: dict) -> Optional[int]:
        year = data.get("publicationYear")
        if year:
            try:
                return int(year)
            except (ValueError, TypeError):
                pass
        return None


# ─────────────────────────────────────────────────────────────────────
# OpenAlex Client
# ─────────────────────────────────────────────────────────────────────

class OpenAlexClient:
    """
    Client for the OpenAlex API.

    Used as a cross-validator for results from Crossref/DataCite,
    and as a fallback for title-based search when no DOI is available.
    """

    def __init__(self):
        self.session = _create_session()
        self.base_url = OPENALEX_API_BASE
        self._last_request_time = 0.0

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def fetch_by_doi(self, doi: str) -> Optional[GroundTruth]:
        """
        Look up a work by DOI in OpenAlex.

        Args:
            doi: A DOI string.

        Returns:
            GroundTruth object, or None on failure.
        """
        url = f"{self.base_url}/doi:{doi}"
        params = {"mailto": OPENALEX_MAILTO}
        self._rate_limit()

        try:
            resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 404:
                logger.info("OpenAlex: DOI not found: %s", doi)
                return None

            resp.raise_for_status()
            data = resp.json()
            return self._parse_work(data)

        except requests.exceptions.RequestException as e:
            logger.error("OpenAlex DOI lookup error for %s: %s", doi, e)
            return None

    def search_by_title(self, title: str, per_page: int = 3) -> Optional[GroundTruth]:
        """
        Search OpenAlex by title text.

        Used as a fallback when no DOI is available in the reference.

        Args:
            title: Title string to search for.
            per_page: Number of results (default 3).

        Returns:
            Best-matching GroundTruth, or None.
        """
        params = {
            "search": title,
            "per_page": per_page,
            "mailto": OPENALEX_MAILTO,
        }
        self._rate_limit()

        try:
            resp = self.session.get(self.base_url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            results = resp.json().get("results", [])

            if not results:
                return None

            return self._parse_work(results[0])

        except requests.exceptions.RequestException as e:
            logger.error("OpenAlex search error: %s", e)
            return None

    def _parse_work(self, data: dict) -> GroundTruth:
        """Parse an OpenAlex work object into a GroundTruth."""
        # Extract authors
        authors = []
        for authorship in data.get("authorships", []):
            author = authorship.get("author", {})
            name = author.get("display_name", "")
            if name:
                authors.append(name)

        # Extract journal
        source = None
        primary_location = data.get("primary_location", {})
        if primary_location:
            source_obj = primary_location.get("source")
            if source_obj:
                source = source_obj.get("display_name")

        return GroundTruth(
            doi=data.get("doi", "").replace("https://doi.org/", "") if data.get("doi") else None,
            title=data.get("title"),
            authors=authors,
            year=data.get("publication_year"),
            source_journal=source,
            api_source="OpenAlex",
            is_retracted=bool(data.get("is_retracted", False)),
        )


# ─────────────────────────────────────────────────────────────────────
# API Router
# ─────────────────────────────────────────────────────────────────────

def route_doi_to_api(doi: str) -> str:
    """
    Determine which API to query first based on the DOI prefix.

    Args:
        doi: A DOI string.

    Returns:
        "DataCite" or "Crossref".
    """
    for prefix in DATACITE_DOI_PREFIXES:
        if doi.lower().startswith(prefix.lower()):
            return "DataCite"
    return "Crossref"
