import os
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
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


# ─── Chat ─────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]


def _format_listings_for_chat(listings) -> str:
    lines = []
    for l in listings:
        price = f"${l.price:,}/mo" if l.price else "price unknown"
        beds = l.bedrooms or "?"
        sqft = f"{l.sqft}sqft" if l.sqft else ""
        nbhd = l.neighborhood or l.address or ""
        amenities = " | ".join(filter(None, [
            "AC" if l.has_ac else None,
            "W/D" if l.has_washer_dryer else None,
        ]))
        parts = " | ".join(filter(None, [price, beds, sqft, nbhd, amenities, l.source, l.url]))
        lines.append(f"- {parts}")
    return "\n".join(lines)


@app.post("/api/chat")
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return JSONResponse({"error": "OPENROUTER_API_KEY not configured"}, status_code=500)

    listings = (
        db.query(Listing)
        .filter(Listing.is_active == True)
        .order_by(Listing.first_seen.desc())
        .limit(200)
        .all()
    )
    context = _format_listings_for_chat(listings)

    system_prompt = f"""You are a helpful SF apartment hunting assistant. \
You have real-time access to {len(listings)} current listings scraped from \
Craigslist, Apartments.com, Zillow, and Padmapper — all studio or 1BR in San Francisco, \
up to $3,500/mo, min 500 sqft, with AC and in-unit W/D.

Current listings:
{context}

Help the user find apartments, answer questions, compare listings, and make recommendations. \
When mentioning a specific listing always include its price, neighborhood, and URL."""

    messages_payload = [{"role": m.role, "content": m.content} for m in request.messages]

    async def generate():
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )
            model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
            logger.info(f"Chat: using model {model}")
            stream = client.chat.completions.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "system", "content": system_prompt}, *messages_payload],
                stream=True,
            )
            for chunk in stream:
                text = chunk.choices[0].delta.content
                if text:
                    yield f"data: {json.dumps({'text': text})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Chat error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


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
