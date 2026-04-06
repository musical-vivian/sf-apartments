import re
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
    "Accept": "application/json",
    "Referer": "https://www.padmapper.com/",
}

# SF bounding box
SF_BOUNDS = {
    "lat_min": 37.708,
    "lat_max": 37.833,
    "long_min": -122.517,
    "long_max": -122.357,
}

API_URL = (
    "https://www.padmapper.com/api/t/1/listings"
    "?min_price=500&max_price=3500"
    "&min_beds=0&max_beds=1"
    f"&lat_min={SF_BOUNDS['lat_min']}"
    f"&lat_max={SF_BOUNDS['lat_max']}"
    f"&long_min={SF_BOUNDS['long_min']}"
    f"&long_max={SF_BOUNDS['long_max']}"
    "&min_sqft=500"
    "&amenities[]=air_conditioning"   # AC filter
    "&amenities[]=in_unit_laundry"    # in-unit W/D filter
)


class PadmapperScraper(BaseScraper):
    def scrape(self) -> List[ListingData]:
        listings = []
        try:
            resp = requests.get(API_URL, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            items = data if isinstance(data, list) else data.get("listings", data.get("results", []))
            for item in items:
                try:
                    listing = self._parse_item(item)
                    if listing:
                        listings.append(listing)
                except Exception as e:
                    logger.warning(f"Padmapper parse error: {e}")

        except Exception as e:
            logger.error(f"Padmapper scrape failed: {e}")

        return listings

    def _parse_item(self, item: dict) -> Optional[ListingData]:
        external_id = str(item.get("id") or item.get("listing_id") or "")
        if not external_id:
            return None

        url = item.get("url") or item.get("permalink") or f"https://www.padmapper.com/apartments/{external_id}"

        title = item.get("title") or item.get("address") or ""

        price = None
        p = item.get("price") or item.get("min_price")
        if p:
            m = re.search(r"\d[\d,]*", str(p))
            if m:
                price = int(m.group().replace(",", ""))

        bedrooms = None
        beds = item.get("bedrooms") or item.get("min_bedrooms")
        if beds is not None:
            if int(beds) == 0:
                bedrooms = "studio"
            elif int(beds) == 1:
                bedrooms = "1br"

        sqft = None
        area = item.get("sqft") or item.get("square_feet")
        if area:
            try:
                sqft = int(str(area).replace(",", ""))
            except ValueError:
                pass

        amenities = (item.get("amenities") or [])
        if isinstance(amenities, list):
            amenities_text = " ".join(str(a).lower() for a in amenities)
        else:
            amenities_text = str(amenities).lower()

        has_ac = "air conditioning" in amenities_text or "a/c" in amenities_text or None
        has_wd = "washer" in amenities_text or "laundry" in amenities_text or None

        neighborhood = item.get("neighborhood") or item.get("city")
        address = item.get("address") or item.get("street_address")

        image_url = None
        photos = item.get("photos") or item.get("images") or []
        if photos and isinstance(photos, list):
            first = photos[0]
            image_url = first.get("url") or first if isinstance(first, str) else None

        return ListingData(
            source="padmapper",
            external_id=external_id,
            title=title,
            url=url,
            price=price,
            bedrooms=bedrooms,
            sqft=sqft,
            has_ac=has_ac if has_ac else None,
            has_washer_dryer=has_wd if has_wd else None,
            neighborhood=neighborhood,
            address=address,
            image_url=image_url,
        )
