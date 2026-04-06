"""
Padmapper scraper — uses Playwright + stealth to scrape search results.
Their /api/t/1/listings endpoint returns 405; scraping HTML instead.
"""
import re
import logging
from typing import List, Optional

from .base import BaseScraper, ListingData

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.padmapper.com/apartments/san-francisco-ca"
    "?type=apartment"
    "&min-price=500&max-price=3500"
    "&min-beds=0&max-beds=1"
)


class PadmapperScraper(BaseScraper):
    def scrape(self) -> List[ListingData]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright not installed")
            return []

        try:
            from playwright_stealth import stealth_sync
        except ImportError:
            stealth_sync = None

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
            if stealth_sync:
                stealth_sync(page)
            page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())

            try:
                page.goto(SEARCH_URL, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(6000)

                html = page.content()
                found = self._parse_html(html)
                logger.info(f"Padmapper: found {len(found)} listings")
                listings.extend(found)

            except Exception as e:
                logger.error(f"Padmapper scrape failed: {e}")
            finally:
                browser.close()

        return listings

    def _parse_html(self, html: str) -> List[ListingData]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        listings = []

        # Padmapper uses list items with data attributes or specific class patterns
        cards = (
            soup.select("[class*='ListItem'], [class*='list-item'], [class*='listing-item']")
            or soup.select("[data-id], [data-listing-id]")
            or soup.select("li[class*='item']")
        )

        logger.info(f"Padmapper: found {len(cards)} raw cards in HTML")

        for card in cards:
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.warning(f"Padmapper card parse error: {e}")

        return listings

    def _parse_card(self, card) -> Optional[ListingData]:
        link = card.select_one("a[href*='padmapper.com'], a[href*='/apartments/']")
        if not link:
            link = card.select_one("a[href]")
        if not link:
            return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = "https://www.padmapper.com" + url
        if "padmapper.com" not in url:
            return None

        # external_id from URL or data attr
        external_id = (
            card.get("data-id")
            or card.get("data-listing-id")
            or re.sub(r"[^a-z0-9_-]", "_", url.replace("https://www.padmapper.com", "").strip("/"))[-80:]
        )
        if not external_id:
            return None

        card_text = card.get_text(" ", strip=True)

        # Price
        price = None
        m = re.search(r"\$\s*([\d,]+)", card_text)
        if m:
            price = int(m.group(1).replace(",", ""))

        # Bedrooms
        bedrooms = None
        tl = card_text.lower()
        if "studio" in tl:
            bedrooms = "studio"
        elif re.search(r"1\s*(?:bed|br)\b", tl):
            bedrooms = "1br"

        # Sqft
        sqft = None
        m = re.search(r"([\d,]+)\s*(?:sq\.?\s*ft|sqft|ft²)", card_text, re.IGNORECASE)
        if m:
            try:
                sqft = int(m.group(1).replace(",", ""))
            except ValueError:
                pass

        # Title / address
        title_el = card.select_one("[class*='address'], [class*='title'], [class*='name']")
        title = title_el.get_text(strip=True) if title_el else url[:60]

        # Image
        image_url = None
        img = card.select_one("img[src*='http']")
        if img:
            image_url = img.get("src")

        # Amenities
        has_ac = True if any(kw in tl for kw in ["air conditioning", "a/c"]) else None
        has_wd = True if any(kw in tl for kw in ["washer", "laundry", "w/d"]) else None

        return ListingData(
            source="padmapper",
            external_id=external_id,
            title=title,
            url=url,
            price=price,
            bedrooms=bedrooms,
            sqft=sqft,
            has_ac=has_ac,
            has_washer_dryer=has_wd,
            neighborhood=None,
            image_url=image_url,
        )
