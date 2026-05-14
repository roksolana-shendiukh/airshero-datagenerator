import random
import logging
from datetime import date, timedelta
from sqlalchemy import text

logger = logging.getLogger(__name__)


def generate_scheduled_flights(engine):
    today = date.today()

    with engine.begin() as conn:
        status_map = {name: sid for sid, name in conn.execute(text(
            "SELECT flight_status_id, flight_status_name FROM FlightStatus"
        )).fetchall()}

        scheduled_status = status_map.get("Scheduled")
        completed_status = status_map.get("Completed")
        cancelled_status = status_map.get("Cancelled")

        flight_schedules = [dict(r._mapping) for r in conn.execute(text("""
            SELECT fs.flight_schedule_id, fs.flight_id, fs.flight_season_id,
                   fse.season_start_date, fse.season_end_date
            FROM FlightSchedule fs
            JOIN FlightSeason fse ON fse.flight_season_id = fs.flight_season_id
        """))]

        day_schedule_map = {}
        for r in conn.execute(text("""
            SELECT fsds.flight_schedule_id, dfs.day_name
            FROM FlightScheduleDaySchedule fsds
            JOIN DaySchedule ds ON ds.day_schedule_id = fsds.day_schedule_id
            JOIN DayForSchedule dfs ON dfs.day_id = ds.day_id
        """)):
            day_schedule_map.setdefault(r[0], []).append(r[1])

        DAY_NAME_TO_WEEKDAY = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2,
            "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6
        }

        existing = set(
            (row[0], row[1])
            for row in conn.execute(text(
                "SELECT flight_id, departs_date FROM ScheduledFlight"
            ))
        )

        inserted = 0

        for fs in flight_schedules:
            flight_id    = fs["flight_id"]
            season_start = fs["season_start_date"]
            season_end   = fs["season_end_date"]
            fs_id        = fs["flight_schedule_id"]

            days_of_week = day_schedule_map.get(fs_id, [])
            if not days_of_week:
                continue

            weekdays = {DAY_NAME_TO_WEEKDAY[d] for d in days_of_week if d in DAY_NAME_TO_WEEKDAY}

            sales_offset     = random.choices([1, 2, 3, 4, 5], weights=[30, 25, 20, 15, 10])[0]
            sales_start_date = season_start + timedelta(days=sales_offset)

            current = season_start
            while current <= season_end:
                if current.weekday() in weekdays:
                    if (flight_id, current) not in existing:
                        is_past = current < today

                        if is_past:
                            status_id = cancelled_status if random.random() < 0.02 else completed_status
                        else:
                            status_id = cancelled_status if random.random() < 0.02 else scheduled_status

                        conn.execute(text("""
                            INSERT INTO ScheduledFlight (flight_id, flight_status_id, departs_date, sales_start_date)
                            VALUES (:flight_id, :status_id, :departs_date, :sales_start_date)
                        """), {
                            "flight_id":        flight_id,
                            "status_id":        status_id,
                            "departs_date":     current,
                            "sales_start_date": sales_start_date
                        })
                        existing.add((flight_id, current))
                        inserted += 1

                current += timedelta(days=1)

        logger.info("ScheduledFlight records inserted: %d", inserted)

        