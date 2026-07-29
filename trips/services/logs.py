"""Slice the continuous HOS timeline into per-calendar-day ELD log sheets.

Each sheet mirrors the paper "Driver's Daily Log": a 24-hour grid of duty
segments, total hours per duty status, miles driven that day, and remarks
for every change of duty status.
"""
from datetime import datetime, timedelta
from typing import List

from .hos import DRIVING, OFF_DUTY, DutyEvent

HOURS_PER_DAY = 24.0


def _day_bounds(start_dt: datetime, total_hours: float):
    """Yield (day_index, day_start_offset, day_end_offset) in trip-hours."""
    midnight = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    first_offset = -((start_dt - midnight).total_seconds() / 3600.0)
    day_start = first_offset
    index = 0
    while day_start < total_hours:
        yield index, day_start, day_start + HOURS_PER_DAY
        day_start += HOURS_PER_DAY
        index += 1


def build_daily_logs(
    events: List[DutyEvent], start_dt: datetime, end_cycle_used: float
) -> list:
    """Convert duty events into a list of daily log sheet dicts."""
    if not events:
        return []

    total_hours = events[-1].end
    logs = []

    for day_index, day_start, day_end in _day_bounds(start_dt, total_hours):
        date = (start_dt + timedelta(hours=day_start + 1)).date()  # +1h guards DST-free midnight edge
        segments = []
        remarks = []
        miles = 0.0

        def add_segment(status: str, seg_start: float, seg_end: float, label: str):
            segments.append(
                {
                    "status": status,
                    "start_hour": round(seg_start - day_start, 4),
                    "end_hour": round(seg_end - day_start, 4),
                    "label": label,
                }
            )

        # Off-duty padding before the trip begins (first day only).
        if day_start < 0:
            add_segment(OFF_DUTY, day_start, 0.0, "Off duty")

        for event in events:
            seg_start = max(event.start, day_start, 0.0)
            seg_end = min(event.end, day_end)
            if seg_end - seg_start <= 1e-9:
                continue
            add_segment(event.status, seg_start, seg_end, event.label)
            if event.status == DRIVING and event.duration > 0:
                miles += event.miles * (seg_end - seg_start) / event.duration
            if day_start <= event.start < day_end and event.start >= 0:
                remarks.append(
                    {
                        "hour": round(event.start - day_start, 4),
                        "label": event.label,
                        "odometer": round(event.odometer_start, 1),
                    }
                )

        # Off-duty padding after the trip ends (last day only).
        if total_hours < day_end:
            add_segment(OFF_DUTY, max(total_hours, day_start), day_end, "Off duty")

        totals = {"off_duty": 0.0, "sleeper": 0.0, "driving": 0.0, "on_duty": 0.0}
        for seg in segments:
            totals[seg["status"]] += seg["end_hour"] - seg["start_hour"]
        totals = {k: round(v, 2) for k, v in totals.items()}

        logs.append(
            {
                "day_index": day_index + 1,
                "date": date.isoformat(),
                "segments": segments,
                "totals": totals,
                "miles": round(miles, 1),
                "remarks": remarks,
            }
        )

    if logs:
        logs[-1]["cycle_used_after"] = round(end_cycle_used, 2)
    return logs
