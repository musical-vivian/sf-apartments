import re
import logging
from typing import List, Optional

from .base import BaseScraper, ListingData

logger = logging.getLogger(__name__)

# Amenity slugs are encoded in the URL path on Apartments.com
SEARCH_URL = (
    "https://www.apartments.com/san-francisco-ca/"
    "air-conditioning-washer-dryer-in-unit/"
    "?max-price=3500&min-beds=0&max-beds=1"
)


class ApartmentsComScraper(BaseScraper):
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
            )
            page = context.new_page()

            try:
                page.goto(SEARCH_URL, timeout=60000, wait_until="networkidle")
                page.wait_for_timeout(3000)

                # Apply amenity filters via UI in case URL path didn't encode them
                self._apply_amenity_filters(page)

                # Paginate through results
                while True:
                    cards = page.query_selector_all("article.placard, [class*='placardContainer'] article")
                    for card in cards:
                        try:
                            listing = self._parse_card(card)
                            if listing:
                                listings.append(listing)
                        except Exception as e:
                            logger.warning(f"Apartments.com card parse error: {e}")

                    # Try to go to next page
                    next_btn = page.query_selector("a[data-page='next'], .next-page a, button.next")
                    if not next_btn:
                        break
                    next_btn.click()
                    page.wait_for_timeout(3000)

            except Exception as e:
                logger.error(f"Apartments.com scrape failed: {e}")
            finally:
                browser.close()

        return listings

    def _apply_amenity_filters(self, page):
        """Click AC + in-unit W/D checkboxes in the filter panel if accessible."""
        try:
            # Open the filter/amenities panel
            for selector in [
                "button[data-tid='desktop-filter-amenities']",
                "button:text('Amenities')",
                "button:text('More Filters')",
            ]:
                btn = page.query_selector(selector)
                if btn:
                    btn.click()
                    page.wait_for_timeout(1500)
                    break

            # Check Air Conditioning
            for selector in [
                "label:has-text('Air Conditioning') input",
                "input[value='air-conditioning']",
                "input[id*='airConditioning']",
            ]:
                el = page.query_selector(selector)
                if el and not el.is_checked():
                    el.check()
                    break

            # Check In-unit Washer/Dryer
            for selector in [
                "label:has-text('Washer/Dryer in Unit') input",
                "label:has-text('In-Unit Laundry') input",
                "input[value='washer-dryer-in-unit']",
                "input[id*='washerDryer']",
            ]:
                el = page.query_selector(selector)
                if el and not el.is_checked():
                    el.check()
                    break

            # Apply / close
            for selector in ["button:text('Apply')", "button:text('See Results')", "button:text('Done')"]:
                btn = page.query_selector(selector)
                if btn:
                    btn.click()
                    page.wait_for_timeout(2000)
                    break

        except Exception as e:
            logger.debug(f"Amenity filter UI interaction skipped: {e}")

    def _parse_card(self, card) -> Optional[ListingData]:
        # URL and external ID
        link = card.query_selector("a.property-link, a[href*='apartments.com']")
        if not link:
            return None
        url = link.get_attribute("href") or ""
        if not url.startswith("http"):
            url = "https://www.apartments.com" + url

        # Use URL path as external ID
        external_id = re.sub(r"https?://[^/]+", "", url).strip("/").replace("/", "_") or url[-50:]

        title_el = card.query_selector(".property-title, .js-placardTitle, [class*='propertyName']")
        title = title_el.inner_text().strip() if title_el else url

        price = None
        price_el = card.query_selector(".price-range, .property-pricing, [class*='price']")
        if price_el:
            m = re.search(r"\$\s*(\d[\d,]*)", price_el.inner_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        bedrooms = None
        sqft = None
        info_el = card.query_selector(".property-beds, [class*='bedInfo'], [class*='unitInfo']")
        if info_el:
            info_text = info_el.inner_text().lower()
            if "studio" in info_text:
                bedrooms = "studio"
            elif "1 bed" in info_text or "1bed" in info_text:
                bedrooms = "1br"
            m = re.search(r"(\d{3,4})\s*(?:sq|ft)", info_text)
            if m:
                sqft = int(m.group(1))

        neighborhood = None
        addr_el = card.query_selector(".property-address, [class*='address']")
        if addr_el:
            neighborhood = addr_el.inner_text().strip()

        image_url = None
        img = card.query_selector("img[src*='apartments.com'], img[src*='cloudfront'], img[src*='rezinc']")
        if img:
            image_url = img.get_attribute("src")

        # Amenities (may be shown inline on card)
        amenities_text = ""
        amenities_el = card.query_selector("[class*='amenities'], [class*='tags']")
        if amenities_el:
            amenities_text = amenities_el.inner_text().lower()

        has_ac = "air conditioning" in amenities_text or "a/c" in amenities_text or None
        has_wd = (
            "in-unit laundry" in amenities_text
            or "washer" in amenities_text
            or None
        )

        return ListingData(
            source="apartments.com",
            external_id=external_id,
            title=title,
            url=url,
            price=price,
            bedrooms=bedrooms,
            sqft=sqft,
            has_ac=has_ac if has_ac is not None else None,
            has_washer_dryer=has_wd if has_wd is not None else None,
            neighborhood=neighborhood,
            image_url=image_url,
        )
