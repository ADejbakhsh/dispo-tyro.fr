"""
Axess Shop API client for Colmiane (https://colmiane.axess.shop)

Fetches reservation data for the TYROLIENNE (zip line) activity:
  - Daily calendar summary (available/max slots per day)
  - Per-time-slot availability (30-min slots, 10:00-16:00, 16 places each)

API endpoints discovered:
  1. POST /api/TicketsV4TimeSlotApi/GetReservationTimeSlotsForCalendar
     - Returns monthly calendar overview with daily aggregates
  2. POST /fr/Products/Tickets/Contingent/{ProjNr}/{PoolNr}/{TicketTypeId}
     - Form submission returning HTML with per-slot time data

URL pattern:
  https://colmiane.axess.shop/fr/Products/Tickets/Calendar/{ProjNr}/{PoolNr}/{TicketTypeId}
  └── base_url ──┘└────────── calendar_path ────────────┘└─proj─┘└─pool─┘└─ticket─┘

The Contingent (time-slot) page mirrors the Calendar URL:
  /fr/Products/Tickets/Contingent/{ProjNr}/{PoolNr}/{TicketTypeId}
"""

import re
import json
from datetime import datetime, date, timedelta
from typing import Optional
from urllib.parse import urlparse

import requests

# ── URL pattern constants ──────────────────────────────────────────────
# The Calendar URL follows the pattern:
#   {base_url}/fr/Products/Tickets/Calendar/{proj_nr}/{pool_nr}/{ticket_type_id}
#
# From this we derive:
#   Contingent URL:  {base_url}/fr/Products/Tickets/Contingent/{proj_nr}/{pool_nr}/{ticket_type_id}
#   Calendar API:    {base_url}/api/TicketsV4TimeSlotApi/GetReservationTimeSlotsForCalendar
#
# Regex to parse the numeric segments from a Calendar or Contingent URL.
_CALENDAR_PATH_RE = re.compile(
    r"/(fr/Products/Tickets)/(Calendar|Contingent)/(\d+)/(\d+)/(\d+)"
)


def parse_calendar_url(url: str) -> dict:
    """Parse a Calendar (or Contingent) URL into its components.

    Accepts URLs like:
      https://colmiane.axess.shop/fr/Products/Tickets/Calendar/529/63/1122
      https://colmiane.axess.shop/fr/Products/Tickets/Contingent/529/63/1122

    Returns a dict with keys:
      base_url, proj_nr, pool_nr, ticket_type_id, products_path
    """
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    match = _CALENDAR_PATH_RE.search(parsed.path)
    if not match:
        raise ValueError(
            f"URL does not match expected Axess Shop pattern. "
            f"Expected: /fr/Products/Tickets/(Calendar|Contingent)/ProjNr/PoolNr/TicketTypeId\n"
            f"Got: {url}"
        )

    products_path = match.group(1)  # "fr/Products/Tickets"
    proj_nr = int(match.group(3))
    pool_nr = int(match.group(4))
    ticket_type_id = int(match.group(5))

    return {
        "base_url": base_url,
        "products_path": products_path,
        "proj_nr": proj_nr,
        "pool_nr": pool_nr,
        "ticket_type_id": ticket_type_id,
    }


class AxessShopClient:
    """Client for the Colmiane Axess Shop reservations API.

    Usage:
        # From a URL (recommended — adapts to URL changes automatically):
        client = AxessShopClient.from_url(
            "https://colmiane.axess.shop/fr/Products/Tickets/Calendar/529/63/1122"
        )

        # Or with explicit parameters (backward compatible):
        client = AxessShopClient(proj_nr=529, pool_nr=63, ticket_type_id=1122)
    """

    BASE_URL = "https://colmiane.axess.shop"

    # Default product configuration for TYROLIENNE
    PROJ_NR = 529
    POOL_NR = 63
    TICKET_TYPE_ID = 1122
    SUB_TYPE_ID = 1061  # Person type identifier for TYROLIENNE

    # Capacity handling for per-slot parsing. Real per-slot totals vary by
    # season (6, 10, 14, 15, 16, 18 places observed). The API occasionally
    # returns the TimeSlotGroup's MaxSlots (e.g. 39) for the first slot
    # instead of the real per-slot total — anything above the realistic
    # ceiling is treated as bogus and replaced with the nominal capacity.
    NOMINAL_SLOT_CAPACITY = 16
    MAX_REALISTIC_SLOT_CAPACITY = 24

    def __init__(
        self,
        session_id: Optional[str] = None,
        base_url: Optional[str] = None,
        proj_nr: Optional[int] = None,
        pool_nr: Optional[int] = None,
        ticket_type_id: Optional[int] = None,
        sub_type_id: Optional[int] = None,
    ):
        """Initialize the client.

        Args:
            session_id: Existing ASP.NET_SessionId cookie value for session reuse.
            base_url: Override the base URL (e.g. "https://colmiane.axess.shop").
            proj_nr: Override the project number.
            pool_nr: Override the pool number.
            ticket_type_id: Override the ticket type ID.
            sub_type_id: Override the person sub-type ID.
        """
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.proj_nr = proj_nr if proj_nr is not None else self.PROJ_NR
        self.pool_nr = pool_nr if pool_nr is not None else self.POOL_NR
        self.ticket_type_id = ticket_type_id if ticket_type_id is not None else self.TICKET_TYPE_ID
        self.sub_type_id = sub_type_id if sub_type_id is not None else self.SUB_TYPE_ID

        self.session = requests.Session()

        # Derive cookie domain from base_url
        cookie_domain = urlparse(self.base_url).netloc

        # Set base cookies
        if session_id:
            self.session.cookies.set("ASP.NET_SessionId", session_id, domain=cookie_domain)
        self.session.cookies.set("ci", "fr", domain=cookie_domain)

        # Default headers matching browser behavior
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        })

    # ── URL builders ───────────────────────────────────────────────────

    @property
    def calendar_url(self) -> str:
        """The Calendar page URL for this product."""
        return (
            f"{self.base_url}/fr/Products/Tickets/Calendar/"
            f"{self.proj_nr}/{self.pool_nr}/{self.ticket_type_id}"
        )

    @property
    def contingent_url(self) -> str:
        """The Contingent (time-slot selection) page URL for this product."""
        return (
            f"{self.base_url}/fr/Products/Tickets/Contingent/"
            f"{self.proj_nr}/{self.pool_nr}/{self.ticket_type_id}"
        )

    @property
    def calendar_api_url(self) -> str:
        """The JSON API endpoint for calendar data."""
        return f"{self.base_url}/api/TicketsV4TimeSlotApi/GetReservationTimeSlotsForCalendar"

    # ── Factory method ─────────────────────────────────────────────────

    @classmethod
    def from_url(cls, url: str, session_id: Optional[str] = None, sub_type_id: Optional[int] = None) -> "AxessShopClient":
        """Create a client from a Calendar (or Contingent) page URL.

        This is the recommended way to create a client — the URL is the
        single source of truth for product identity.  If the URL changes
        (different activity, different venue), you only change the URL,
        not the constants.

        Args:
            url: Full URL to the Calendar or Contingent page.
            session_id: Optional existing session cookie.
            sub_type_id: Optional person sub-type ID override.

        Returns:
            A configured AxessShopClient instance.

        Raises:
            ValueError: If the URL doesn't match the expected pattern.
        """
        parts = parse_calendar_url(url)
        return cls(
            session_id=session_id,
            base_url=parts["base_url"],
            proj_nr=parts["proj_nr"],
            pool_nr=parts["pool_nr"],
            ticket_type_id=parts["ticket_type_id"],
            sub_type_id=sub_type_id,
        )

    # ── Session management ─────────────────────────────────────────────

    def _ensure_session(self) -> None:
        """Ensure a session is established by visiting the Calendar page."""
        if "ASP.NET_SessionId" not in self.session.cookies.get_dict():
            self.session.get(self.calendar_url)

    def get_calendar_data(self, month: Optional[int] = None, year: Optional[int] = None) -> list[dict]:
        """Fetch monthly calendar overview with daily availability.

        Calls GetReservationTimeSlotsForCalendar to get aggregated data
        for all dates in the given month.

        Args:
            month: Month number (1-12). Defaults to current month.
            year: Year. Defaults to current year.

        Returns:
            List of daily entries with ValidFrom, Tariff, Products, TimeSlotInfo.
        """
        self._ensure_session()
        today = date.today()
        if month is None:
            month = today.month
        if year is None:
            year = today.year

        data = {
            "ProjNr": self.proj_nr,
            "ProductGroupIdentifier": self.pool_nr,
            "Id": self.ticket_type_id,
            "Month": month,
            "Year": year,
            "CiUppercase": "fr",
            "SubTypeIdentifiers[0][SubTypeIdentifier]": self.sub_type_id,
            "SubTypeIdentifiers[0][Quantity]": 0,
            "Type": 0,
        }

        resp = self.session.post(
            self.calendar_api_url,
            data=data,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.calendar_url,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def get_time_slots_html(self, target_date: str, quantity: int = 1) -> str:
        """Get the Contingent (time slot selection) HTML page for a given date.

        This submits the date/quantity form via POST and returns the full HTML
        page containing per-slot availability data.

        Args:
            target_date: Date string in YYYY-MM-DD format.
            quantity: Number of tickets (default 1).

        Returns:
            Raw HTML of the Contingent page.
        """
        self._ensure_session()

        form_data = {
            "TicketTypeId": self.ticket_type_id,
            "ProjNr": self.proj_nr,
            "PoolNr": self.pool_nr,
            "Date": target_date,
            "PersonTypes[0].PersonTypeId": self.sub_type_id,
            "PersonTypes[0].Quantity": quantity,
        }

        resp = self.session.post(
            self.contingent_url,
            data=form_data,
            headers={
                "Referer": self.calendar_url,
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.base_url,
            },
        )
        resp.raise_for_status()
        return resp.text

    # Multiple regex patterns to try for extracting timeSlots data.
    # The site may change the JS variable name or surrounding whitespace;
    # we try each pattern in order.
    _TIMESLOT_PATTERNS = [
        re.compile(r"timeSlots\s*:\s*(\[[\s\S]*?\])", re.IGNORECASE),
        re.compile(r"timeSlots\s*=\s*(\[[\s\S]*?\])", re.IGNORECASE),
        re.compile(r'"TimeSlots"\s*:\s*(\[[\s\S]*?\])', re.IGNORECASE),
        re.compile(r"var\s+timeSlots\s*=\s*(\[[\s\S]*?\])", re.IGNORECASE),
    ]

    @staticmethod
    def parse_time_slots(html: str) -> list[dict]:
        """Parse time slot data from the Contingent page HTML.

        Time slot availability data is embedded in the page as a JavaScript
        JSON variable: `timeSlots: [{...}]`.

        Each entry contains:
          - time: minutes from midnight (e.g. 600 = 10:00)
          - availableSlots: number of free places
          - total: total capacity for that slot
          - date: date string

        Args:
            html: Raw HTML of the Contingent page.

        Returns:
            List of dicts with keys: time, available, max, reserved.
        """
        # Try multiple regex patterns to extract the timeSlots JSON array
        raw_slots = None
        for pattern in AxessShopClient._TIMESLOT_PATTERNS:
            match = pattern.search(html)
            if match:
                try:
                    raw_slots = json.loads(match.group(1))
                    if isinstance(raw_slots, list) and raw_slots:
                        break
                except json.JSONDecodeError:
                    continue

        if not raw_slots or not isinstance(raw_slots, list):
            return []

        slots = []
        for entry in raw_slots:
            total_minutes = entry.get("time", 0)
            hours = total_minutes // 60
            minutes = total_minutes % 60
            time_str = f"{hours:02d}:{minutes:02d}"
            available = entry.get("availableSlots", 0)
            raw_total = entry.get("total", 0)

            # Per-slot capacity legitimately varies by season (6-18 places).
            # The API occasionally returns the TimeSlotGroup's MaxSlots
            # (e.g. 39) for the first slot instead of the real per-slot
            # capacity — treat those outliers as the nominal capacity.
            if raw_total > AxessShopClient.MAX_REALISTIC_SLOT_CAPACITY:
                total = AxessShopClient.NOMINAL_SLOT_CAPACITY
            else:
                total = raw_total

            # The site can report more available slots than capacity
            # (e.g. after cancellations); never emit a negative count.
            reserved = max(0, total - available)

            slots.append({
                "time": time_str,
                "available": available,
                "max": total,
                "reserved": reserved,
            })

        # Sort by time
        slots.sort(key=lambda s: s["time"])
        return slots

    def get_time_slots(self, target_date: str, quantity: int = 1) -> list[dict]:
        """Convenience method: fetch and parse time slots for a date.

        Args:
            target_date: Date string in YYYY-MM-DD format.
            quantity: Number of tickets (default 1).

        Returns:
            List of time slot dicts with time, available, max, reserved.
        """
        html = self.get_time_slots_html(target_date, quantity)
        return self.parse_time_slots(html)

    def get_daily_availability(self, month: Optional[int] = None, year: Optional[int] = None) -> list[dict]:
        """Get daily aggregate availability for a month.

        Returns a simplified view of daily reserved/max slots.

        Args:
            month: Month number. Defaults to current month.
            year: Year. Defaults to current year.

        Returns:
            List of dicts with date, tariff, available, max, reserved.
        """
        data = self.get_calendar_data(month, year)
        result = []
        for entry in data:
            valid_from = entry.get("ValidFrom")
            tariff = entry.get("Tariff")
            slots_info = entry.get("TimeSlotInfo") or []

            for slot_group in slots_info:
                available = slot_group.get("AvailableSlots", 0)
                max_slots = slot_group.get("MaxSlots", 0)
                result.append({
                    "date": valid_from,
                    "tariff": tariff,
                    "available": available,
                    "max": max_slots,
                    "reserved": max_slots - available,
                    "limited_threshold": slot_group.get("LimitedThreshold"),
                    "time_slot_group_key": slot_group.get("TimeSlotGroupKey"),
                })
        return result

    def get_all_upcoming_slots(self, num_days: int = 14) -> dict:
        """Get detailed time slot data for all upcoming days.

        Fetches the calendar overview first, then for each upcoming day
        with availability > 0, fetches the per-slot details.

        Args:
            num_days: Number of upcoming days to check.

        Returns:
            Dict keyed by date (YYYY-MM-DD) with list of time slots.
        """
        today = date.today()
        result = {}

        # Get current and next month data
        for month_offset in range(3):
            m = today.month + month_offset
            y = today.year
            while m > 12:
                m -= 12
                y += 1

            cal_data = self.get_calendar_data(m, y)
            for entry in cal_data:
                date_str = entry.get("ValidFrom")
                if not date_str:
                    continue
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                if d < today:
                    continue
                if (d - today).days > num_days:
                    continue

                # Check if date has any availability
                has_availability = any(
                    sg.get("MaxSlots", 0) > 0
                    for sg in (entry.get("TimeSlotInfo") or [])
                )

                if has_availability:
                    try:
                        slots = self.get_time_slots(date_str)
                        result[date_str] = slots
                    except Exception as e:
                        result[date_str] = {"error": str(e)}

        return result


def _merge_today_slots(old_data: dict, new_data: dict) -> dict:
    """Merge today's time slots from old and new exports.

    As the day progresses, past time slots disappear from the server.
    This preserves morning slots from a previous export while updating
    future slots with fresh data.

    Args:
        old_data: Previously exported data dict (dates → slots).
        new_data: Freshly fetched data dict (dates → slots).

    Returns:
        Merged dict with today's slots combined from both sources.
    """
    today_str = date.today().isoformat()
    old_today = old_data.get(today_str)
    new_today = new_data.get(today_str)

    if not old_today and not new_today:
        return new_data  # nothing to merge

    if not new_today:
        # API returned no slots for today (all passed), keep old data
        result = dict(new_data)
        result[today_str] = old_today
        return result

    if not old_today:
        # No previous data, just use fresh
        return new_data

    # Build merged: start with old slots, overwrite with new by matching time
    merged_slots = {s["time"]: s for s in old_today}
    for s in new_today:
        merged_slots[s["time"]] = s  # new data wins for same time

    result = dict(new_data)  # copy — all non-today dates from fresh fetch
    result[today_str] = sorted(merged_slots.values(), key=lambda s: s["time"])
    return result


def export_to_json(client: AxessShopClient = None, filepath: str = "data.json",
                    num_days: int = 14) -> str:
    """Export availability data to a JSON file for the dashboard.

    If data.json already exists, today's time slots are merged with the
    previous export so that morning slots (which disappear from the server
    as the day goes on) are preserved.

    Args:
        client: AxessShopClient instance. Created via from_url() if not provided.
        filepath: Output JSON file path.
        num_days: Number of upcoming days to fetch.

    Returns:
        Path to the written JSON file.
    """
    if client is None:
        client = AxessShopClient.from_url(
            "https://colmiane.axess.shop/fr/Products/Tickets/Calendar/529/63/1122"
        )

    print(f"Fetching {num_days} days of upcoming slots...")
    data = client.get_all_upcoming_slots(num_days=num_days)

    # Filter out error entries and keep only successful slot lists
    clean = {}
    for date_str, slots in sorted(data.items()):
        if isinstance(slots, list) and slots:
            clean[date_str] = slots
        elif isinstance(slots, dict) and "error" in slots:
            print(f"  {date_str}: ERROR — {slots['error']}")
        else:
            print(f"  {date_str}: No data")

    # Merge today's slots with previous export to preserve past time slots.
    # Also carry forward yesterday's data — the API stops returning slots
    # for past dates, but we want the final reservation count for display.
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            old_data = json.load(f)
        # Remove metadata keys before merging
        old_data = {k: v for k, v in old_data.items() if not k.startswith("_")}
        merged = _merge_today_slots(old_data, clean)

        merged_count = len(merged.get(date.today().isoformat(), []))
        clean_count = len(clean.get(date.today().isoformat(), []))
        if merged_count > clean_count:
            print(f"  Preserved {merged_count - clean_count} past slot(s) for today from previous export")

        # Preserve yesterday's data (API stops returning past dates)
        yesterday_str = (date.today() - timedelta(days=1)).isoformat()
        if yesterday_str in old_data and yesterday_str not in merged:
            merged[yesterday_str] = old_data[yesterday_str]
            print(f"  Preserved yesterday's data ({yesterday_str}) from previous export")

        clean = merged
    except (FileNotFoundError, json.JSONDecodeError):
        pass  # no previous data to merge, use fresh data as-is

    # Embed export timestamp for the dashboard
    clean["_exported_at"] = datetime.now().isoformat()

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)

    total_dates = len([k for k in clean if not k.startswith("_")])
    total_slots = sum(len(v) for k, v in clean.items() if not k.startswith("_"))
    print(f"Exported {total_dates} dates ({total_slots} slots) to {filepath}")
    return filepath


# Default Calendar URL for the TYROLIENNE activity at Colmiane.
# Change this URL to target a different product/venue — the client
# parses ProjNr, PoolNr, and TicketTypeId from it automatically.
DEFAULT_CALENDAR_URL = (
    "https://colmiane.axess.shop/fr/Products/Tickets/Calendar/529/63/1122"
)


def main():
    """Example usage of the AxessShopClient."""
    client = AxessShopClient.from_url(DEFAULT_CALENDAR_URL)

    today = date.today()
    print(f"=== Colmiane Axess Shop - Reservation Data ===")
    print(f"Calendar URL: {client.calendar_url}")
    print(f"Today: {today}")
    print()

    # 1. Get daily summary for current month
    print("--- Calendar Overview (Current Month) ---")
    daily = client.get_daily_availability()
    for entry in daily:
        print(f"  {entry['date']}: {entry['available']}/{entry['max']} available (tariff: {entry['tariff']}€)")
    print()

    # 2. Get detailed time slots for today (or next available day)
    target_date = today.isoformat()
    print(f"--- Time Slot Details for {target_date} ---")
    try:
        slots = client.get_time_slots(target_date)
        if slots:
            total_reserved = sum(s["reserved"] for s in slots)
            total_max = sum(s["max"] for s in slots)
            print(f"  Total: {total_reserved}/{total_max} places reserved across {len(slots)} time slots")
            print()
            for s in slots:
                status = "FULL" if s["available"] == 0 else "OK"
                print(f"  {s['time']}: {s['available']}/{s['max']} free ({s['reserved']} reserved) [{status}]")
        else:
            print("  No time slots found or date unavailable.")
    except Exception as e:
        print(f"  Error: {e}")
    print()

    # 3. All upcoming days
    print("--- All Upcoming Days (7 days) ---")
    upcoming = client.get_all_upcoming_slots(num_days=7)
    for date_str, slots in sorted(upcoming.items()):
        if isinstance(slots, list) and slots:
            total_reserved = sum(s["reserved"] for s in slots)
            total_max = sum(s["max"] for s in slots)
            print(f"  {date_str}: {total_reserved}/{total_max} reserved across {len(slots)} time slots")
            for s in slots:
                print(f"    {s['time']}: {s['available']}/{s['max']} free ({s['reserved']} reserved)")
        elif isinstance(slots, dict) and "error" in slots:
            print(f"  {date_str}: ERROR - {slots['error']}")
        else:
            print(f"  {date_str}: No data")
    print()

    # 4. Summary statistics
    today_slots = client.get_time_slots(today.isoformat())
    if today_slots:
        print("--- Today's Summary ---")
        print(f"  Date: {today.isoformat()}")
        print(f"  Activity: TYROLIENNE @ 35€")
        print(f"  Time slots: {len(today_slots)} (30-min intervals from 10:00 to ~16:00)")
        print(f"  Total places: {sum(s['max'] for s in today_slots)}")
        print(f"  Total reserved: {sum(s['reserved'] for s in today_slots)}")
        print(f"  Total free: {sum(s['available'] for s in today_slots)}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--export":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 14
        export_to_json(num_days=days)
    else:
        main()
