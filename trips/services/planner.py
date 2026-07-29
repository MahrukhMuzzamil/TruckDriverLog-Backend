"""Trip planning orchestrator: geocode -> route -> HOS simulate -> payload."""
from datetime import datetime, timedelta, timezone as dt_timezone

from . import geocoding, routing
from .hos import DRIVING, simulate_trip
from .logs import build_daily_logs

STOP_TYPE_BY_KIND = {
    "pickup": "pickup",
    "dropoff": "dropoff",
    "fuel": "fuel",
    "rest10": "rest",
    "break30": "break",
    "restart34": "restart",
}


def _default_start() -> datetime:
    """Trips start at 08:00 (home terminal time) today, for readable logs."""
    now = datetime.now(dt_timezone.utc)
    return now.replace(hour=8, minute=0, second=0, microsecond=0)


def plan_trip(
    current_location: str,
    pickup_location: str,
    dropoff_location: str,
    current_cycle_used: float,
    start_time: datetime | None = None,
) -> dict:
    """Compute the full trip plan and return a JSON-serializable payload."""
    start_dt = start_time or _default_start()

    current = geocoding.geocode(current_location)
    pickup = geocoding.geocode(pickup_location)
    dropoff = geocoding.geocode(dropoff_location)

    route = routing.get_route([current, pickup, dropoff])
    leg1, leg2 = route["legs"][0], route["legs"][1]

    sim = simulate_trip(
        leg1_miles=leg1["distance_miles"],
        leg2_miles=leg2["distance_miles"],
        cycle_used=current_cycle_used,
    )

    def at(hours: float) -> str:
        return (start_dt + timedelta(hours=hours)).isoformat()

    # --- Stops & rests for the map and itinerary -----------------------------
    stops = [
        {
            "type": "start",
            "label": "Trip start",
            "lat": current["lat"],
            "lon": current["lon"],
            "arrival": at(0),
            "departure": at(0),
            "duration_hours": 0.0,
            "odometer_miles": 0.0,
        }
    ]
    for event in sim.events:
        stop_type = STOP_TYPE_BY_KIND.get(event.kind)
        if not stop_type:
            continue
        if stop_type == "pickup":
            lat, lon = pickup["lat"], pickup["lon"]
        elif stop_type == "dropoff":
            lat, lon = dropoff["lat"], dropoff["lon"]
        else:
            lat, lon = routing.point_at_mile(route, event.odometer_start)
        stops.append(
            {
                "type": stop_type,
                "label": event.label,
                "lat": lat,
                "lon": lon,
                "arrival": at(event.start),
                "departure": at(event.end),
                "duration_hours": round(event.duration, 2),
                "odometer_miles": round(event.odometer_start, 1),
            }
        )

    # --- Full schedule timeline ----------------------------------------------
    schedule = [
        {
            "status": event.status,
            "kind": event.kind,
            "label": event.label,
            "start": at(event.start),
            "end": at(event.end),
            "duration_hours": round(event.duration, 2),
            "miles": round(event.miles, 1),
            "odometer_miles": round(event.odometer_end, 1),
        }
        for event in sim.events
    ]

    logs = build_daily_logs(sim.events, start_dt, sim.cycle_used)

    driving_hours = sum(e.duration for e in sim.events if e.status == DRIVING)
    counts = {
        "fuel_stops": sum(1 for e in sim.events if e.kind == "fuel"),
        "rest_periods": sum(1 for e in sim.events if e.kind == "rest10"),
        "breaks": sum(1 for e in sim.events if e.kind == "break30"),
        "restarts": sum(1 for e in sim.events if e.kind == "restart34"),
    }

    return {
        "inputs": {
            "current_location": current_location,
            "pickup_location": pickup_location,
            "dropoff_location": dropoff_location,
            "current_cycle_used": current_cycle_used,
        },
        "locations": {"current": current, "pickup": pickup, "dropoff": dropoff},
        "route": {
            "distance_miles": round(route["distance_miles"], 1),
            "geometry": route["geometry"],
            "legs": [
                {"name": "Current -> Pickup", "distance_miles": round(leg1["distance_miles"], 1)},
                {"name": "Pickup -> Drop-off", "distance_miles": round(leg2["distance_miles"], 1)},
            ],
        },
        "summary": {
            "total_distance_miles": round(route["distance_miles"], 1),
            "driving_hours": round(driving_hours, 2),
            "total_trip_hours": round(sim.time, 2),
            "start_time": start_dt.isoformat(),
            "end_time": at(sim.time),
            "days": len(logs),
            "cycle_used_after": round(sim.cycle_used, 2),
            **counts,
        },
        "stops": stops,
        "schedule": schedule,
        "logs": logs,
    }
