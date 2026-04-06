from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

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
