"""Helper utilities for detecting, scraping titles from, and formatting external recipe URLs."""

import logging
import re
from typing import Optional, Tuple
from urllib.parse import urlparse
import httpx

logger = logging.getLogger("url_helper")

URL_REGEX = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def extract_url_from_text(text: str) -> Optional[str]:
    """Find the first HTTP or HTTPS URL in the provided text."""
    if not text:
        return None
    match = URL_REGEX.search(text.strip())
    return match.group(0) if match else None


def clean_domain(url: str) -> str:
    """Extract a user-friendly domain name (e.g., 'seriouseats.com')."""
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or "website"
    except Exception:
        return "website"


def slug_to_title(url: str) -> str:
    """Generate a clean title fallback from a URL path slug."""
    try:
        path = urlparse(url).path.strip("/")
        if path:
            segments = [s for s in path.split("/") if s]
            if segments:
                last = segments[-1]
                # Remove file extensions (.html, .php, etc.)
                last = re.sub(r"\.(html|htm|php|asp|aspx)$", "", last, flags=re.IGNORECASE)
                # Remove leading/trailing digits or IDs
                last = re.sub(r"^[0-9]+-", "", last)
                clean = re.sub(r"[-_]+", " ", last).strip().title()
                if clean and len(clean) >= 3:
                    return clean
    except Exception:
        pass
    domain = clean_domain(url)
    return f"Recipe from {domain}"


def clean_page_title(title: str) -> str:
    """Strip website suffixes like ' | Serious Eats' or ' - Allrecipes' from titles."""
    if not title:
        return ""
    # Strip HTML entities if any
    cleaned = (
        title.replace("&amp;", "&")
        .replace("&#039;", "'")
        .replace("&quot;", '"')
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    # Common separators between dish title and site brand
    cleaned = re.sub(
        r"\s*([|•–—]| - )\s*(allrecipes|serious eats|nyt cooking|food network|bon app[eé]tit|smitten kitchen|budget bytes|king arthur|delish|epicurious|tasty|bbc good food|the kitchn|cooking light|food & wine|simply recipes|cookie and kate|half baked harvest|damned delicious|gimme some oven|love and lemons|minimalist baker|pinch of yum).*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    # Generic trailing ' | ...' or ' - ...' if still present
    cleaned = re.sub(r"\s*[|•]\s*[^|•]+$", "", cleaned).strip()
    return cleaned or title.strip()


async def fetch_recipe_url_info(url: str) -> Tuple[str, str]:
    """Fetch external webpage title and domain with quick timeout.

    Returns:
        (title, domain)
    """
    domain = clean_domain(url)
    fallback_title = slug_to_title(url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                html = resp.text[:120000]  # Only inspect initial HTML block for head tags

                # 1. Check og:title
                og_match = re.search(
                    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
                    html,
                    re.IGNORECASE,
                )
                if not og_match:
                    og_match = re.search(
                        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
                        html,
                        re.IGNORECASE,
                    )

                if og_match:
                    candidate = clean_page_title(og_match.group(1))
                    if candidate and len(candidate) > 2:
                        return candidate, domain

                # 2. Check <title> tag
                title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
                if title_match:
                    candidate = clean_page_title(title_match.group(1))
                    if candidate and len(candidate) > 2:
                        return candidate, domain
    except Exception as e:
        logger.debug(f"Could not scrape title from {url}: {e}")

    return fallback_title, domain
