"""
Craigslist scraper — uses Playwright + stealth to bypass bot blocking.
Plain HTTP requests get 403 from Railway IPs; browser rendering avoids this.
"""
import re
import logging
from typing import List, Optional

from .base import BaseScraper, ListingData

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://sfbay.craigslist.org/search/sfc/apa"
    "?max_price=3500"
    "&min_bedrooms=0&max_bedrooms=1"
    "&min_sqft=500"
    "&laundry=1"
    "&availabilityMode=0"
    "&hasPic=1"
)


class CraigslistScraper(BaseScraper):
    def scrape(self) -> List[ListingData]:
        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import stealth_sync
        except ImportError as e:
            logger.error(f"Missing dependency: {e}")
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
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            page = context.new_page()
            stealth_sync(page)
            page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())

            try:
                page.goto(SEARCH_URL, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # Paginate up to 3 pages
                for page_num in range(3):
                    html = page.content()
                    found = self._parse_html(html)
                    listings.extend(found)
                    logger.info(f"Craigslist page {page_num + 1}: found {len(found)} listings")

                    # Try next page button
                    next_btn = page.query_selector("a[aria-label='next'], button[aria-label='next'], .cl-page-number ~ a")
                    if not next_btn:
                        break
                    next_btn.click()
                    page.wait_for_timeout(3000)

            except Exception as e:
                logger.error(f"Craigslist scrape failed: {e}")
            finally:
                browser.close()

        return listings

    def _parse_html(self, html: str) -> List[ListingData]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        listings = []

        # CL uses li.cl-static-search-result (2024+ layout)
        cards = soup.select("li.cl-static-search-result, li.cl-search-result")
        if not cards:
            # Older layout fallback
            cards = soup.select(".result-row")

        logger.info(f"Craigslist: found {len(cards)} raw cards in HTML")

        for card in cards:
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.warning(f"CL card parse error: {e}")

        return listings

    def _parse_card(self, card) -> Optional[ListingData]:
        # URL
        link = card.select_one("a[href*='craigslist.org']") or card.select_one("a[href]")
        if not link:
            return None
        url = link.get("href", "")
        if not url.startswith("http"):
            url = "https://sfbay.craigslist.org" + url

        match = re.search(r"/(\d{10,})\.html", url)
        if not match:
            return None
        external_id = match.group(1)

        # Title
        title_el = (
            card.select_one(".posting-title .label")
            or card.select_one(".title")
            or card.select_one("a")
        )
        raw_title = title_el.get_text(strip=True) if title_el else url[:60]

        # Price
        price = None
        price_el = card.select_one(".priceinfo, .price, [class*='price']")
        price_text = price_el.get_text() if price_el else raw_title
        m = re.search(r"\$\s*([\d,]+)", price_text)
        if m:
            price = int(m.group(1).replace(",", ""))

        # Beds + sqft from housing span
        bedrooms = None
        sqft = None
        housing_el = card.select_one(".housing, [class*='housing'], [class*='meta']")
        housing_text = (housing_el.get_text() if housing_el else raw_title).lower()

        if "studio" in housing_text or "studio" in raw_title.lower():
            bedrooms = "studio"
        elif re.search(r"1\s*br\b", housing_text) or re.search(r"1\s*br\b", raw_title.lower()):
            bedrooms = "1br"

        m = re.search(r"(\d{3,4})\s*ft", housing_text, re.IGNORECASE)
        if m:
            sqft = int(m.group(1))

        # Neighborhood from title (text in parens)
        neighborhood = None
        m = re.search(r"\(([^)]+)\)", raw_title)
        if m:
            neighborhood = m.group(1).strip()

        # Image
        image_url = None
        img = card.select_one("img[src]")
        if img:
            image_url = img.get("src")

        return ListingData(
            source="craigslist",
            external_id=external_id,
            title=raw_title,
            url=url,
            price=price,
            bedrooms=bedrooms,
            sqft=sqft,
            has_washer_dryer=True,   # guaranteed by laundry=1 filter
            has_ac=None,
            neighborhood=neighborhood,
            image_url=image_url,
        )
