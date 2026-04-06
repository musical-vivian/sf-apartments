"""
Rentals.com scraper (replaces Apartments.com which uses Cloudflare blocking).
Uses Playwright + inline stealth patches.
"""
import re
import logging
from typing import List, Optional

from .base import BaseScraper, ListingData, STEALTH_JS, detect_neighborhood

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.rentals.com/California/San-Francisco/"
    "?maxRent=3500&maxBeds=1&minSqft=500"
)


class ApartmentsComScraper(BaseScraper):
    """Kept as ApartmentsComScraper for scheduler compatibility; now scrapes Rentals.com."""

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
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            page = context.new_page()
            page.add_init_script(STEALTH_JS)

            try:
                page.goto(SEARCH_URL, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                logger.info(f"Rentals.com page title: {page.title()}")

                for page_num in range(3):
                    html = page.content()
                    found = self._parse_html(html)
                    listings.extend(found)
                    logger.info(f"Rentals.com page {page_num + 1}: found {len(found)} listings")

                    next_btn = page.query_selector(
                        "a[aria-label='Next'], a[aria-label='next page'], "
                        "button[aria-label='Next'], [class*='pagination'] a[rel='next']"
                    )
                    if not next_btn:
                        break
                    next_btn.click()
                    page.wait_for_timeout(4000)

            except Exception as e:
                logger.error(f"Rentals.com scrape failed: {e}")
            finally:
                browser.close()

        return listings

    def _parse_html(self, html: str) -> List[ListingData]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        listings = []

        # Rentals.com uses article or li cards with data attributes
        cards = (
            soup.select("article[data-id], article[data-listing-id]")
            or soup.select("[data-listing-id], [data-property-id]")
            or soup.select("article.rental-card, div.rental-card, li.rental-card")
            or soup.select("[class*='PropertyCard'], [class*='property-card'], [class*='listing-card']")
        )
        logger.info(f"Rentals.com: found {len(cards)} raw cards in HTML")

        for card in cards:
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.warning(f"Rentals.com card parse error: {e}")

        return listings

    def _parse_card(self, card) -> Optional[ListingData]:
        link = card.select_one("a[href*='rentals.com']") or card.select_one("a[href]")
        if not link:
            return None
        url = link.get("href", "")
        if not url.startswith("http"):
            url = "https://www.rentals.com" + url
        if "rentals.com" not in url:
            return None

        external_id = (
            card.get("data-id")
            or card.get("data-listing-id")
            or card.get("data-property-id")
            or re.sub(r"[^a-z0-9_-]", "_", url.replace("https://www.rentals.com", "").strip("/"))[-80:]
        )
        if not external_id:
            return None

        card_text = card.get_text(" ", strip=True)
        tl = card_text.lower()

        price = None
        m = re.search(r"\$\s*([\d,]+)", card_text)
        if m:
            price = int(m.group(1).replace(",", ""))

        bedrooms = None
        if "studio" in tl:
            bedrooms = "studio"
        elif re.search(r"1\s*(?:bed|br)\b", tl):
            bedrooms = "1br"

        sqft = None
        m = re.search(r"([\d,]+)\s*(?:sq\.?\s*ft|sqft|ft²)", card_text, re.IGNORECASE)
        if m:
            try:
                sqft = int(m.group(1).replace(",", ""))
            except ValueError:
                pass

        title_el = card.select_one("[class*='address'], [class*='title'], [class*='name'], h2, h3")
        title = title_el.get_text(strip=True) if title_el else url[:60]
        neighborhood = detect_neighborhood(card_text) or detect_neighborhood(url)

        image_url = None
        img = card.select_one("img[src*='http']")
        if img:
            image_url = img.get("src")

        has_ac = True if any(kw in tl for kw in ["air conditioning", "a/c"]) else None
        has_wd = True if any(kw in tl for kw in ["washer", "laundry", "w/d"]) else None

        return ListingData(
            source="rentals.com",
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
