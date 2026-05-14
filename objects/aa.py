import random
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

SHORT_RANGE = 7000
LONG_RANGE  = 12000


def generate_airline_airfleet(engine):
    with engine.begin() as conn:
        existing_pairs = set(
            (row[0], row[1])
            for row in conn.execute(text("SELECT airline_id, airfleet_id FROM AirlineAirfleet"))
        )

        airfleets = [dict(row._mapping) for row in conn.execute(text(
            "SELECT airfleet_id, aircraft_range_km FROM Airfleet"
        ))]

        short_haul  = [af for af in airfleets if af["aircraft_range_km"] <= SHORT_RANGE]
        medium_haul = [af for af in airfleets if SHORT_RANGE < af["aircraft_range_km"] <= LONG_RANGE]
        long_haul   = [af for af in airfleets if af["aircraft_range_km"] > LONG_RANGE]

        logger.info("Short haul aircraft: %d", len(short_haul))
        logger.info("Medium haul aircraft: %d", len(medium_haul))
        logger.info("Long haul aircraft: %d", len(long_haul))

        airline_ranges = [dict(row._mapping) for row in conn.execute(text("""
            SELECT f.airline_id, MIN(r.flight_range) AS min_range, MAX(r.flight_range) AS max_range
            FROM Flight f
            JOIN Route r ON f.route_id = r.route_id
            GROUP BY f.airline_id
        """))]

        new_pairs = []

        for ar in airline_ranges:
            airline_id = ar["airline_id"]
            min_range  = float(ar["min_range"])
            max_range  = float(ar["max_range"])

            candidates = []

            if short_haul and min_range <= SHORT_RANGE and random.random() < 0.95:
                candidates += random.sample(short_haul, min(random.randint(1, 2), len(short_haul)))

            if medium_haul and random.random() < 0.85:
                candidates += random.sample(medium_haul, min(random.randint(1, 2), len(medium_haul)))

            if long_haul and max_range > LONG_RANGE and random.random() < 0.75:
                candidates += random.sample(long_haul, min(random.randint(1, 2), len(long_haul)))

            for af in candidates:
                pair = (airline_id, af["airfleet_id"])
                if pair not in existing_pairs:
                    new_pairs.append({
                        "airline_id":  airline_id,
                        "airfleet_id": af["airfleet_id"]
                    })
                    existing_pairs.add(pair)

        logger.info("New pairs to insert: %d", len(new_pairs))

        if new_pairs:
            conn.execute(text("""
                INSERT INTO AirlineAirfleet (airline_id, airfleet_id)
                VALUES (:airline_id, :airfleet_id)
            """), new_pairs)

        logger.info("Total AirlineAirfleet pairs: %d", len(existing_pairs))

