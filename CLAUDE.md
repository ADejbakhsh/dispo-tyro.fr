# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Scrapes real-time reservation/availability data for the **TYROLIENNE** (zip line) activity at Colmiane from the Axess Shop ticketing platform. Two deliverables:

- **Python client** (`api_client.py`) — fetches data from the Axess Shop and exports to JSON
- **Static dashboard** (`index.html`) — renders the JSON as an interactive chart + day strip

## Commands

```bash
# Fetch and print today's availability summary
python api_client.py

# Export upcoming 30 days of time-slot data to data.json (dashboard input)
python api_client.py --export

# Export a custom number of days
python api_client.py --export 7
```

No test suite, no build step, no linting configured.

## Architecture

### Data flow

```
Axess Shop (colmiane.axess.shop)
  │
  ├─ POST /api/TicketsV4TimeSlotApi/GetReservationTimeSlotsForCalendar
  │     → monthly calendar overview (JSON): daily aggregates per date
  │
  └─ POST /fr/Products/Tickets/Contingent/{ProjNr}/{PoolNr}/{TicketTypeId}
        → per-time-slot HTML page: 30-min slots, 16 places each (15 at 15:00)
        → JS variable `timeSlots: [{time, availableSlots, total, ...}]`
        → parsed via regex in `parse_time_slots()`
  │
  ▼
api_client.py  ──export──►  data.json
  │                           │
  │              fetch()      ▼
  └──────────────────────  index.html  (static dashboard, no server needed)
```

### URL pattern (source of truth)

All product identity is encoded in one URL:

```
https://colmiane.axess.shop/fr/Products/Tickets/Calendar/{ProjNr}/{PoolNr}/{TicketTypeId}
                                                        529      63       1122
```

The Contingent page mirrors it (`Calendar` → `Contingent`). The JSON API lives at a fixed path under `/api/`.

`AxessShopClient.from_url(url)` parses this URL and derives all three endpoints automatically. To target a different product/venue, pass its Calendar URL — no constants to change.

### Key architectural decisions

- **No auth** — only needs `ASP.NET_SessionId` cookie (obtained by visiting the Calendar page) + `ci=fr` language cookie
- **Session state is server-side** — the Contingent POST requires prior Calendar page visit to initialize session state. `_ensure_session()` handles this transparently.
- **No JSON API for time slots** — per-slot data only exists in the HTML of the Contingent page, embedded as a JS object. Parsing is regex-based with multiple fallback patterns in `_TIMESLOT_PATTERNS`.
- **`SUB_TYPE_ID = 1061`** (person type) is NOT encoded in the URL — it's discovered from the page HTML and is the one value that must be provided separately when using `from_url()`.
- **Dashboard is fully static** — `index.html` fetches `data.json` at runtime. No web server, no build. The JSON includes an `_exported_at` timestamp used for the "last updated" display.
- **15:00 slot has 15 capacity** (not 16) — this is a site quirk, not a bug. The dashboard chart uses a fixed `maxVal = 16` y-axis.
