"""
Apartments.com scraper — uses Apify's Advanced Apartments.com Scraper actor.
Falls back to Rentals.com via Playwright if APIFY_TOKEN is not set.
"""
import re
import logging
from typing import List, Optional

from .base import BaseScraper, ListingData, STEALTH_JS, detect_neighborhood, run_apify_actor

logger = logging.getLogger(__name__)

APIFY_ACTOR = "BvepfniODI2AixuNN"  # saswave/advanced-apartments-com-scraper
SEARCH_URL_APIFY = "https://www.apartments.com/san-francisco-ca/?min-sqft=500&max-price=3500&max-beds=1"

RENTALS_URL = (
    "https://www.rentals.com/California/San-Francisco/"
    "?maxRent=3500&maxBeds=1&minSqft=500"
)


class ApartmentsComScraper(BaseScraper):
    def scrape(self) -> List[ListingData]:
        items = run_apify_actor(APIFY_ACTOR, {
            "startUrls": [{"url": SEARCH_URL_APIFY}],
            "maxItems": 100,
        })
        if items:
            logger.info(f"Apartments.com (Apify): got {len(items)} items")
            listings = []
            for item in items:
                try:
                    listing = self._parse_apify_item(item)
                    if listing:
                        listings.append(listing)
                except Exception as e:
                    logger.warning(f"Apartments.com parse error: {e}")
            return listings

        # Fallback: Rentals.com via Playwright
        return self._scrape_rentals_playwright()

    def _parse_apify_item(self, item: dict) -> Optional[ListingData]:
        url = item.get("url") or item.get("detailUrl") or ""
        if not url or "apartments.com" not in url:
            return None

        external_id = item.get("id") or item.get("propertyId") or re.sub(
            r"[^a-z0-9_-]", "_", url.replace("https://www.apartments.com", "").strip("/")
        )[-80:]
        if not external_id:
            return None

        title = item.get("name") or item.get("address") or item.get("propertyName") or url[:60]

        price = None
        for field in ("minRent", "price", "rent"):
            val = item.get(field)
            if val:
                m = re.search(r"\d[\d,]*", str(val))
                if m:
                    price = int(m.group().replace(",", ""))
                    break

        bedrooms = None
        beds = item.get("beds") or item.get("minBeds") or item.get("bedrooms")
        if beds is not None:
            s = str(beds).lower()
            if s in ("0", "studio"):
                bedrooms = "studio"
            elif s == "1":
                bedrooms = "1br"

        sqft = None
        for field in ("sqft", "minSqft", "area", "livingArea"):
            val = item.get(field)
            if val:
                try:
                    sqft = int(str(val).replace(",", ""))
                    break
                except ValueError:
                    pass

        image_url = item.get("photos", [None])[0] if item.get("photos") else item.get("imgSrc")
        if isinstance(image_url, dict):
            image_url = image_url.get("url")

        neighborhood = detect_neighborhood(title) or detect_neighborhood(url)

        has_ac = True if item.get("hasAC") or "air conditioning" in str(item).lower() else None
        has_wd = True if item.get("hasWasherDryer") or "washer" in str(item).lower() else None

        return ListingData(
            source="apartments.com",
            external_id=str(external_id),
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

    def _scrape_rentals_playwright(self) -> List[ListingData]:
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
                page.goto(RENTALS_URL, timeout=60000, wait_until="domcontentloaded")
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
        cards = (
            soup.select("article[data-id], article[data-listing-id]")
            or soup.select("[data-listing-id], [data-property-id]")
            or soup.select("article.rental-card, div.rental-card, li.rental-card")
            or soup.select("[class*='PropertyCard'], [class*='property-card'], [class*='listing-card']")
        )
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
            card.get("data-id") or card.get("data-listing-id") or card.get("data-property-id")
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
