"""
Zillow scraper — uses Apify's Zillow Search Scraper actor (maxcopell/zillow-scraper).
Falls back to Playwright if APIFY_TOKEN is not set.
"""
import re
import json
import logging
from typing import List, Optional

from .base import BaseScraper, ListingData, STEALTH_JS, run_apify_actor, detect_neighborhood

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.zillow.com/san-francisco-ca/rentals/"
    "?searchQueryState=%7B%22filterState%22%3A%7B"
    "%22price%22%3A%7B%22max%22%3A3500%7D%2C"
    "%22beds%22%3A%7B%22max%22%3A1%7D%2C"
    "%22sqft%22%3A%7B%22min%22%3A500%7D%2C"
    "%22rentHomes%22%3A%7B%22value%22%3Atrue%7D%7D%7D"
)

APIFY_ACTOR = "X46xKaa20oUA1fRiP"  # maxcopell/zillow-scraper


class ZillowScraper(BaseScraper):
    def scrape(self) -> List[ListingData]:
        items = run_apify_actor(APIFY_ACTOR, {
            "searchUrls": [{"url": SEARCH_URL}],
            "maxItems": 100,
        })
        if items:
            logger.info(f"Zillow (Apify): got {len(items)} items")
            listings = []
            for item in items:
                try:
                    listing = self._parse_item(item)
                    if listing:
                        listings.append(listing)
                except Exception as e:
                    logger.warning(f"Zillow parse error: {e}")
            return listings

        # Fallback: Playwright
        return self._scrape_playwright()

    def _scrape_playwright(self) -> List[ListingData]:
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
            page.add_init_script(STEALTH_JS)
            page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())
            try:
                page.goto(SEARCH_URL, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                html = page.content()
                data = self._extract_next_data(html)
                if data:
                    for item in self._find_listings(data):
                        try:
                            listing = self._parse_item(item)
                            if listing:
                                listings.append(listing)
                        except Exception as e:
                            logger.warning(f"Zillow parse error: {e}")
            except Exception as e:
                logger.error(f"Zillow Playwright scrape failed: {e}")
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
        url = item.get("detailUrl") or item.get("url") or item.get("hdpUrl") or ""
        if not url.startswith("http"):
            url = "https://www.zillow.com" + url
        if not url or "zillow.com" not in url:
            return None

        external_id = str(item.get("zpid") or item.get("id") or "")
        if not external_id:
            m = re.search(r"/(\d+)_zpid", url)
            external_id = m.group(1) if m else ""
        if not external_id:
            return None

        title = item.get("address") or item.get("streetAddress") or ""

        price = None
        for field in ("price", "unformattedPrice", "rentZestimate"):
            val = item.get(field)
            if val:
                m = re.search(r"\d[\d,]*", str(val))
                if m:
                    price = int(m.group().replace(",", ""))
                    break

        bedrooms = None
        beds = item.get("beds") or item.get("minBeds")
        if beds is not None:
            bedrooms = "studio" if str(beds) in ("0", "studio") else "1br" if str(beds) == "1" else None

        sqft = None
        for field in ("area", "livingArea", "lotAreaValue"):
            area = item.get(field)
            if area:
                try:
                    sqft = int(str(area).replace(",", ""))
                    break
                except ValueError:
                    pass

        image_url = None
        imgs = item.get("carouselPhotos") or item.get("imgSrc")
        if isinstance(imgs, list) and imgs:
            image_url = imgs[0].get("url") if isinstance(imgs[0], dict) else imgs[0]
        elif isinstance(imgs, str):
            image_url = imgs

        neighborhood = detect_neighborhood(title) or detect_neighborhood(url)

        return ListingData(
            source="zillow",
            external_id=external_id,
            title=title,
            url=url,
            price=price,
            bedrooms=bedrooms,
            sqft=sqft,
            neighborhood=neighborhood,
            address=title or None,
            image_url=image_url,
        )
