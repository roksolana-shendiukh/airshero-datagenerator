import random
import string
import logging
from datetime import timedelta
from sqlalchemy import text

logger = logging.getLogger(__name__)

BATCH_SIZE             = 10_000
MAX_DAYS_BEFORE_FLIGHT = 330

_used_numbers = set()


def _random_booking_number():
    while True:
        num = "BK" + "".join(random.choices(string.digits, k=8))
        if num not in _used_numbers:
            _used_numbers.add(num)
            return num


def _booking_date(departs_date):
    earliest      = departs_date - timedelta(days=MAX_DAYS_BEFORE_FLIGHT)
    delta_seconds = int((departs_date - earliest).total_seconds())
    return earliest + timedelta(seconds=random.randint(0, delta_seconds))


def generate_bookings(engine):
    with engine.begin() as conn:

        booking_statuses = {
            name: sid
            for sid, name in conn.execute(text(
                "SELECT booking_status_id, booking_status_name FROM BookingStatus"
            ))
        }
        flight_statuses = {
            name: sid
            for sid, name in conn.execute(text(
                "SELECT flight_status_id, flight_status_name FROM FlightStatus"
            ))
        }

        status_confirmed = booking_statuses["Confirmed"]
        status_cancelled = booking_statuses["Cancelled"]
        cancelled_flight = flight_statuses["Cancelled"]

        flights = conn.execute(text("""
            SELECT sf.schedule_flight_id, sf.departs_date, sf.flight_status_id, a.seat_capacity
            FROM ScheduledFlight sf
            JOIN Flight f  ON f.flight_id      = sf.flight_id
            JOIN Airfleet a ON a.airfleet_id   = f.airfleet_id
        """)).fetchall()

        if not flights:
            logger.warning("No flights found in ScheduledFlight")
            return

        total_inserted = 0
        batch = []

        for sf_id, departs_date, flight_status_id, seat_capacity in flights:
            is_cancelled = flight_status_id == cancelled_flight

            occupancy = random.uniform(0.05, 0.15) if is_cancelled else random.uniform(0.45, 0.65)
            num_bookings = int(seat_capacity * occupancy)

            for _ in range(num_bookings):
                status_id    = random.choices(
                    [status_confirmed, status_cancelled],
                    weights=[95, 5]
                )[0]
                booking_date = _booking_date(departs_date)

                batch.append({
                    "booking_status_id":    status_id,
                    "booking_date_time":    booking_date,
                    "booking_total_amount": 0,
                    "booking_number":       _random_booking_number(),
                    "created_at":           booking_date,
                })
                total_inserted += 1

                if len(batch) >= BATCH_SIZE:
                    conn.execute(text("""
                        INSERT INTO Booking (
                            booking_status_id,
                            booking_date_time,
                            booking_total_amount,
                            booking_number,
                            created_at
                        ) VALUES (
                            :booking_status_id,
                            :booking_date_time,
                            :booking_total_amount,
                            :booking_number,
                            :created_at
                        )
                    """), batch)
                    batch.clear()

        if batch:
            conn.execute(text("""
                INSERT INTO Booking (
                    booking_status_id,
                    booking_date_time,
                    booking_total_amount,
                    booking_number,
                    created_at
                ) VALUES (
                    :booking_status_id,
                    :booking_date_time,
                    :booking_total_amount,
                    :booking_number,
                    :created_at
                )
            """), batch)

    logger.info("Booking records inserted: %d", total_inserted)

