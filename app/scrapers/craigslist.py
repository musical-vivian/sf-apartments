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
SEARCH_URL = (
    BASE_URL
    + "/search/sfc/apa"
    "?max_price=3500"
    "&min_bedrooms=0&max_bedrooms=1"
    "&min_sqft=500"
    "&availabilityMode=0"
    "&hasPic=1"
    "&laundry=1"           # in-unit W/D (Craigslist native filter)
    "&air_conditioning=1"  # has AC (Craigslist native filter)
)


class CraigslistScraper(BaseScraper):
    def scrape(self) -> List[ListingData]:
        listings = []
        offset = 0
        while True:
            url = SEARCH_URL + f"&s={offset}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"Craigslist fetch failed (offset={offset}): {e}")
                break

            soup = BeautifulSoup(resp.text, "lxml")
            results = soup.select("li.cl-search-result")
            if not results:
                break

            for result in results:
                try:
                    listing = self._parse_result(result)
                    if listing:
                        listings.append(listing)
                except Exception as e:
                    logger.warning(f"CL parse error: {e}")

            # Craigslist returns 120 results per page
            if len(results) < 120:
                break
            offset += 120
            time.sleep(1)

        # Enrich new-looking listings with full page details (AC, W/D)
        for listing in listings:
            try:
                self._enrich(listing)
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"CL enrich error for {listing.external_id}: {e}")

        return listings

    def _parse_result(self, result) -> Optional[ListingData]:
        link = result.select_one("a.posting-title") or result.select_one("a[href*='/apa/']")
        if not link:
            return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = BASE_URL + url

        match = re.search(r"/(\d{10,})\.html", url)
        if not match:
            return None
        external_id = match.group(1)

        title = link.get_text(strip=True)

        price = None
        price_el = result.select_one(".priceinfo") or result.select_one(".price")
        if price_el:
            m = re.search(r"\d[\d,]*", price_el.get_text())
            if m:
                price = int(m.group().replace(",", ""))

        bedrooms = None
        sqft = None
        housing_el = result.select_one(".housing")
        if housing_el:
            ht = housing_el.get_text().lower()
            if "studio" in ht:
                bedrooms = "studio"
            elif "1br" in ht or "1 br" in ht:
                bedrooms = "1br"
            m = re.search(r"(\d{3,4})ft", ht)
            if m:
                sqft = int(m.group(1))

        neighborhood = None
        loc_el = result.select_one(".cl-app-anchor.maptag") or result.select_one(".meta .maptag")
        if loc_el:
            neighborhood = loc_el.get_text(strip=True)

        image_url = None
        img = result.select_one("img")
        if img:
            image_url = img.get("src") or img.get("data-src")

        return ListingData(
            source="craigslist",
            external_id=external_id,
            title=title,
            url=url,
            price=price,
            bedrooms=bedrooms,
            sqft=sqft,
            neighborhood=neighborhood,
            image_url=image_url,
        )

    def _enrich(self, listing: ListingData):
        resp = requests.get(listing.url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        attrs_text = " ".join(
            span.get_text(strip=True).lower()
            for span in soup.select(".attrgroup span")
        )

        listing.has_ac = any(
            kw in attrs_text for kw in ["air conditioning", "central air", "a/c", "ac unit"]
        )
        listing.has_washer_dryer = any(
            kw in attrs_text
            for kw in ["in-unit laundry", "washer/dryer", "w/d in unit", "laundry in unit", "washer in unit"]
        )

        if not listing.sqft:
            m = re.search(r"(\d{3,4})\s*ft", attrs_text)
            if m:
                listing.sqft = int(m.group(1))

        desc_el = soup.select_one("#postingbody")
        if desc_el:
            listing.description = desc_el.get_text(strip=True)[:800]

        if not listing.image_url:
            img = soup.select_one("#thumbs img") or soup.select_one(".iw img")
            if img:
                listing.image_url = img.get("src")
