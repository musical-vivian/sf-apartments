import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .database import Listing, get_db, init_db
from .scheduler import start_scheduler, run_scrapers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    init_db()
    _scheduler = start_scheduler()
    # Run an initial scrape on startup if DB is empty
    from .database import SessionLocal
    db = SessionLocal()
    count = db.query(Listing).count()
    db.close()
    if count == 0:
        import threading
        threading.Thread(target=run_scrapers, daemon=True).start()
    yield
    if _scheduler:
        _scheduler.shutdown()


app = FastAPI(title="SF Apartments", lifespan=lifespan)


# ─── API routes ──────────────────────────────────────────────────────────────

@app.get("/api/listings")
def get_listings(
    has_ac: Optional[bool] = Query(None),
    has_washer_dryer: Optional[bool] = Query(None),
    source: Optional[str] = Query(None),
    bedrooms: Optional[str] = Query(None),
    max_price: Optional[int] = Query(None),
    sort: str = Query("newest"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(Listing).filter(Listing.is_active == True)

    if has_ac is not None:
        q = q.filter(Listing.has_ac == has_ac)
    if has_washer_dryer is not None:
        q = q.filter(Listing.has_washer_dryer == has_washer_dryer)
    if source:
        q = q.filter(Listing.source == source)
    if bedrooms:
        q = q.filter(Listing.bedrooms == bedrooms)
    if max_price:
        q = q.filter(Listing.price <= max_price)

    if sort == "price_asc":
        q = q.order_by(Listing.price.asc().nullslast())
    elif sort == "price_desc":
        q = q.order_by(Listing.price.desc().nullslast())
    else:
        q = q.order_by(Listing.first_seen.desc())

    total = q.count()
    listings = q.offset(offset).limit(limit).all()

    return {
        "total": total,
        "listings": [_serialize(l) for l in listings],
    }


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(Listing).filter(Listing.is_active == True).count()
    by_source = {}
    for source in ["craigslist", "apartments.com", "zillow", "padmapper"]:
        by_source[source] = (
            db.query(Listing)
            .filter(Listing.source == source, Listing.is_active == True)
            .count()
        )
    return {"total": total, "by_source": by_source}


@app.post("/api/scrape")
def trigger_scrape(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_scrapers)
    return {"status": "scrape started"}


@app.post("/api/alerts/send")
def trigger_alerts(background_tasks: BackgroundTasks):
    from .scheduler import send_daily_alerts
    background_tasks.add_task(send_daily_alerts)
    return {"status": "alerts queued"}


# ─── Static files ─────────────────────────────────────────────────────────────

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _serialize(l: Listing) -> dict:
    return {
        "id": l.id,
        "source": l.source,
        "title": l.title,
        "price": l.price,
        "bedrooms": l.bedrooms,
        "sqft": l.sqft,
        "has_ac": l.has_ac,
        "has_washer_dryer": l.has_washer_dryer,
        "neighborhood": l.neighborhood,
        "address": l.address,
        "url": l.url,
        "image_url": l.image_url,
        "first_seen": l.first_seen.isoformat() if l.first_seen else None,
    }
