"""
scheduler.py — background tee time checker
Runs every 5 minutes, logs into each member's Ibis account,
scrapes available tee times, and sends SMS alerts via Twilio.
"""

import os
import json
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from playwright.sync_api import sync_playwright
from twilio.rest import Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

TWILIO_SID    = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM   = os.environ.get("TWILIO_FROM_NUMBER", "")

TEE_TIME_URL  = "https://www.clubatibis.com/Club/Scripts/Sports/Golf/GolfTeeTimes.asp"
LOGIN_URL     = "https://www.clubatibis.com/Club/Scripts/Members/MemberLogin.asp"


def send_sms(to: str, body: str):
    try:
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(body=body, from_=TWILIO_FROM, to=to)
        logging.info("SMS sent to %s", to)
    except Exception as e:
        logging.error("SMS failed to %s: %s", to, e)


def scrape_tee_times_for_member(ibis_email: str, ibis_password: str) -> list[dict]:
    """
    Log into The Club at Ibis as this member and return available tee times.
    Returns list of dicts: [{"date": "2026-03-29", "time": "7:30 AM", "players_available": 4}, ...]
    """
    tee_times = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Log in
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
            page.wait_for_timeout(1000)

            # Fill in credentials — field names may need adjusting after testing
            page.fill('input[name="MemberID"], input[type="email"], input[name="Email"]', ibis_email)
            page.fill('input[name="Password"], input[type="password"]', ibis_password)
            page.click('input[type="submit"], button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=15_000)

            # Navigate to tee times
            page.goto(TEE_TIME_URL, wait_until="networkidle", timeout=30_000)
            page.wait_for_timeout(2000)

            page_text = page.inner_text("body")
            browser.close()

        # Use simple text parsing to find times — Claude's API not needed here
        # Common patterns: "7:30 AM", "08:00", "9:00 AM" near date strings
        import re
        time_pattern = re.compile(r'\b(\d{1,2}:\d{2}\s*(?:AM|PM)?)\b', re.IGNORECASE)
        date_pattern = re.compile(r'\b(\d{4}-\d{2}-\d{2}|\w+ \d{1,2},? \d{4})\b')

        current_date = None
        lines = page_text.split('\n')

        for line in lines:
            date_match = date_pattern.search(line)
            if date_match:
                try:
                    raw = date_match.group(1)
                    # Try to normalise to YYYY-MM-DD
                    for fmt in ("%Y-%m-%d", "%B %d %Y", "%B %d, %Y"):
                        try:
                            current_date = datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

            time_matches = time_pattern.findall(line)
            for t in time_matches:
                t = t.strip()
                # Try to extract player count from the same line
                players_match = re.search(r'(\d)\s*(?:player|spot|open)', line, re.IGNORECASE)
                players = int(players_match.group(1)) if players_match else None

                tee_times.append({
                    "date": current_date or datetime.today().strftime("%Y-%m-%d"),
                    "time": t,
                    "players_available": players,
                })

    except Exception as e:
        logging.error("Scrape failed for %s: %s", ibis_email, e)

    return tee_times


def matches_preferences(slot: dict, member) -> bool:
    """Check if a tee time slot matches this member's preferences."""
    date = slot.get("date", "")
    time_str = slot.get("time", "")
    players = slot.get("players_available")

    # Date filter
    wanted_dates = member.get_dates_list()
    if wanted_dates and date not in wanted_dates:
        return False

    # Player filter
    if players is not None and players < member.min_players:
        return False

    # Time filter — convert to comparable format
    try:
        slot_time = datetime.strptime(time_str.upper().replace(" ", ""), "%I:%M%p").strftime("%H:%M")
    except ValueError:
        try:
            slot_time = datetime.strptime(time_str, "%H:%M").strftime("%H:%M")
        except ValueError:
            slot_time = time_str

    if slot_time < member.earliest_time or slot_time > member.latest_time:
        return False

    return True


def check_all_members(app):
    """Main job — runs every 5 minutes."""
    with app.app_context():
        from models import db, Member

        members = Member.query.filter_by(active=True).all()
        logging.info("Checking tee times for %d active member(s)...", len(members))

        for member in members:
            try:
                tee_times = scrape_tee_times_for_member(member.ibis_email, member.ibis_password)
                logging.info("  %s → %d slot(s) found", member.ibis_email, len(tee_times))

                alerted = member.get_alerted_set()
                new_slots = []

                for slot in tee_times:
                    key = f"{slot['date']}|{slot['time']}"
                    if key not in alerted and matches_preferences(slot, member):
                        new_slots.append(slot)

                for slot in new_slots:
                    date = slot.get("date", "")
                    time_str = slot.get("time", "")
                    players = slot.get("players_available")
                    players_str = f" ({players} spots open)" if players else ""

                    msg = (
                        f"Tee time alert!\n"
                        f"{date} at {time_str}{players_str}\n"
                        f"Book now: {TEE_TIME_URL}"
                    )
                    send_sms(member.phone, msg)
                    member.add_alerted(f"{date}|{time_str}")

                db.session.commit()

            except Exception as e:
                logging.error("Error processing member %s: %s", member.ibis_email, e)


def start_scheduler(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=check_all_members,
        args=[app],
        trigger="interval",
        minutes=5,
        id="tee_time_check",
        replace_existing=True,
    )
    scheduler.start()
    logging.info("Scheduler started — checking every 5 minutes.")
