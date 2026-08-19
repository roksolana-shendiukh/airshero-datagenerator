import logging
import random
import string

from sqlalchemy import text

logger = logging.getLogger(__name__)

MIN_AIRCRAFT_PER_AIRLINE = 2
MAX_AIRCRAFT_PER_AIRLINE = 5

FALLBACK_MIN_AIRCRAFT = 3
FALLBACK_MAX_AIRCRAFT = 5

RANGE_KM_VARIATION = 0.08  

HANGAR_PROBABILITY = 0.15

HEX_DIGITS = string.hexdigits[:16].upper()


def _generate_icao24(existing_codes):
    """Генерує унікальний 24-бітний ICAO hex-код (6 hex-символів), якого ще нема в existing_codes."""
    while True:
        code = "".join(random.choice(HEX_DIGITS) for _ in range(6))
        if code not in existing_codes:
            existing_codes.add(code)
            return code


def generate_aircraft(engine):
    with engine.begin() as conn:
        airfleets = conn.execute(
            text("SELECT airfleet_id, aircraft_range_km FROM Airfleet")
        ).mappings().all()

        if not airfleets:
            logger.warning("No Airfleet rows found — cannot generate Aircraft")
            return

        existing_codes = set(
            conn.execute(text("SELECT icao24 FROM Aircraft")).scalars().all()
        )

        airlines_per_airfleet = dict(conn.execute(text("""
            SELECT airfleet_id, COUNT(DISTINCT airline_id) AS airline_count
            FROM AirlineAirfleet
            GROUP BY airfleet_id
        """)).all())

        inserted_aircraft = 0

        for airfleet in airfleets:
            airfleet_id = airfleet["airfleet_id"]
            base_range_km = airfleet["aircraft_range_km"]

            airline_count = airlines_per_airfleet.get(airfleet_id, 0)

            if airline_count > 0:
                aircraft_count = sum(
                    random.randint(MIN_AIRCRAFT_PER_AIRLINE, MAX_AIRCRAFT_PER_AIRLINE)
                    for _ in range(airline_count)
                )
            else:
                aircraft_count = random.randint(FALLBACK_MIN_AIRCRAFT, FALLBACK_MAX_AIRCRAFT)

            for _ in range(aircraft_count):
                icao24 = _generate_icao24(existing_codes)

                variation = random.uniform(-RANGE_KM_VARIATION, RANGE_KM_VARIATION)
                aircraft_range_km = round(base_range_km * (1 + variation), 2)

                is_in_hangar = random.random() < HANGAR_PROBABILITY

                result = conn.execute(text("""
                    INSERT INTO Aircraft (airfleet_id, icao24, aircraft_range_km, is_in_hangar)
                    SELECT :airfleet_id, :icao24, :aircraft_range_km, :is_in_hangar
                    WHERE NOT EXISTS (SELECT 1 FROM Aircraft WHERE icao24 = :icao24)
                """), {
                    "airfleet_id":       airfleet_id,
                    "icao24":            icao24,
                    "aircraft_range_km": aircraft_range_km,
                    "is_in_hangar":      is_in_hangar
                })
                if result.rowcount > 0:
                    inserted_aircraft += 1

    logger.info("Inserted — Aircraft: %d", inserted_aircraft)