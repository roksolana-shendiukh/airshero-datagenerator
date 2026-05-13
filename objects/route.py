import json
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def insert_routes(engine, json_path="files/route.json"):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    inserted_routes = 0

    with engine.begin() as conn:
        for route in data["routes"]:
            departs_airport_id = conn.execute(
                text("SELECT TOP 1 airport_id FROM Airport WHERE airport_code = :code"),
                {"code": route["departs_airport_code"]}
            ).scalar_one_or_none()
            if not departs_airport_id:
                logger.warning("Departure airport not found: %s", route["departs_airport_code"])
                continue

            arrives_airport_id = conn.execute(
                text("SELECT TOP 1 airport_id FROM Airport WHERE airport_code = :code"),
                {"code": route["arrives_airport_code"]}
            ).scalar_one_or_none()
            if not arrives_airport_id:
                logger.warning("Arrival airport not found: %s", route["arrives_airport_code"])
                continue

            exists = conn.execute(
                text("""
                    SELECT 1 FROM Route
                    WHERE departs_airport_id = :departs_airport_id
                      AND arrives_airport_id = :arrives_airport_id
                """),
                {
                    "departs_airport_id": departs_airport_id,
                    "arrives_airport_id": arrives_airport_id
                }
            ).fetchone()
            if exists:
                continue

            conn.execute(text("""
                INSERT INTO Route (departs_airport_id, arrives_airport_id, flight_range)
                VALUES (:departs_airport_id, :arrives_airport_id, :flight_range)
            """), {
                "departs_airport_id": departs_airport_id,
                "arrives_airport_id": arrives_airport_id,
                "flight_range":       route["flight_range"]
            })
            inserted_routes += 1

    logger.info("Routes inserted: %d", inserted_routes)


    