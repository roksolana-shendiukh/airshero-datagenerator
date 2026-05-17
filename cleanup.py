import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def cleanup_empty_bookings(engine):
    with engine.begin() as conn:
        result = conn.execute(text("""
            DELETE FROM Booking
            WHERE NOT EXISTS (
                SELECT 1 FROM BookingItem bi WHERE bi.booking_id = Booking.booking_id
            )
        """))
        logger.info("Deleted empty bookings: %d", result.rowcount)

        