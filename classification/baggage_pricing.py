import json
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def insert_baggage_pricing_rules(engine, json_path="files/baggage_pricing.json"):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total_inserted = 0

    with engine.begin() as conn:
        for btype_name, params in data["baggageTypes"].items():
            baggage_type_id = conn.execute(
                text("SELECT baggage_type_id FROM BaggageType WHERE baggage_type_name = :name"),
                {"name": btype_name}
            ).scalar_one_or_none()

            if not baggage_type_id:
                logger.warning("BaggageType not found: %s", btype_name)
                continue

            for dim in params["dims"]:
                conn.execute(text("""
                    INSERT INTO BaggagePricingRule (baggage_type_id, baggage_dimension, baggage_max_weight)
                    VALUES (:bt_id, :dim, :max_w)
                """), {
                    "bt_id": baggage_type_id,
                    "dim":   dim,
                    "max_w": params["max_w"]
                })
                total_inserted += 1

        sports_type_id = conn.execute(
            text("SELECT baggage_type_id FROM BaggageType WHERE baggage_type_name = :name"),
            {"name": "Sports equipment"}
        ).scalar_one_or_none()

        if not sports_type_id:
            logger.warning("BaggageType not found: Sports equipment")
        else:
            for subtype, params in data["sportsSubtypes"].items():
                conn.execute(text("""
                    INSERT INTO BaggagePricingRule (baggage_type_id, baggage_dimension, baggage_max_weight)
                    VALUES (:bt_id, :dim, :max_w)
                """), {
                    "bt_id": baggage_type_id,
                    "dim":   dim,
                    "max_w": params["max_w"]
                })
                total_inserted += 1

    logger.info("Inserted %d BaggagePricingRule records", total_inserted)

    