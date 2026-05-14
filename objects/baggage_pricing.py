import random
import logging
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import text

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000

BASE_PRICES = {
    "Checked baggage":   Decimal("25.00"),
    "Oversized baggage": Decimal("60.00"),
    "Fragile baggage":   Decimal("40.00"),
    "Sports equipment":  Decimal("75.00"),
    "Special baggage":   Decimal("50.00"),
}

CLASS_MULTIPLIER = {
    "Economy":         (0.95, 1.05),
    "Premium Economy": (1.2,  1.4),
    "Business":        (1.5,  1.8),
    "First":           (1.8,  2.5),
}

FREE_CHECKED_CHANCE = {
    "short":  0.30,
    "medium": 0.60,
    "long":   0.90,
}


def _range_category(flight_range):
    if flight_range < 2000:  return "short"
    if flight_range <= 5000: return "medium"
    return "long"


def _apply_multiplier(base_price, class_name):
    low, high = CLASS_MULTIPLIER[class_name]
    factor = Decimal(str(round(random.uniform(low, high), 2)))
    return (base_price * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _flush(conn, batch):
    if not batch:
        return
    conn.execute(text("""
        INSERT INTO BaggagePricingInFlight (baggage_pricing_rule_id, flight_class_id, baggage_price)
        VALUES (:rule_id, :fc_id, :price)
    """), batch)
    batch.clear()


def generate_baggage_pricing(engine):
    total_inserted = 0

    with engine.begin() as conn:
        classes = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT class_id, class_name FROM Class"))
        }

        baggage_types = {
            row[1]: row[0]
            for row in conn.execute(text("SELECT baggage_type_id, baggage_type_name FROM BaggageType"))
        }

        rules = conn.execute(text("""
            SELECT baggage_pricing_rule_id, baggage_type_id, baggage_max_weight
            FROM BaggagePricingRule
        """)).fetchall()

        rules_by_type = {}
        for r_id, r_type, max_w in rules:
            rules_by_type.setdefault(r_type, []).append((r_id, max_w))

        flight_classes = conn.execute(text("""
            SELECT fc.flight_class_id, fc.class_id, r.flight_range
            FROM FlightClass fc
            JOIN Flight f ON f.flight_id = fc.flight_id
            JOIN Route r ON r.route_id = f.route_id
        """)).fetchall()

        checked_type_id     = baggage_types.get("Checked baggage")
        chargeable_type_ids = {tid for tname, tid in baggage_types.items() if tname in BASE_PRICES}

        batch = []

        for fc_id, class_id, flight_range in flight_classes:
            class_name     = classes.get(class_id)
            if not class_name or class_name not in CLASS_MULTIPLIER:
                continue

            range_category      = _range_category(float(flight_range))
            available_type_ids  = list(chargeable_type_ids & rules_by_type.keys())
            random.shuffle(available_type_ids)
            first_checked_done  = False

            for t_id in available_type_ids:
                rule_id, max_w = sorted(rules_by_type[t_id], key=lambda x: x[1])[0]

                type_name = next((n for n, i in baggage_types.items() if i == t_id), None)
                if not type_name or type_name not in BASE_PRICES:
                    continue

                if (
                    t_id == checked_type_id
                    and not first_checked_done
                    and class_name in ("Business", "First")
                    and random.random() < FREE_CHECKED_CHANCE[range_category]
                ):
                    price = Decimal("0.00")
                    first_checked_done = True
                else:
                    price = _apply_multiplier(BASE_PRICES[type_name], class_name)

                batch.append({
                    "rule_id": rule_id,
                    "fc_id":   fc_id,
                    "price":   float(price)
                })
                total_inserted += 1

                if len(batch) >= BATCH_SIZE:
                    _flush(conn, batch)

        _flush(conn, batch)

    logger.info("BaggagePricingInFlight records inserted: %d", total_inserted)

    