"""Render a trip's daily logs as a printable, FMCSA-style PDF (one page/day).

Uses ReportLab (pure Python) so it works cross-platform with no native deps.
The layout mirrors the paper "Driver's Daily Log": header block, the 24-hour ×
4-duty-status grid with a stepped duty line, per-row totals, remarks, the
shipping-documents box, and the 70-hour/8-day recap.
"""

from __future__ import annotations

import io
from datetime import date, datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas

# Duty status -> grid row (top to bottom), matching the official form.
ROW_LABELS = [
    ("1. Off Duty", "off_duty"),
    ("2. Sleeper Berth", "sleeper"),
    ("3. Driving", "driving"),
    ("4. On Duty (not driving)", "on_duty"),
]
ROW_INDEX = {"off_duty": 0, "sleeper": 1, "driving": 2, "on_duty": 3}

PAGE_W, PAGE_H = landscape(letter)   # 792 x 612 pt
MARGIN = 36

# Grid geometry (points).
GRID_X = 150                          # left edge of the 24h grid
TOTAL_W = 52                          # "Total Hours" column width
GRID_W = PAGE_W - MARGIN - TOTAL_W - GRID_X
ROW_H = 22
GRID_H = ROW_H * 4


def _parse(dt: str) -> datetime:
    return datetime.fromisoformat(dt)


def _minutes_into(dt: str, day_key: str) -> float:
    midnight = datetime.fromisoformat(f"{day_key}T00:00:00")
    return (_parse(dt) - midnight).total_seconds() / 60.0


def _x_for_minutes(m: float) -> float:
    return GRID_X + (max(0.0, min(1440.0, m)) / 1440.0) * GRID_W


def _hour_label(h: int) -> str:
    if h in (0, 24):
        return "Midnight"
    if h == 12:
        return "Noon"
    return str(h % 12)


def _day_from_to(day: dict) -> tuple[str, str]:
    """Best-effort From/To city labels for a day, from its segment locations."""
    locs = [s.get("location", "") for s in day.get("segments", [])
            if s.get("location") and s.get("note") != "Off duty"]
    frm = locs[0].split(",")[0] if locs else ""
    to = locs[-1].split(",")[0] if locs else ""
    return frm, to


# ---------------------------------------------------------------------------

def _draw_header(c: canvas.Canvas, trip, day: dict, top: float) -> float:
    """Draw the title + header fields. Returns the y just below the header."""
    d = _date_parts(day["date"])
    frm, to = _day_from_to(day)

    c.setFont("Helvetica-Bold", 15)
    c.drawString(MARGIN, top, "Driver's Daily Log")
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN + 130, top + 1, "(24 hours)")
    c.drawRightString(PAGE_W - MARGIN, top + 4,
                      "Original — File at home terminal.")
    c.drawRightString(PAGE_W - MARGIN, top - 6,
                      "Duplicate — Driver retains for 8 days.")

    # Date line (month / day / year), centered.
    c.setFont("Helvetica-Bold", 11)
    date_str = f"{d[0]} / {d[1]} / {d[2]}"
    c.drawCentredString(PAGE_W / 2, top, date_str)
    c.setFont("Helvetica", 6)
    c.drawCentredString(PAGE_W / 2, top - 9, "(month)         (day)         (year)")

    y = top - 26
    line_h = 15

    def field(x, w, label, value):
        c.setFont("Helvetica", 6)
        c.drawString(x, y, label)
        c.setFont("Helvetica", 9)
        c.drawString(x, y - 10, value or "")
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        c.line(x, y - 12, x + w, y - 12)

    # Row 1: From / To / Carrier
    field(MARGIN, 150, "From:", frm)
    field(MARGIN + 170, 150, "To:", to)
    field(MARGIN + 340, PAGE_W - MARGIN - (MARGIN + 340),
          "Name of Carrier or Carriers:", trip.carrier_name)

    y -= (line_h + 14)
    # Row 2: miles + office/terminal
    field(MARGIN, 110, "Total Miles Driving Today:",
          str(round(day.get("driving_miles", 0))))
    field(MARGIN + 130, 110, "Total Mileage Today:",
          str(round(day.get("driving_miles", 0))))
    field(MARGIN + 260, 130, "Main Office Address:", trip.main_office_address)
    field(MARGIN + 400, PAGE_W - MARGIN - (MARGIN + 400),
          "Home Terminal Address:", trip.home_terminal_address)

    y -= (line_h + 14)
    # Row 3: truck/trailer + driver
    field(MARGIN, 300,
          "Truck/Tractor & Trailer Numbers or License Plate(s):",
          trip.truck_trailer_numbers)
    field(MARGIN + 320, PAGE_W - MARGIN - (MARGIN + 320),
          "Driver:", trip.driver_name)

    return y - 22


def _draw_grid(c: canvas.Canvas, day: dict, grid_top: float) -> float:
    """Draw the 24h × 4-row grid + duty line + totals. Returns y below grid."""
    top_row_y = grid_top                       # y of the top edge of row 0
    bottom_y = top_row_y - GRID_H

    # Hour labels above the grid.
    c.setFont("Helvetica", 5.5)
    for h in range(25):
        x = _x_for_minutes(h * 60)
        c.drawCentredString(x, top_row_y + 4, _hour_label(h))

    # Quarter-hour minor lines.
    c.setStrokeColor(colors.Color(0.8, 0.8, 0.8))
    c.setLineWidth(0.25)
    for q in range(24 * 4 + 1):
        if q % 4 == 0:
            continue
        x = GRID_X + (q / (24 * 4)) * GRID_W
        c.line(x, top_row_y, x, bottom_y)

    # Hour lines (full height).
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.6)
    for h in range(25):
        x = _x_for_minutes(h * 60)
        c.line(x, top_row_y, x, bottom_y)

    # Row separators + labels + totals.
    totals = day.get("totals", {})
    for i, (label, key) in enumerate(ROW_LABELS):
        ry_top = top_row_y - i * ROW_H
        c.setLineWidth(0.6)
        c.line(GRID_X, ry_top, GRID_X + GRID_W, ry_top)
        c.setFont("Helvetica", 7)
        c.drawRightString(GRID_X - 6, ry_top - ROW_H / 2 - 2, label)
        # total hours column
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(GRID_X + GRID_W + TOTAL_W / 2,
                            ry_top - ROW_H / 2 - 3,
                            f"{totals.get(key, 0):.2f}")
    c.line(GRID_X, bottom_y, GRID_X + GRID_W, bottom_y)

    # Total-hours column frame + header.
    c.rect(GRID_X + GRID_W, bottom_y, TOTAL_W, GRID_H, stroke=1, fill=0)
    c.setFont("Helvetica", 5.5)
    c.drawCentredString(GRID_X + GRID_W + TOTAL_W / 2, top_row_y + 4, "Total Hours")

    # Duty-status line.
    c.setStrokeColor(colors.HexColor("#c8102e"))
    c.setLineWidth(1.6)
    prev_x = prev_y = None
    for seg in day.get("segments", []):
        key = seg["status"]
        if key not in ROW_INDEX:
            continue
        row = ROW_INDEX[key]
        y = top_row_y - row * ROW_H - ROW_H / 2
        x1 = _x_for_minutes(_minutes_into(seg["start"], day["date"]))
        x2 = _x_for_minutes(_minutes_into(seg["end"], day["date"]))
        if prev_x is not None and prev_y is not None:
            c.line(prev_x, prev_y, x1, y)      # vertical connector
        c.line(x1, y, x2, y)                     # horizontal run
        prev_x, prev_y = x2, y

    return bottom_y - 16


def _draw_remarks_and_recap(c: canvas.Canvas, trip, day: dict, top: float):
    # Remarks
    c.setFont("Helvetica-Bold", 8)
    c.drawString(MARGIN, top, "Remarks:")
    c.setFont("Helvetica", 7)
    y = top - 11
    events = [s for s in day.get("segments", [])
              if s.get("note") and s["note"] != "Off duty"
              and s["status"] != "driving"]
    for s in events[:8]:
        t = _parse(s["start"]).strftime("%H:%M")
        note = s["note"]
        if note.startswith("Fueling"):
            note += "" if s.get("verified") else " (approx.)"
        loc = s.get("location", "")
        c.drawString(MARGIN + 4, y, f"{t}  —  {note}"
                     + (f"  @ {loc.split(',')[0]}" if loc else ""))
        y -= 10

    # Shipping documents box (right of remarks).
    sx = MARGIN + 330
    c.setFont("Helvetica", 6)
    c.drawString(sx, top, "Shipping Documents:")
    c.setFont("Helvetica", 8)
    c.drawString(sx, top - 11, f"DVL or Manifest No.: {trip.shipping_document}")
    c.drawString(sx, top - 22, f"Shipper & Commodity: {trip.shipper_commodity}")

    # Recap (70hr/8day).
    rx = PAGE_W - MARGIN - 200
    on_today = day.get("total_on_duty", 0.0)
    cycle_end = day.get("_cycle_running", 0.0)
    available = max(0.0, 70.0 - cycle_end)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(rx, top, "Recap — 70 hr / 8 day")
    c.setFont("Helvetica", 7)
    c.drawString(rx, top - 11, f"On-duty hours today (lines 3 + 4): {on_today:.2f}")
    c.drawString(rx, top - 22, f"Total on duty, incl. today: {cycle_end:.2f}")
    c.drawString(rx, top - 33, f"Hours available tomorrow (70 − used): {available:.2f}")


def _date_parts(day_key: str) -> tuple[str, str, str]:
    d = date.fromisoformat(day_key)
    return (f"{d.month:02d}", f"{d.day:02d}", str(d.year))


def render_trip_pdf(trip) -> bytes:
    """Render every day of a planned trip into a multi-page PDF."""
    result = trip.result or {}
    days = (result.get("plan") or {}).get("days") or []
    if not days:
        raise ValueError("Trip has no computed plan to render.")

    # Pre-compute the running 70-hr cycle total per day for the recap.
    running = float(trip.current_cycle_used or 0.0)
    for day in days:
        running += day.get("total_on_duty", 0.0)
        day["_cycle_running"] = running

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    for i, day in enumerate(days):
        c.setTitle(f"Driver Daily Log — {day['date']}")
        top = PAGE_H - MARGIN - 6
        grid_top = _draw_header(c, trip, day, top)
        below = _draw_grid(c, day, grid_top)
        _draw_remarks_and_recap(c, trip, day, below)
        # Footer note.
        c.setFont("Helvetica-Oblique", 6)
        c.drawString(MARGIN, MARGIN - 12,
                     f"Day {i + 1} of {len(days)}  ·  Times in home-terminal "
                     f"local time  ·  Generated by ELD Trip Planner")
        c.showPage()
    c.save()
    return buf.getvalue()
