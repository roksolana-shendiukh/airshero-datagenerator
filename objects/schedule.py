import json
import random
import logging
from datetime import datetime, timedelta
from sqlalchemy import text

logger = logging.getLogger(__name__)

HUB_AIRPORTS = {
    "LHR", "CDG", "FRA", "IST", "DXB",
    "JFK", "LAX", "ORD", "PEK", "PVG",
    "SYD", "AUH", "GRU", "KBP"
}
UA_AIRPORTS  = {"KBP", "IEV", "LWO", "ODS", "HRK"}
USA_AIRPORTS = {"JFK", "LGA", "LAX", "BUR", "ORD", "MDW", "MIA", "IAH", "HOU"}
AU_AIRPORTS  = {"SYD", "MEL"}
EU_AIRPORTS  = {
    "LHR", "LGW", "MAN", "BHX", "CDG", "ORY", "LYS",
    "FRA", "BER", "MUC", "FCO", "CIA", "MXP", "LIN",
    "WAW", "KRK", "WRO", "IST", "SAW", "ESB"
}

SEASONS = [
    ("2025-11-01", "2026-02-28"),
    ("2026-03-01", "2026-05-31"),
    ("2026-06-01", "2026-09-30"),
]

ALL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _season_count(dep_code, arr_code, flight_range):
    both_hub = dep_code in HUB_AIRPORTS and arr_code in HUB_AIRPORTS
    both_ua  = dep_code in UA_AIRPORTS  and arr_code in UA_AIRPORTS
    both_usa = dep_code in USA_AIRPORTS and arr_code in USA_AIRPORTS
    both_au  = dep_code in AU_AIRPORTS  and arr_code in AU_AIRPORTS
    both_eu  = dep_code in EU_AIRPORTS  and arr_code in EU_AIRPORTS

    if both_hub:
        return random.randint(2, 3)
    if both_ua:
        return random.randint(2, 3)
    if both_usa or both_au:
        return 2
    if both_eu and flight_range < 2000:
        return 2
    return random.randint(1, 2)


def _days_of_week(dep_code, arr_code, flight_range):
    both_hub = dep_code in HUB_AIRPORTS and arr_code in HUB_AIRPORTS
    both_ua  = dep_code in UA_AIRPORTS  and arr_code in UA_AIRPORTS
    both_eu  = dep_code in EU_AIRPORTS  and arr_code in EU_AIRPORTS

    if both_hub:
        count = random.randint(4, 6)
    elif both_ua or (both_eu and flight_range < 2000):
        count = random.randint(2, 4)
    else:
        count = random.randint(1, 3)

    return random.sample(ALL_DAYS, count)


def _arrival_time(dep_minutes: int, duration_minutes: int) -> int:
    return (dep_minutes + duration_minutes) % (24 * 60)


def _minutes_to_time(minutes: int) -> str:
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}:00"


def generate_flight_schedules(engine):
    with engine.begin() as conn:
        flights = [dict(r._mapping) for r in conn.execute(text("""
            SELECT f.flight_id, f.flight_number, f.flight_duration, f.route_id,
                   r.flight_range, r.departs_airport_id, r.arrives_airport_id
            FROM Flight f
            JOIN Route r ON f.route_id = r.route_id
        """))]

        airports = {r[0]: r[1] for r in conn.execute(text(
            "SELECT airport_id, airport_code FROM Airport"
        ))}

        existing_schedules = [dict(r._mapping) for r in conn.execute(text(
            "SELECT schedule_id, schedule_departure_time, schedule_arrival_time FROM Schedule"
        ))]

        day_for_schedule = {r[0]: r[1] for r in conn.execute(text(
            "SELECT day_id, day_name FROM DayForSchedule"
        ))}

        inserted_seasons   = 0
        inserted_schedules = 0
        inserted_fs        = 0
        inserted_ds        = 0
        inserted_fsds      = 0

        route_departure_minutes = {}

        for flight in flights:
            dep_code     = airports.get(flight["departs_airport_id"], "")
            arr_code     = airports.get(flight["arrives_airport_id"], "")
            flight_range = float(flight["flight_range"])
            route_id     = flight["route_id"]

            duration_td      = flight["flight_duration"]
            duration_minutes = duration_td.hour * 60 + duration_td.minute

            reverse_key = (flight["arrives_airport_id"], flight["departs_airport_id"])
            forward_key = (flight["departs_airport_id"], flight["arrives_airport_id"])

            if reverse_key in route_departure_minutes:
                reverse_dep = route_departure_minutes[reverse_key]
                reverse_arr = _arrival_time(reverse_dep, duration_minutes)
                dep_minutes = (reverse_arr + random.randint(60, 120)) % (24 * 60)
            else:
                min_dep = 6 * 60
                max_dep = 22 * 60 - duration_minutes
                if max_dep < min_dep:
                    max_dep = min_dep
                dep_minutes = random.randint(min_dep, max_dep)

            route_departure_minutes[forward_key] = dep_minutes
            arr_minutes = _arrival_time(dep_minutes, duration_minutes)

            dep_time_str = _minutes_to_time(dep_minutes)
            arr_time_str = _minutes_to_time(arr_minutes)

            existing = next((
                s for s in existing_schedules
                if s["schedule_departure_time"].strftime("%H:%M:%S") == dep_time_str
                and s["schedule_arrival_time"].strftime("%H:%M:%S") == arr_time_str
            ), None)

            if existing:
                schedule_id = existing["schedule_id"]
            else:
                schedule_id = conn.execute(text("""
                    INSERT INTO Schedule (schedule_departure_time, schedule_arrival_time)
                    OUTPUT inserted.schedule_id
                    VALUES (:dep, :arr)
                """), {"dep": dep_time_str, "arr": arr_time_str}).scalar_one()
                existing_schedules.append({
                    "schedule_id": schedule_id,
                    "schedule_departure_time": datetime.strptime(dep_time_str, "%H:%M:%S"),
                    "schedule_arrival_time":   datetime.strptime(arr_time_str, "%H:%M:%S")
                })
                inserted_schedules += 1

            days = _days_of_week(dep_code, arr_code, flight_range)
            day_schedule_ids = []
            for day_name in days:
                day_id = next((k for k, v in day_for_schedule.items() if v == day_name), None)
                if not day_id:
                    continue

                exists = conn.execute(text("""
                    SELECT TOP 1 day_schedule_id FROM DaySchedule
                    WHERE schedule_id = :sid AND day_id = :did
                """), {"sid": schedule_id, "did": day_id}).scalar_one_or_none()

                if exists:
                    day_schedule_ids.append(exists)
                else:
                    ds_id = conn.execute(text("""
                        INSERT INTO DaySchedule (schedule_id, day_id)
                        OUTPUT inserted.day_schedule_id
                        VALUES (:sid, :did)
                    """), {"sid": schedule_id, "did": day_id}).scalar_one()
                    day_schedule_ids.append(ds_id)
                    inserted_ds += 1

            season_count   = _season_count(dep_code, arr_code, flight_range)
            chosen_seasons = random.sample(SEASONS, min(season_count, len(SEASONS)))

            for season_start, season_end in chosen_seasons:
                season_id = conn.execute(text("""
                    INSERT INTO FlightSeason (season_start_date, season_end_date)
                    OUTPUT inserted.flight_season_id
                    VALUES (:start, :end)
                """), {"start": season_start, "end": season_end}).scalar_one()
                inserted_seasons += 1

                fs_id = conn.execute(text("""
                    INSERT INTO FlightSchedule (flight_id, flight_season_id)
                    OUTPUT inserted.flight_schedule_id
                    VALUES (:fid, :fsid)
                """), {"fid": flight["flight_id"], "fsid": season_id}).scalar_one()
                inserted_fs += 1

                for ds_id in day_schedule_ids:
                    conn.execute(text("""
                        INSERT INTO FlightScheduleDaySchedule (flight_schedule_id, day_schedule_id)
                        VALUES (:fsid, :dsid)
                    """), {"fsid": fs_id, "dsid": ds_id})
                    inserted_fsds += 1

        logger.info("FlightSeason inserted:             %d", inserted_seasons)
        logger.info("Schedule inserted:                 %d", inserted_schedules)
        logger.info("DaySchedule inserted:              %d", inserted_ds)
        logger.info("FlightSchedule inserted:           %d", inserted_fs)
        logger.info("FlightScheduleDaySchedule inserted:%d", inserted_fsds)

        