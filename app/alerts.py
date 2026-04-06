import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

from .database import Listing

logger = logging.getLogger(__name__)

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "musicalvivian@gmail.com")
ALERT_PHONE = os.getenv("ALERT_PHONE", "7326683269")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
APP_URL = os.getenv("APP_URL", "http://localhost:8000")


def _listing_row_html(listing: Listing) -> str:
    ac_badge = (
        '<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:4px;font-size:12px;margin-right:4px">AC</span>'
        if listing.has_ac
        else ""
    )
    wd_badge = (
        '<span style="background:#dbeafe;color:#1e40af;padding:2px 8px;border-radius:4px;font-size:12px;margin-right:4px">W/D</span>'
        if listing.has_washer_dryer
        else ""
    )
    sqft_str = f" · {listing.sqft} sqft" if listing.sqft else ""
    beds_str = listing.bedrooms or "?"
    price_str = f"${listing.price:,}" if listing.price else "?"
    neighborhood = listing.neighborhood or ""

    img_tag = (
        f'<img src="{listing.image_url}" style="width:100%;height:160px;object-fit:cover;border-radius:6px 6px 0 0;" />'
        if listing.image_url
        else ""
    )

    return f"""
    <div style="border:1px solid #e5e7eb;border-radius:8px;margin-bottom:16px;overflow:hidden;max-width:360px;display:inline-block;vertical-align:top;margin-right:16px;">
      {img_tag}
      <div style="padding:12px;">
        <div style="font-size:18px;font-weight:700;color:#111827;">{price_str}/mo</div>
        <div style="color:#6b7280;font-size:13px;margin-top:2px;">{beds_str}{sqft_str}</div>
        <div style="color:#6b7280;font-size:13px;">{neighborhood}</div>
        <div style="margin-top:8px;">{ac_badge}{wd_badge}</div>
        <div style="margin-top:8px;">
          <span style="background:#f3f4f6;color:#374151;padding:2px 6px;border-radius:4px;font-size:11px;">{listing.source}</span>
        </div>
        <a href="{listing.url}" style="display:block;margin-top:10px;text-align:center;background:#4f46e5;color:#fff;padding:8px;border-radius:6px;text-decoration:none;font-size:13px;">View Listing →</a>
      </div>
    </div>
    """


def send_daily_email(new_listings: List[Listing]) -> bool:
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        logger.warning("Gmail credentials not configured — skipping email alert")
        return False

    count = len(new_listings)
    subject = f"SF Apartments: {count} new listing{'s' if count != 1 else ''} today"

    cards_html = "".join(_listing_row_html(l) for l in new_listings)

    html_body = f"""
    <html><body style="font-family:sans-serif;max-width:800px;margin:0 auto;padding:20px;">
      <h2 style="color:#111827;">🏠 {count} New SF Apartment{'s' if count != 1 else ''} Today</h2>
      <p style="color:#6b7280;">Studio &amp; 1BR · Up to $3,500 · Min 500 sqft</p>
      <div style="margin-top:20px;">
        {cards_html}
      </div>
      <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;">
        <a href="{APP_URL}" style="color:#4f46e5;">Browse all listings →</a>
      </div>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = ALERT_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, ALERT_EMAIL, msg.as_string())
        logger.info(f"Email alert sent: {count} new listings")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def send_sms(new_listings: List[Listing]) -> bool:
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER]):
        logger.warning("Twilio credentials not configured — skipping SMS alert")
        return False

    count = len(new_listings)
    lines = [f"🏠 SF Apartments: {count} new listing{'s' if count != 1 else ''} today"]
    for l in new_listings[:5]:
        price_str = f"${l.price:,}" if l.price else "?"
        beds_str = l.bedrooms or "?"
        sqft_str = f", {l.sqft}sqft" if l.sqft else ""
        nbhd = f" - {l.neighborhood}" if l.neighborhood else ""
        badges = []
        if l.has_ac:
            badges.append("AC")
        if l.has_washer_dryer:
            badges.append("W/D")
        badge_str = f" ({', '.join(badges)})" if badges else ""
        lines.append(f"• {price_str} {beds_str}{sqft_str}{nbhd}{badge_str}")

    if count > 5:
        lines.append(f"...and {count - 5} more")
    lines.append(f"Browse: {APP_URL}")

    message = "\n".join(lines)

    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=TWILIO_FROM_NUMBER,
            to=f"+1{ALERT_PHONE}",
        )
        logger.info("SMS alert sent")
        return True
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        return False
