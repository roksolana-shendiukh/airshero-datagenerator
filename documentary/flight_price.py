import random
import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import text

logger = logging.getLogger(__name__)

MIN_PAST_POINTS = 4
MAX_PAST_POINTS = 6
MAX_PAST_DAYS   = 60
BATCH_SIZE      = 500

CLASS_MULTIPLIER = {
    "Economy":         1.0,
    "Premium Economy": 1.6,
    "Business":        3.0,
    "First":           5.5,
}

MONTH_MULT = {
    1: 0.90, 2: 0.90, 3: 1.05, 4: 1.10, 5: 1.15, 6: 1.30,
    7: 1.40, 8: 1.35, 9: 1.10, 10: 1.00, 11: 0.95, 12: 1.20,
}

WEEKDAY_MULT = {0: 1.05, 1: 0.95, 2: 0.95, 3: 1.00, 4: 1.10, 5: 1.15, 6: 1.10}


def _base_price_usd(flight_range_km):
    km = int(flight_range_km)
    if km < 1000:  return random.randint(25,  120)
    if km < 2000:  return random.randint(50,  250)
    if km < 4000:  return random.randint(120, 500)
    if km < 7000:  return random.randint(280, 900)
    if km < 11000: return random.randint(450, 1400)
    return                random.randint(600, 1800)


def _time_multiplier(days_before):
    if days_before is None: return 1.00
    if days_before >= 60:   return 0.85
    if days_before >= 30:   return 0.95
    if days_before >= 14:   return 1.05
    if days_before >= 7:    return 1.20
    if days_before >= 3:    return 1.35
    return                         1.55


def _generate_price(base_usd, flight_range_km, departs_date, days_before=None):
    price = (
        Decimal(str(base_usd))
        * Decimal(str(round(1.0 + (float(flight_range_km) / 10000) ** 0.7, 6)))
        * Decimal(str(MONTH_MULT[departs_date.month]))
        * Decimal(str(WEEKDAY_MULT[departs_date.weekday()]))
        * Decimal(str(_time_multiplier(days_before)))
        * Decimal(str(round(random.uniform(0.93, 1.07), 4)))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return max(price, Decimal("15.00"))


def _flush(conn, batch):
    if not batch:
        return
    conn.execute(text("""
        INSERT INTO FlightPrice (schedule_flight_id, flight_class_id, flight_published_date, ticket_price)
        VALUES (:sf_id, :fc_id, :fpd, :tp)
    """), batch)
    batch.clear()


def generate_flight_prices(engine):
    today = date.today()
    total_inserted = 0

    with engine.begin() as conn:
        records = conn.execute(text("""
            SELECT sf.schedule_flight_id, sf.departs_date,
                   fc.flight_class_id, c.class_name,
                   r.flight_range
            FROM ScheduledFlight sf
            JOIN Flight f ON f.flight_id = sf.flight_id
            JOIN Route r ON r.route_id = f.route_id
            JOIN FlightClass fc ON fc.flight_id = f.flight_id
            JOIN Class c ON c.class_id = fc.class_id
            WHERE sf.flight_status_id != (
                SELECT flight_status_id FROM FlightStatus WHERE flight_status_name = 'Cancelled'
            )
        """)).fetchall()

        logger.info("Records to process: %d", len(records))

        batch = []

        for sf_id, departs_date, fc_id, class_name, flight_range in records:
            base_price = _base_price_usd(flight_range) * CLASS_MULTIPLIER.get(class_name, 1.0)
            is_past    = departs_date < today

            if is_past:
                num_points = random.randint(MIN_PAST_POINTS, MAX_PAST_POINTS)
                generated  = 0

                for _ in range(num_points * 2):
                    if generated >= num_points:
                        break
                    days_before    = random.randint(1, MAX_PAST_DAYS)
                    published_date = departs_date - timedelta(days=days_before)
                    if published_date >= today:
                        continue

                    batch.append({
                        "sf_id": sf_id,
                        "fc_id": fc_id,
                        "fpd":   published_date,
                        "tp":    _generate_price(base_price, flight_range, departs_date, days_before)
                    })
                    generated      += 1
                    total_inserted += 1
            else:
                days_before = (departs_date - today).days
                batch.append({
                    "sf_id": sf_id,
                    "fc_id": fc_id,
                    "fpd":   today,
                    "tp":    _generate_price(base_price, flight_range, departs_date, days_before)
                })
                total_inserted += 1

            if len(batch) >= BATCH_SIZE:
                _flush(conn, batch)

        _flush(conn, batch)

    logger.info("FlightPrice records inserted: %d", total_inserted)

    