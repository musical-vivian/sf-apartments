"""Entry point for GitHub Actions daily alerts workflow."""
import logging
from .database import init_db
from .scheduler import send_daily_alerts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    init_db()
    send_daily_alerts()
