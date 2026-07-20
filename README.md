# Colmiane Axess Shop - API Client

Python client for fetching reservation/availability data from [Colmiane Axess Shop](https://colmiane.axess.shop/fr/Products/Tickets/Calendar/529/63/1122).

## Overview

This client scrapes reservation data for the **TYROLIENNE** (zip line) activity at Colmiane. Each operating day has **12 time slots of 30 minutes** (10:00-16:00), each with **16 places** (except 15:00 which has 15).

## APIs Discovered

### 1. `POST /api/TicketsV4TimeSlotApi/GetReservationTimeSlotsForCalendar`
- **Type**: JSON API (XMLHttpRequest)
- **Format**: `application/x-www-form-urlencoded`
- **Purpose**: Returns monthly calendar overview with daily aggregate availability
- **Parameters**: `ProjNr`, `ProductGroupIdentifier`, `Id`, `Month`, `Year`, `CiUppercase`, `SubTypeIdentifiers`, `Type`
- **Auth**: ASP.NET Session cookie only

### 2. `POST /fr/Products/Tickets/Contingent/{ProjNr}/{PoolNr}/{TicketTypeId}`
- **Type**: HTML form submission (full page load)
- **Format**: `application/x-www-form-urlencoded`
- **Purpose**: Returns HTML page with per-time-slot availability data
- **Parameters**: `TicketTypeId`, `ProjNr`, `PoolNr`, `Date`, `PersonTypes[]`
- **Auth**: ASP.NET Session cookie only (session state must be initialized via Calendar page)

## Authentication

No login required. The site uses:
- `ASP.NET_SessionId` cookie for server-side session state
- `ci=fr` cookie for language preference
- No Bearer tokens, API keys, or OAuth

Session is automatically established by visiting any page.

## Usage

### Recommended: from a URL

The URL is the single source of truth — the client parses `ProjNr`, `PoolNr`, and `TicketTypeId` automatically:

```python
from api_client import AxessShopClient

# Create client from the Calendar page URL
client = AxessShopClient.from_url(
    "https://colmiane.axess.shop/fr/Products/Tickets/Calendar/529/63/1122"
)

# All URLs are derived from that one input:
print(client.calendar_url)     # .../Calendar/529/63/1122
print(client.contingent_url)   # .../Contingent/529/63/1122
print(client.calendar_api_url) # .../api/TicketsV4TimeSlotApi/...

# Get daily summary for current month
daily = client.get_daily_availability()
for entry in daily:
    print(f"{entry['date']}: {entry['available']}/{entry['max']} free")

# Get per-slot details for a specific date
slots = client.get_time_slots("2026-07-15")
for s in slots:
    print(f"{s['time']}: {s['available']}/{s['max']} free ({s['reserved']} reserved)")

# Get all upcoming days
upcoming = client.get_all_upcoming_slots(num_days=7)
```

### Alternative: explicit parameters (backward compatible)

```python
client = AxessShopClient(proj_nr=529, pool_nr=63, ticket_type_id=1122)
```

### Output format

Each time slot dict contains:
```json
{
  "time": "10:00",
  "available": 11,
  "max": 16,
  "reserved": 5
}
```

Each calendar entry contains:
```json
{
  "date": "2026-07-15",
  "tariff": "35,00",
  "available": 16,
  "max": 16,
  "reserved": 0,
  "limited_threshold": 3,
  "time_slot_group_key": 1005
}
```

## Example: July 15, 2026

| Time   | Free | Max | Reserved |
|--------|------|-----|----------|
| 10:00  | 11   | 16  | 5        |
| 10:30  | 16   | 16  | 0        |
| 11:00  | 8    | 16  | 8        |
| 11:30  | 14   | 16  | 2        |
| 12:00  | 11   | 16  | 5        |
| 13:00  | 16   | 16  | 0        |
| 13:30  | 12   | 16  | 4        |
| 14:00  | 10   | 16  | 6        |
| 14:30  | 16   | 16  | 0        |
| 15:00  | 14   | 15  | 1        |
| 15:30  | 16   | 16  | 0        |
| 16:00  | 14   | 16  | 2        |

## Caveats

1. **Session-dependent**: The time slot detail page requires server-side session state set by prior page visits. The client handles this automatically by visiting the Calendar page first.
2. **HTML parsing**: Per-slot data is only available in the HTML of the Contingent page (no JSON API). Uses regex to extract slot data.
3. **Rate limiting**: No rate limiting observed, but be respectful.
4. **Date format**: Dates use YYYY-MM-DD format internally. The Contingent POST expects this format.
5. **404 for direct GET**: The Contingent page returns 302 → 404 if accessed via GET without the proper session state.

## Files

- `api_client.py` - The API client
- `README.md` - This file

## URL Pattern

The Axess Shop uses a consistent URL structure:

```
{base_url}/fr/Products/Tickets/Calendar/{ProjNr}/{PoolNr}/{TicketTypeId}
```

And the time-slot selection page mirrors it:

```
{base_url}/fr/Products/Tickets/Contingent/{ProjNr}/{PoolNr}/{TicketTypeId}
```

To target a different product or venue, just pass the new Calendar URL to `from_url()` — no constants to update.
