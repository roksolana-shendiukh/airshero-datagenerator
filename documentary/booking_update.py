import logging
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
import random
from sqlalchemy import text

logger = logging.getLogger(__name__)

BATCH_SIZE    = 10_000
PROGRESS_STEP = 10_000


def _realistic_booking_date(flight_published, departs_date):
    min_date = datetime.combine(flight_published, datetime.min.time()) if not isinstance(flight_published, datetime) else flight_published
    max_date = datetime.combine(departs_date, datetime.min.time()) - timedelta(hours=1)

    if min_date >= max_date:
        return min_date

    days_before = (max_date - min_date).days
    rnd = random.random()

    if rnd < 0.75:
        start = min_date
        end   = min_date + timedelta(days=int(days_before * 0.6))
    elif rnd < 0.95:
        start = min_date + timedelta(days=int(days_before * 0.3))
        end   = min_date + timedelta(days=int(days_before * 0.6))
    else:
        start = min_date + timedelta(days=int(days_before * 0.9))
        end   = max_date

    delta = int((end - start).total_seconds())
    if delta <= 0:
        return start
    return start + timedelta(seconds=random.randint(0, delta))


def update_bookings(engine):
    now    = datetime.utcnow()
    offset = 0

    with engine.begin() as conn:
        total_bookings = conn.execute(text("SELECT COUNT(*) FROM Booking")).scalar()
        logger.info("Total bookings: %d", total_bookings)

        batch     = []
        processed = 0

        while offset < total_bookings:
            items_rows = conn.execute(text("""
                SELECT
                    b.booking_id,
                    fp.ticket_price,
                    fp.flight_published_date,
                    sf.departs_date,
                    ISNULL(SUM(bpi.baggage_price * bo.baggage_quantity), 0) AS baggage_total
                FROM Booking b
                JOIN BookingItem bi          ON bi.booking_id = b.booking_id
                JOIN FlightPrice fp          ON fp.flight_price_id = bi.flight_price_id
                JOIN ScheduledFlight sf      ON sf.schedule_flight_id = fp.schedule_flight_id
                LEFT JOIN BaggageOptionInFlight bo   ON bo.booking_item_id = bi.booking_item_id
                LEFT JOIN BaggagePricingInFlight bpi ON bpi.baggage_pricing_in_flight_id = bo.baggage_pricing_in_flight_id
                GROUP BY
                    b.booking_id, fp.ticket_price, fp.flight_published_date, sf.departs_date
                ORDER BY b.booking_id
                OFFSET :offset ROWS FETCH NEXT :batch_size ROWS ONLY
            """), {"offset": offset, "batch_size": BATCH_SIZE}).fetchall()

            if not items_rows:
                break

            bookings_data = defaultdict(list)
            for r in items_rows:
                bookings_data[r.booking_id].append(r)

            for booking_id, items in bookings_data.items():
                total_amount     = Decimal("0.00")
                new_booking_date = None

                for bi in items:
                    if new_booking_date is None:
                        new_booking_date = _realistic_booking_date(
                            bi.flight_published_date, bi.departs_date
                        )
                    total_amount += Decimal(str(bi.ticket_price))
                    total_amount += Decimal(str(bi.baggage_total))

                batch.append({
                    "bdt":        new_booking_date,
                    "total":      total_amount,
                    "updated_at": now,
                    "bid":        booking_id
                })
                processed += 1

            conn.execute(text("""
                UPDATE Booking
                SET booking_date_time    = :bdt,
                    booking_total_amount = :total,
                    updated_at           = :updated_at
                WHERE booking_id = :bid
            """), batch)
            batch.clear()

            offset += BATCH_SIZE
            logger.info("Processed %d / %d bookings", processed, total_bookings)

    logger.info("Bookings updated: %d", processed)

    
