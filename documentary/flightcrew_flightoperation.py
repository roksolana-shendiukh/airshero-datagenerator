import logging
from datetime import datetime
from sqlalchemy import text

logger = logging.getLogger(__name__)

BATCH_SIZE = 5_000


def generate_flight_crew_operations(engine):
    now = datetime.utcnow()

    with engine.begin() as conn:
        records = conn.execute(text("""
            SELECT fo.flight_operation_id, ffc.flight_crew_id
            FROM FlightOperation fo
            JOIN ScheduledFlight sf ON sf.schedule_flight_id = fo.schedule_flight_id
            JOIN FlightFlightCrew ffc ON ffc.flight_id = sf.flight_id
            WHERE ffc.is_active = 1
        """)).fetchall()

        logger.info("Records to insert: %d", len(records))

        batch    = []
        inserted = 0

        for fo_id, crew_id in records:
            batch.append({
                "flight_operation_id": fo_id,
                "flight_crew_id":      crew_id
            })

            if len(batch) >= BATCH_SIZE:
                conn.execute(text("""
                    INSERT INTO FlightCrewFlightOperation (flight_operation_id, flight_crew_id)
                    VALUES (:flight_operation_id, :flight_crew_id)
                """), batch)
                inserted += len(batch)
                batch.clear()

        if batch:
            conn.execute(text("""
                INSERT INTO FlightCrewFlightOperation (flight_operation_id, flight_crew_id)
                VALUES (:flight_operation_id, :flight_crew_id)
            """), batch)
            inserted += len(batch)

        logger.info("FlightCrewFlightOperation inserted: %d", inserted)

        