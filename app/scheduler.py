import logging
from datetime import datetime, timezone

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.exc import IntegrityError

from .database import Listing, SessionLocal
from .scrapers.craigslist import CraigslistScraper
from .scrapers.apartments_com import ApartmentsComScraper
from .scrapers.zillow import ZillowScraper
from .scrapers.padmapper import PadmapperScraper

logger = logging.getLogger(__name__)

PT = pytz.timezone("America/Los_Angeles")


def run_scrapers():
    """Run all scrapers and save new listings to the database."""
    logger.info("Starting scrape run...")
    scrapers = [
        CraigslistScraper(),
        ApartmentsComScraper(),
        ZillowScraper(),
        PadmapperScraper(),
    ]

    db = SessionLocal()
    new_count = 0
    try:
        for scraper in scrapers:
            name = scraper.__class__.__name__
            try:
                listings = scraper.scrape()
                logger.info(f"{name}: fetched {len(listings)} listings")
                for data in listings:
                    existing = (
                        db.query(Listing)
                        .filter_by(source=data.source, external_id=data.external_id)
                        .first()
                    )
                    if existing:
                        existing.last_seen = datetime.utcnow()
                        existing.is_active = True
                    else:
                        listing = Listing(
                            source=data.source,
                            external_id=data.external_id,
                            title=data.title,
                            price=data.price,
                            bedrooms=data.bedrooms,
                            sqft=data.sqft,
                            has_ac=data.has_ac,
                            has_washer_dryer=data.has_washer_dryer,
                            neighborhood=data.neighborhood,
                            address=data.address,
                            url=data.url,
                            image_url=data.image_url,
                            description=data.description,
                        )
                        db.add(listing)
                        new_count += 1
                db.commit()
            except IntegrityError:
                db.rollback()
            except Exception as e:
                logger.error(f"{name} failed: {e}")
                db.rollback()
    finally:
        db.close()

    logger.info(f"Scrape complete. {new_count} new listings added.")
    return new_count


def send_daily_alerts():
    """Send email + SMS with listings added in the last 24 hours that haven't been alerted."""
    from .alerts import send_daily_email, send_sms

    db = SessionLocal()
    try:
        new_listings = (
            db.query(Listing)
            .filter(Listing.alerted == False, Listing.is_active == True)
            .order_by(Listing.first_seen.desc())
            .all()
        )

        if not new_listings:
            logger.info("No new listings to alert on")
            return

        logger.info(f"Sending alerts for {len(new_listings)} new listings")
        send_daily_email(new_listings)
        send_sms(new_listings)

        for listing in new_listings:
            listing.alerted = True
        db.commit()
    finally:
        db.close()


def start_scheduler():
    scheduler = BackgroundScheduler(timezone=PT)

    # Scrape every 4 hours
    scheduler.add_job(
        run_scrapers,
        trigger=CronTrigger(hour="0,4,8,12,16,20", minute=0, timezone=PT),
        id="scrape",
        replace_existing=True,
    )

    # Send daily digest at 8am PT
    scheduler.add_job(
        send_daily_alerts,
        trigger=CronTrigger(hour=8, minute=5, timezone=PT),
        id="alerts",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started")
    return scheduler
