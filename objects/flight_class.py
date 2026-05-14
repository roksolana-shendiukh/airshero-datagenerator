import random
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

SHORT_RANGE  = 2000
MEDIUM_RANGE = 5000


def generate_flight_class(engine):
    with engine.begin() as conn:
        class_map = {name: cid for cid, name in conn.execute(text(
            "SELECT class_id, class_name FROM Class"
        )).fetchall()}

        flights = [dict(r._mapping) for r in conn.execute(text("""
            SELECT f.flight_id, r.flight_range
            FROM Flight f
            JOIN Route r ON f.route_id = r.route_id
        """))]

        inserted = 0

        for flight in flights:
            flight_id    = flight["flight_id"]
            flight_range = float(flight["flight_range"])

            classes = ["Economy"]

            if flight_range < SHORT_RANGE:
                if random.random() < 0.2:
                    classes.append("Business")
            elif flight_range < MEDIUM_RANGE:
                if random.random() < 0.6:
                    classes.append("Business")
                if random.random() < 0.3:
                    classes.append("Premium Economy")
            else:
                classes.append("Business")
                if random.random() < 0.7:
                    classes.append("Premium Economy")
                if random.random() < 0.4:
                    classes.append("First")

            for class_name in classes:
                class_id = class_map.get(class_name)
                if not class_id:
                    continue

                exists = conn.execute(text("""
                    SELECT 1 FROM FlightClass
                    WHERE flight_id = :fid AND class_id = :cid
                """), {"fid": flight_id, "cid": class_id}).fetchone()

                if not exists:
                    conn.execute(text("""
                        INSERT INTO FlightClass (flight_id, class_id)
                        VALUES (:fid, :cid)
                    """), {"fid": flight_id, "cid": class_id})
                    inserted += 1

        logger.info("FlightClass records inserted: %d", inserted)

        