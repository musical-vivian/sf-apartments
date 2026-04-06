import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

# Known SF neighborhoods for fallback detection
SF_NEIGHBORHOODS = [
    "Mission", "Castro", "SoMa", "SOMA", "Pacific Heights", "Noe Valley",
    "Haight", "Richmond", "Sunset", "Marina", "North Beach", "Tenderloin",
    "NOPA", "Potrero Hill", "Dogpatch", "Bernal Heights", "Glen Park",
    "Excelsior", "Inner Sunset", "Outer Sunset", "Inner Richmond", "Outer Richmond",
    "Russian Hill", "Nob Hill", "Hayes Valley", "Lower Haight", "Western Addition",
    "Japantown", "Chinatown", "Financial District", "Downtown", "Fillmore",
    "Duboce Triangle", "Cole Valley", "Twin Peaks", "West Portal", "Parkside",
    "Lakeshore", "Ingleside", "Visitacion Valley", "Bayview", "Hunters Point",
    "Portola", "Crocker Amazon", "Oceanview", "Merced Heights", "Forest Hill",
    "Eureka Valley", "Dolores Heights", "Alamo Square", "Lower Pacific Heights",
]
_NEIGHBORHOOD_PATTERN = re.compile(
    "|".join(re.escape(n) for n in SF_NEIGHBORHOODS), re.IGNORECASE
)


def detect_neighborhood(text: str) -> str | None:
    """Scan text for a known SF neighborhood name."""
    if not text:
        return None
    m = _NEIGHBORHOOD_PATTERN.search(text)
    if m:
        # Return the canonical casing from our list
        matched = m.group(0).lower()
        for n in SF_NEIGHBORHOODS:
            if n.lower() == matched:
                return n
        return m.group(0)
    return None

# Inline stealth patches — no external package needed.
# Hides Playwright automation signals that trigger bot detection.
STEALTH_JS = """
() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', {
        get: () => { const arr = [1,2,3,4,5]; arr.item = i => arr[i]; return arr; }
    });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    Object.defineProperty(navigator, 'platform', { get: () => 'MacIntel' });
    window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {}, app: {} };
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (p) =>
        p.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : origQuery(p);
}
"""


@dataclass
class ListingData:
    source: str
    external_id: str
    title: str
    url: str
    price: Optional[int] = None
    bedrooms: Optional[str] = None   # "studio" or "1br"
    sqft: Optional[int] = None
    has_ac: Optional[bool] = None
    has_washer_dryer: Optional[bool] = None
    neighborhood: Optional[str] = None
    address: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None


class BaseScraper(ABC):
    @abstractmethod
    def scrape(self) -> List[ListingData]:
        pass
