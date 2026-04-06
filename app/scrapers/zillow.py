"""
Zillow scraper — uses Playwright to bypass 403 bot protection.
"""
import re
import json
import logging
from typing import List, Optional

from .base import BaseScraper, ListingData

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.zillow.com/san-francisco-ca/rentals/"
    "?searchQueryState=%7B%22filterState%22%3A%7B"
    "%22price%22%3A%7B%22max%22%3A3500%7D%2C"
    "%22beds%22%3A%7B%22max%22%3A1%7D%2C"
    "%22sqft%22%3A%7B%22min%22%3A500%7D%2C"
    "%22rentHomes%22%3A%7B%22value%22%3Atrue%7D%7D%7D"
)


class ZillowScraper(BaseScraper):
    def scrape(self) -> List[ListingData]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright not installed")
            return []

        listings = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
                locale="en-US",
            )
            page = context.new_page()
            # Block images/fonts to speed up load and reduce fingerprinting
            page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())

            try:
                page.goto(SEARCH_URL, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)

                html = page.content()
                data = self._extract_next_data(html)
                if not data:
                    logger.warning("Zillow: could not find __NEXT_DATA__ in page")
                else:
                    results = self._find_listings(data)
                    logger.info(f"Zillow: found {len(results)} raw results")
                    for item in results:
                        try:
                            listing = self._parse_item(item)
                            if listing:
                                listings.append(listing)
                        except Exception as e:
                            logger.warning(f"Zillow parse error: {e}")

            except Exception as e:
                logger.error(f"Zillow scrape failed: {e}")
            finally:
                browser.close()

        return listings

    def _extract_next_data(self, html: str) -> Optional[dict]:
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html, re.DOTALL
        )
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        return None

    def _find_listings(self, data: dict) -> list:
        try:
            cat1 = data["props"]["pageProps"]["searchPageState"]["cat1"]
            return cat1["searchResults"]["listResults"]
        except (KeyError, TypeError):
            pass
        return self._deep_find(data, "listResults") or []

    def _deep_find(self, obj, key):
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            for v in obj.values():
                r = self._deep_find(v, key)
                if r:
                    return r
        elif isinstance(obj, list):
            for item in obj:
                r = self._deep_find(item, key)
                if r:
                    return r
        return None

    def _parse_item(self, item: dict) -> Optional[ListingData]:
        url = item.get("detailUrl", "")
        if not url.startswith("http"):
            url = "https://www.zillow.com" + url

        external_id = str(item.get("zpid") or item.get("id") or "")
        if not external_id:
            return None

        title = item.get("address") or item.get("streetAddress") or ""

        price = None
        m = re.search(r"\d[\d,]*", str(item.get("price") or item.get("unformattedPrice") or ""))
        if m:
            price = int(m.group().replace(",", ""))

        bedrooms = None
        beds = item.get("beds") or item.get("minBeds")
        if beds is not None:
            bedrooms = "studio" if str(beds) in ("0", "studio") else "1br" if str(beds) == "1" else None

        sqft = None
        area = item.get("area") or item.get("livingArea")
        if area:
            try:
                sqft = int(str(area).replace(",", ""))
            except ValueError:
                pass

        image_url = None
        imgs = item.get("carouselPhotos") or item.get("imgSrc")
        if isinstance(imgs, list) and imgs:
            image_url = imgs[0].get("url") if isinstance(imgs[0], dict) else imgs[0]
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
            neighborhood=item.get("addressCity") or None,
            address=item.get("address") or None,
            image_url=image_url,
        )
