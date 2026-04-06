from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


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
