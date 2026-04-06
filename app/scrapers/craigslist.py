"""
Craigslist scraper — uses the RSS feed for stable parsing.
The HTML UI changes frequently; the RSS format is far more reliable.
"""
import re
import time
import logging
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, ListingData

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )
}

BASE_URL = "https://sfbay.craigslist.org"
# laundry=1 = in-unit W/D (valid CL filter param)
# Note: air_conditioning is not a valid CL URL param — we detect it from listing text
RSS_URL = (
    BASE_URL + "/search/sfc/apa"
    "?format=rss"
    "&max_price=3500"
    "&min_bedrooms=0&max_bedrooms=1"
    "&min_sqft=500"
    "&laundry=1"
    "&availabilityMode=0"
    "&hasPic=1"
)


class CraigslistScraper(BaseScraper):
    def scrape(self) -> List[ListingData]:
        listings = []
        offset = 0

        while True:
            url = RSS_URL + f"&s={offset}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"Craigslist RSS fetch failed (offset={offset}): {e}")
                break

            soup = BeautifulSoup(resp.text, "xml")
            items = soup.find_all("item")
            if not items:
                break

            for item in items:
                try:
                    listing = self._parse_item(item)
                    if listing:
                        listings.append(listing)
                except Exception as e:
                    logger.warning(f"CL item parse error: {e}")

            if len(items) < 120:
                break
            offset += 120
            time.sleep(1)

        # Enrich listings for AC and extra details
        for listing in listings:
            try:
                self._enrich(listing)
                time.sleep(0.4)
            except Exception as e:
                logger.warning(f"CL enrich error {listing.external_id}: {e}")

        return listings

    def _parse_item(self, item) -> Optional[ListingData]:
        link_tag = item.find("link")
        if not link_tag:
            return None
        # In RSS, <link> text is sometimes after a newline
        url = (link_tag.next_sibling or link_tag.get_text()).strip()
        if not url.startswith("http"):
            return None

        match = re.search(r"/(\d{10,})\.html", url)
        if not match:
            return None
        external_id = match.group(1)

        title_tag = item.find("title")
        raw_title = title_tag.get_text(strip=True) if title_tag else ""

        # Parse price from title: "$2,800 1br - ..."
        price = None
        m = re.search(r"\$\s*([\d,]+)", raw_title)
        if m:
            price = int(m.group(1).replace(",", ""))

        # Bedrooms from title
        bedrooms = None
        tl = raw_title.lower()
        if "studio" in tl:
            bedrooms = "studio"
        elif re.search(r"1\s*br\b", tl):
            bedrooms = "1br"

        # Sqft from title: "645ft" or "645 ft²"
        sqft = None
        m = re.search(r"(\d{3,4})\s*ft", raw_title, re.IGNORECASE)
        if m:
            sqft = int(m.group(1))

        # Neighborhood from title (text in parentheses)
        neighborhood = None
        m = re.search(r"\(([^)]+)\)", raw_title)
        if m:
            neighborhood = m.group(1).strip()

        # Image from enclosure
        image_url = None
        enc = item.find("enclosure")
        if enc:
            image_url = enc.get("resource") or enc.get("url")

        # Since we filtered with laundry=1, all results have in-unit W/D
        return ListingData(
            source="craigslist",
            external_id=external_id,
            title=raw_title,
            url=url,
            price=price,
            bedrooms=bedrooms,
            sqft=sqft,
            has_washer_dryer=True,   # guaranteed by laundry=1 filter
            has_ac=None,             # checked in _enrich
            neighborhood=neighborhood,
            image_url=image_url,
        )

    def _enrich(self, listing: ListingData):
        resp = requests.get(listing.url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        attrs_text = " ".join(
            span.get_text(strip=True).lower()
            for span in soup.select(".attrgroup span, .mapAndAttrs span")
        )
        # Also check full body text for AC mentions
        body = soup.select_one("#postingbody")
        body_text = body.get_text().lower() if body else ""
        full_text = attrs_text + " " + body_text

        listing.has_ac = any(
            kw in full_text
            for kw in ["air conditioning", "central air", "a/c", "ac unit", "air-conditioning"]
        )

        if not listing.sqft:
            m = re.search(r"(\d{3,4})\s*(?:sq\s*ft|ft²|sqft)", full_text)
            if m:
                listing.sqft = int(m.group(1))

        if body:
            listing.description = body.get_text(strip=True)[:800]

        if not listing.image_url:
            img = soup.select_one("#thumbs img, .iw img")
            if img:
                listing.image_url = img.get("src")
