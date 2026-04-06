import re
import logging
from typing import List, Optional

from .base import BaseScraper, ListingData

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.apartments.com/san-francisco-ca/"
    "?max-price=3500&min-beds=0&max-beds=1"
)


class ApartmentsComScraper(BaseScraper):
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
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            if stealth_sync:
                stealth_sync(page)

            try:
                page.goto(SEARCH_URL, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(6000)

                page_num = 0
                while page_num < 5:  # max 5 pages
                    page_num += 1
                    html = page.content()
                    found = self._parse_html(html)
                    listings.extend(found)
                    logger.info(f"Apartments.com page {page_num}: found {len(found)} listings")

                    # Next page
                    next_btn = page.query_selector(
                        "a[aria-label='Next Page'], a.next, [class*='paging'] a[rel='next']"
                    )
                    if not next_btn:
                        break
                    next_btn.click()
                    page.wait_for_timeout(4000)

            except Exception as e:
                logger.error(f"Apartments.com scrape failed: {e}")
            finally:
                browser.close()

        return listings

    def _parse_html(self, html: str) -> List[ListingData]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        listings = []

        # Apartments.com uses <article> tags for listing cards
        cards = soup.select("article.placard, article[class*='placard'], li[class*='placard']")
        if not cards:
            # Fallback: look for any property cards
            cards = soup.select("[data-listingid], [data-propertyid]")

        logger.info(f"Apartments.com: found {len(cards)} raw cards in HTML")

        for card in cards:
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.warning(f"Apartments.com card parse error: {e}")

        return listings

    def _parse_card(self, card) -> Optional[ListingData]:
        # URL
        link = card.select_one("a.property-link, a[href*='apartments.com']")
        if not link:
            link = card.select_one("a[href]")
        if not link:
            return None
        url = link.get("href", "")
        if not url.startswith("http"):
            url = "https://www.apartments.com" + url
        if "apartments.com" not in url:
            return None

        external_id = re.sub(r"https?://[^/]+", "", url).strip("/").replace("/", "_")[-80:]

        title_el = card.select_one(
            ".property-title, .js-placardTitle, [class*='propertyName'], [class*='property-name']"
        )
        title = title_el.get_text(strip=True) if title_el else url[:60]

        price = None
        price_el = card.select_one(
            ".price-range, .property-pricing, [class*='price'], [class*='rent']"
        )
        if price_el:
            m = re.search(r"\$\s*([\d,]+)", price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        bedrooms = None
        sqft = None
        info_el = card.select_one(
            ".property-beds, [class*='bedInfo'], [class*='unitInfo'], [class*='bed']"
        )
        if info_el:
            info_text = info_el.get_text().lower()
            if "studio" in info_text:
                bedrooms = "studio"
            elif re.search(r"1\s*bed", info_text):
                bedrooms = "1br"
            m = re.search(r"([\d,]+)\s*(?:sq|ft)", info_text)
            if m:
                sqft = int(m.group(1).replace(",", ""))

        neighborhood = None
        addr_el = card.select_one(".property-address, [class*='address']")
        if addr_el:
            neighborhood = addr_el.get_text(strip=True)

        image_url = None
        img = card.select_one("img[src*='http']")
        if img:
            image_url = img.get("src")

        amenities_text = card.get_text().lower()
        has_ac = True if any(kw in amenities_text for kw in ["air conditioning", "a/c"]) else None
        has_wd = True if any(kw in amenities_text for kw in ["in-unit laundry", "washer", "w/d"]) else None

        return ListingData(
            source="apartments.com",
            external_id=external_id,
            title=title,
            url=url,
            price=price,
            bedrooms=bedrooms,
            sqft=sqft,
            has_ac=has_ac,
            has_washer_dryer=has_wd,
            neighborhood=neighborhood,
            image_url=image_url,
        )
