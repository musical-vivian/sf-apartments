"""Entry point for GitHub Actions scraper workflow."""
import logging
from .database import init_db
from .scheduler import run_scrapers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    init_db()
    run_scrapers()
