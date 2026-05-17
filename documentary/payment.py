import random
import logging
from datetime import datetime, timedelta
from sqlalchemy import text

logger = logging.getLogger(__name__)

BATCH_SIZE      = 10_000
PROGRESS_STEP   = 10_000
FAILED_PERCENT  = 0.02
PARTIAL_PERCENT = 0.06


def _payment_date(booking_dt):
    return booking_dt + timedelta(seconds=random.randint(0, 600))


def _pick_method(method_ids, card_id):
    if random.random() < 0.80:
        return card_id
    others = [m for m in method_ids if m != card_id]
    return random.choice(others) if others else card_id


def generate_payments(engine):
    now = datetime.utcnow()

    with engine.begin() as conn:
        logger.info("Loading data...")

        payment_methods = {
            name: mid
            for mid, name in conn.execute(text("SELECT payment_method_id, payment_method_name FROM PaymentMethod"))
        }
        payment_statuses = {
            name: sid
            for sid, name in conn.execute(text("SELECT payment_status_id, payment_status_name FROM PaymentStatus"))
        }
        booking_statuses = {
            name: sid
            for sid, name in conn.execute(text("SELECT booking_status_id, booking_status_name FROM BookingStatus"))
        }

        status_paid       = payment_statuses["Paid"]
        status_pending    = payment_statuses["Partially Pending"]
        status_failed     = payment_statuses["Failed"]
        booking_cancelled = booking_statuses["Cancelled"]

        method_ids = list(payment_methods.values())
        card_id    = payment_methods.get("Card")
        if not card_id:
            logger.warning("'Card' payment method not found, using first available")
            card_id = method_ids[0]

        total_bookings = conn.execute(text("SELECT COUNT(*) FROM Booking")).scalar()
        logger.info("Total bookings: %d", total_bookings)

        batch     = []
        processed = 0
        skipped   = 0
        offset    = 0

        while offset < total_bookings:
            bookings = conn.execute(text("""
                SELECT booking_id, booking_total_amount, booking_status_id, booking_date_time
                FROM Booking
                ORDER BY booking_id
                OFFSET :offset ROWS FETCH NEXT :batch_size ROWS ONLY
            """), {"offset": offset, "batch_size": BATCH_SIZE}).fetchall()

            if not bookings:
                break

            for booking in bookings:
                b_id       = booking.booking_id
                total      = float(booking.booking_total_amount)
                b_status   = booking.booking_status_id
                booking_dt = booking.booking_date_time

                if b_status == booking_cancelled:
                    skipped += 1
                    continue

                if random.random() < FAILED_PERCENT:
                    batch.append({
                        "booking_id":        b_id,
                        "payment_status_id": status_failed,
                        "payment_method_id": _pick_method(method_ids, card_id),
                        "payment_date_time": _payment_date(booking_dt),
                        "payment_amount":    total,
                        "created_at":        now,
                    })
                elif random.random() < PARTIAL_PERCENT:
                    num_parts = random.choice([2, 3])
                    remaining = total
                    for i in range(num_parts):
                        if i == num_parts - 1:
                            part_amount = round(remaining, 2)
                            p_status    = status_paid
                        else:
                            part_amount = round(random.uniform(0.2, 0.6) * remaining, 2)
                            remaining  -= part_amount
                            p_status    = status_pending
                        batch.append({
                            "booking_id":        b_id,
                            "payment_status_id": p_status,
                            "payment_method_id": _pick_method(method_ids, card_id),
                            "payment_date_time": _payment_date(booking_dt),
                            "payment_amount":    part_amount,
                            "created_at":        now,
                        })
                else:
                    batch.append({
                        "booking_id":        b_id,
                        "payment_status_id": status_paid,
                        "payment_method_id": _pick_method(method_ids, card_id),
                        "payment_date_time": _payment_date(booking_dt),
                        "payment_amount":    total,
                        "created_at":        now,
                    })

                processed += 1

            if batch:
                conn.execute(text("""
                    INSERT INTO Payment
                        (booking_id, payment_status_id, payment_method_id,
                         payment_date_time, payment_amount, created_at)
                    VALUES
                        (:booking_id, :payment_status_id, :payment_method_id,
                         :payment_date_time, :payment_amount, :created_at)
                """), batch)
                batch.clear()

            offset += BATCH_SIZE
            logger.info("Processed %d / %d bookings", processed, total_bookings)

    logger.info("Payments inserted: %d, skipped (cancelled): %d", processed, skipped)