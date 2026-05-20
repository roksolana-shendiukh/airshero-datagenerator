import random
import logging
from collections import defaultdict
from datetime import date
from sqlalchemy import text

logger = logging.getLogger(__name__)

BATCH_SIZE = 10_000

ALLOWED_BAGGAGE_NAMES = {
    "Economy":         ["Checked baggage", "Oversized baggage", "Fragile baggage", "Sports equipment", "Special baggage"],
    "Premium Economy": ["Checked baggage", "Oversized baggage", "Fragile baggage", "Sports equipment", "Special baggage"],
    "Business":        ["Oversized baggage", "Fragile baggage", "Sports equipment", "Special baggage"],
    "First":           ["Oversized baggage", "Fragile baggage", "Sports equipment", "Special baggage"],
}

BAGGAGE_CHANCE_ADULT = {
    "Economy":         {"regional": (0.25, 0.35), "international": (0.75, 0.85)},
    "Premium Economy": {"regional": (0.20, 0.30), "international": (0.60, 0.70)},
    "Business":        {"regional": (0.10, 0.20), "international": (0.15, 0.25)},
    "First":           {"regional": (0.08, 0.15), "international": (0.10, 0.20)},
}

BAGGAGE_CHANCE_CHILD = {
    "Economy":         {"regional": (0.10, 0.20), "international": (0.20, 0.30)},
    "Premium Economy": {"regional": (0.10, 0.20), "international": (0.20, 0.30)},
    "Business":        {"regional": (0.05, 0.10), "international": (0.10, 0.15)},
    "First":           {"regional": (0.05, 0.10), "international": (0.10, 0.15)},
}

QUANTITY_BY_CLASS = {
    "Economy":         (1, 2),
    "Premium Economy": (1, 3),
    "Business":        (1, 2),
    "First":           (1, 2),
}

EXTRA_BAGGAGE_CHANCE = 0.25


def _calc_age(dob, today):
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def generate_baggage_options(engine):
    today = date.today()

    with engine.begin() as conn:
        logger.info("Loading data...")

        baggage_type_ids = {
            name: tid
            for tid, name in conn.execute(text("SELECT baggage_type_id, baggage_type_name FROM BaggageType"))
        }

        allowed_baggage_ids = {
            class_name: [baggage_type_ids[name] for name in names if name in baggage_type_ids]
            for class_name, names in ALLOWED_BAGGAGE_NAMES.items()
        }

        booking_items = [dict(r._mapping) for r in conn.execute(text("""
            SELECT
                bi.booking_item_id,
                fp.flight_class_id,
                c.class_name,
                dco.country_id AS dep_country_id,
                aco.country_id AS arr_country_id,
                p.passenger_date_of_birth
            FROM BookingItem bi
            JOIN FlightPrice fp       ON bi.flight_price_id = fp.flight_price_id
            JOIN FlightClass fc       ON fp.flight_class_id = fc.flight_class_id
            JOIN Class c              ON fc.class_id = c.class_id
            JOIN Flight f             ON fc.flight_id = f.flight_id
            JOIN Route r              ON r.route_id = f.route_id
            JOIN Airport da           ON da.airport_id = r.departs_airport_id
            JOIN Airport aa           ON aa.airport_id = r.arrives_airport_id
            JOIN City dco             ON dco.city_id = da.city_id
            JOIN City aco             ON aco.city_id = aa.city_id
            JOIN PassengerDocument pd ON pd.passenger_document_id = bi.passenger_document_id
            JOIN Passenger p          ON p.passenger_id = pd.passenger_id
        """)).fetchall()]
        logger.info("BookingItems loaded: %d", len(booking_items))

        rules = [dict(r._mapping) for r in conn.execute(text("""
            SELECT bpi.baggage_pricing_in_flight_id, bpi.flight_class_id,
                   bpr.baggage_type_id, bpr.baggage_max_weight
            FROM BaggagePricingInFlight bpi
            JOIN BaggagePricingRule bpr ON bpr.baggage_pricing_rule_id = bpi.baggage_pricing_rule_id
        """)).fetchall()]
        logger.info("Rules loaded: %d", len(rules))

        rules_by_flight_class = defaultdict(list)
        for r in rules:
            rules_by_flight_class[r["flight_class_id"]].append(r)

        batch             = []
        inserted          = 0
        skipped_infant    = 0
        skipped_no_chance = 0
        skipped_no_rules  = 0

        for bi in booking_items:
            age = _calc_age(bi["passenger_date_of_birth"], today)

            if age < 2:
                skipped_infant += 1
                continue

            flight_type  = "regional" if bi["dep_country_id"] == bi["arr_country_id"] else "international"
            class_name   = bi["class_name"]
            chance_table = BAGGAGE_CHANCE_CHILD if age < 12 else BAGGAGE_CHANCE_ADULT
            chance_range = chance_table.get(
                class_name, {"regional": (0.25, 0.35), "international": (0.75, 0.85)}
            )[flight_type]

            if random.random() > random.uniform(float(chance_range[0]), float(chance_range[1])):
                skipped_no_chance += 1
                continue

            allowed_types   = allowed_baggage_ids.get(class_name, list(baggage_type_ids.values()))
            available_rules = [
                r for r in rules_by_flight_class.get(bi["flight_class_id"], [])
                if r["baggage_type_id"] in allowed_types
            ]

            if not available_rules:
                skipped_no_rules += 1
                continue

            shuffled = available_rules.copy()
            random.shuffle(shuffled)

            rules_by_type = {}
            for r in shuffled:
                bt = r["baggage_type_id"]
                if bt not in rules_by_type:
                    rules_by_type[bt] = r

            unique_rules = list(rules_by_type.values())

            if flight_type == "international":
                weights     = [float(r["baggage_max_weight"]) for r in unique_rules]
                total       = sum(weights)
                first_rule  = random.choices(unique_rules, weights=[w / total for w in weights], k=1)[0]
            else:
                first_rule = (
                    min(unique_rules, key=lambda r: r["baggage_max_weight"])
                    if random.random() < 0.7
                    else random.choice(unique_rules)
                )

            min_q, max_q = QUANTITY_BY_CLASS.get(class_name, (1, 2))

            batch.append({
                "booking_item_id":              bi["booking_item_id"],
                "baggage_pricing_in_flight_id": first_rule["baggage_pricing_in_flight_id"],
                "baggage_quantity":             random.randint(min_q, max_q),
            })

            remaining_rules = [r for r in unique_rules if r["baggage_type_id"] != first_rule["baggage_type_id"]]
            for extra_rule in remaining_rules:
                if random.random() > EXTRA_BAGGAGE_CHANCE:
                    continue
                batch.append({
                    "booking_item_id":              bi["booking_item_id"],
                    "baggage_pricing_in_flight_id": extra_rule["baggage_pricing_in_flight_id"],
                    "baggage_quantity":             random.randint(min_q, max_q),
                })

            if len(batch) >= BATCH_SIZE:
                conn.execute(text("""
                    INSERT INTO BaggageOptionInFlight
                        (booking_item_id, baggage_pricing_in_flight_id, baggage_quantity)
                    VALUES
                        (:booking_item_id, :baggage_pricing_in_flight_id, :baggage_quantity)
                """), batch)
                inserted += len(batch)
                logger.info("Inserted: %d", inserted)
                batch.clear()

        if batch:
            conn.execute(text("""
                INSERT INTO BaggageOptionInFlight
                    (booking_item_id, baggage_pricing_in_flight_id, baggage_quantity)
                VALUES
                    (:booking_item_id, :baggage_pricing_in_flight_id, :baggage_quantity)
            """), batch)
            inserted += len(batch)

    logger.info("BaggageOptionInFlight inserted: %d", inserted)
    logger.info("Skipped — infants: %d, no chance: %d, no rules: %d",
                skipped_infant, skipped_no_chance, skipped_no_rules)
    
