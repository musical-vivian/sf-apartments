import re
import json
import urllib.parse
import logging
from typing import List, Optional

import requests

from .base import BaseScraper, ListingData

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

_FILTER_STATE = {
    "price": {"max": 3500},
    "beds": {"max": 1},
    "sqft": {"min": 500},
    "rentHomes": {"value": True},
    "hasAirConditioning": {"value": True},   # AC filter
    "hasInUnitLaundry": {"value": True},     # in-unit W/D filter
}
_SEARCH_QUERY = urllib.parse.quote(json.dumps({"filterState": _FILTER_STATE}))
SEARCH_URL = f"https://www.zillow.com/san-francisco-ca/rentals/?searchQueryState={_SEARCH_QUERY}"


class ZillowScraper(BaseScraper):
    """
    Parses Zillow's __NEXT_DATA__ JSON payload embedded in the page HTML.
    Note: Zillow has aggressive bot detection — this may occasionally fail.
    """

    def scrape(self) -> List[ListingData]:
        listings = []
        try:
            resp = requests.get(SEARCH_URL, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = self._extract_next_data(resp.text)
            if not data:
                logger.warning("Zillow: could not extract __NEXT_DATA__")
                return listings

            results = self._find_listings(data)
            for item in results:
                try:
                    listing = self._parse_item(item)
                    if listing:
                        listings.append(listing)
                except Exception as e:
                    logger.warning(f"Zillow parse error: {e}")

        except Exception as e:
            logger.error(f"Zillow scrape failed: {e}")

        return listings

    def _extract_next_data(self, html: str) -> Optional[dict]:
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        return None

    def _find_listings(self, data: dict) -> list:
        try:
            cat1 = (
                data["props"]["pageProps"]["searchPageState"]["cat1"]
            )
            return cat1["searchResults"]["listResults"]
        except (KeyError, TypeError):
            pass
        # Fallback: search recursively for listResults key
        return self._deep_find(data, "listResults") or []

    def _deep_find(self, obj, key):
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            for v in obj.values():
                result = self._deep_find(v, key)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._deep_find(item, key)
                if result:
                    return result
        return None

    def _parse_item(self, item: dict) -> Optional[ListingData]:
        url = item.get("detailUrl", "")
        if not url.startswith("http"):
            url = "https://www.zillow.com" + url

        external_id = item.get("zpid") or item.get("id")
        if not external_id:
            return None
        external_id = str(external_id)

        title = item.get("address") or item.get("streetAddress") or ""

        price = None
        price_str = item.get("price") or item.get("unformattedPrice") or ""
        m = re.search(r"\d[\d,]*", str(price_str))
        if m:
            price = int(m.group().replace(",", ""))

        bedrooms = None
        beds = item.get("beds") or item.get("minBeds")
        if beds is not None:
            if str(beds) in ("0", "studio"):
                bedrooms = "studio"
            elif str(beds) == "1":
                bedrooms = "1br"

        sqft = None
        area = item.get("area") or item.get("livingArea")
        if area:
            try:
                sqft = int(str(area).replace(",", ""))
            except ValueError:
                pass

        neighborhood = item.get("addressState") or None
        address = item.get("address") or None

        image_url = None
        imgs = item.get("carouselPhotos") or item.get("imgSrc")
        if isinstance(imgs, list) and imgs:
            image_url = imgs[0].get("url") or imgs[0]
        elif isinstance(imgs, str):
            image_url = imgs

        return ListingData(
            source="zillow",
            external_id=external_id,
            title=title,
            url=url,
            price=price,
            bedrooms=bedrooms,
            sqft=sqft,
            neighborhood=neighborhood,
            address=address,
            image_url=image_url,
        )
