import random
import string
import logging
from collections import defaultdict
from sqlalchemy import text

logger = logging.getLogger(__name__)

BATCH_SIZE = 5_000

OVERWEIGHT_RATE_BY_TYPE = {
    "Carry-on baggage":  0.15,
    "Checked baggage":   0.08,
    "Oversized baggage": 0.12,
    "Fragile baggage":   0.05,
    "Sports equipment":  0.10,
    "Special baggage":   0.07,
}

_existing_tracking = set()


def _generate_tracking_number():
    while True:
        num = "BG" + "".join(random.choices(string.digits, k=10))
        if num not in _existing_tracking:
            _existing_tracking.add(num)
            return num


def generate_baggage_units(engine):
    with engine.begin() as conn:
        baggage_type_names = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT baggage_type_id, baggage_type_name FROM BaggageType"))
        }

        pricing_rules = [dict(r._mapping) for r in conn.execute(text("""
            SELECT baggage_pricing_rule_id, baggage_type_id, baggage_dimension, baggage_max_weight
            FROM BaggagePricingRule
        """)).fetchall()]
        rules_by_type = defaultdict(list)
        for r in pricing_rules:
            rules_by_type[r["baggage_type_id"]].append(r)

        payment_methods = {
            name: mid
            for mid, name in conn.execute(text("SELECT payment_method_id, payment_method_name FROM PaymentMethod"))
        }
        payment_statuses = {
            name: sid
            for sid, name in conn.execute(text("SELECT payment_status_id, payment_status_name FROM PaymentStatus"))
        }

        card_id        = payment_methods["Card"]
        cash_id        = payment_methods["Cash"]
        paid_status_id = payment_statuses["Paid"]

        options = [dict(r._mapping) for r in conn.execute(text("""
            SELECT
                boif.booking_item_id,
                boif.baggage_quantity,
                bpif.baggage_pricing_in_flight_id,
                bpr.baggage_type_id,
                bpr.baggage_max_weight
            FROM BaggageOptionInFlight boif
            JOIN BaggagePricingInFlight bpif ON bpif.baggage_pricing_in_flight_id = boif.baggage_pricing_in_flight_id
            JOIN BaggagePricingRule bpr      ON bpr.baggage_pricing_rule_id = bpif.baggage_pricing_rule_id
        """)).fetchall()]
        logger.info("BaggageOptionInFlight loaded: %d", len(options))

        bp_by_booking_item = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT booking_item_id, boarding_pass_id FROM BoardingPass"))
        }
        logger.info("BoardingPass loaded: %d", len(bp_by_booking_item))

        baggage_batch    = []
        overweight_batch = []
        baggage_inserted = 0
        skipped_no_bp    = 0
        stats            = defaultdict(int)

        for opt_idx, opt in enumerate(options):
            if (opt_idx + 1) % 50_000 == 0:
                logger.info("Progress: %d/%d options | Units: %d", opt_idx + 1, len(options), baggage_inserted)

            booking_item_id  = opt["booking_item_id"]
            baggage_type_id  = opt["baggage_type_id"]
            baggage_quantity = opt["baggage_quantity"]
            max_weight       = float(opt["baggage_max_weight"])

            boarding_pass_id = bp_by_booking_item.get(booking_item_id)
            if boarding_pass_id is None:
                skipped_no_bp += baggage_quantity
                continue

            type_name       = baggage_type_names.get(baggage_type_id, "")
            overweight_rate = OVERWEIGHT_RATE_BY_TYPE.get(type_name, 0.08)
            dimensions      = [r["baggage_dimension"] for r in rules_by_type.get(baggage_type_id, [])]

            for _ in range(baggage_quantity):
                tracking      = _generate_tracking_number()
                dimension     = random.choice(dimensions) if dimensions else "60x40x30"
                is_overweight = random.random() < overweight_rate
                unit_weight   = round(
                    random.uniform(max_weight, max_weight * 1.3) if is_overweight
                    else random.uniform(0.5, max_weight), 2
                )

                baggage_batch.append({
                    "boarding_pass_id":             boarding_pass_id,
                    "baggage_type_id":              baggage_type_id,
                    "baggage_unit_tracking_number": tracking,
                    "baggage_unit_weight_kg":       unit_weight,
                    "baggage_unit_dimensions":      dimension,
                })
                stats["total"] += 1
                if is_overweight:
                    stats["overweight"] += 1
                    overweight_batch.append({
                        "tracking":      tracking,
                        "overweight_kg": round(unit_weight - max_weight, 2)
                    })

                if len(baggage_batch) >= BATCH_SIZE:
                    conn.execute(text("""
                        INSERT INTO BaggageUnit (
                            boarding_pass_id, baggage_type_id, baggage_unit_tracking_number,
                            baggage_unit_weight_kg, baggage_unit_dimensions
                        ) VALUES (
                            :boarding_pass_id, :baggage_type_id, :baggage_unit_tracking_number,
                            :baggage_unit_weight_kg, :baggage_unit_dimensions
                        )
                    """), baggage_batch)
                    baggage_inserted += len(baggage_batch)
                    baggage_batch.clear()

        if baggage_batch:
            conn.execute(text("""
                INSERT INTO BaggageUnit (
                    boarding_pass_id, baggage_type_id, baggage_unit_tracking_number,
                    baggage_unit_weight_kg, baggage_unit_dimensions
                ) VALUES (
                    :boarding_pass_id, :baggage_type_id, :baggage_unit_tracking_number,
                    :baggage_unit_weight_kg, :baggage_unit_dimensions
                )
            """), baggage_batch)
            baggage_inserted += len(baggage_batch)

        logger.info("BaggageUnit inserted: %d, skipped: %d, overweight: %d",
                    baggage_inserted, skipped_no_bp, stats["overweight"])

        logger.info("Processing overweight payments: %d", len(overweight_batch))

        payment_inserted = 0
        linking_inserted = 0
        linking_batch    = []

        for i in range(0, len(overweight_batch), BATCH_SIZE):
            chunk     = overweight_batch[i:i + BATCH_SIZE]
            trackings = [p["tracking"] for p in chunk]

            placeholders = ",".join([f"'{t}'" for t in trackings])
            baggage_ids  = {
                row[0]: row[1]
                for row in conn.execute(text(f"""
                    SELECT baggage_unit_tracking_number, baggage_unit_id
                    FROM BaggageUnit
                    WHERE baggage_unit_tracking_number IN ({placeholders})
                """)).fetchall()
            }

            for p in chunk:
                bu_id = baggage_ids.get(p["tracking"])
                if not bu_id:
                    continue

                overweight_fee = round(p["overweight_kg"] * random.uniform(5, 15), 2)
                method_id      = random.choices([card_id, cash_id], weights=[0.65, 0.35])[0]

                checkin_payment_id = conn.execute(text("""
                    INSERT INTO CheckinInPayment (
                        payment_status_id, payment_method_id,
                        checkin_payment_date_time, checkin_payment_amount
                    )
                    OUTPUT INSERTED.checkin_payment_id
                    VALUES (:status_id, :method_id, GETDATE(), :amount)
                """), {
                    "status_id": paid_status_id,
                    "method_id": method_id,
                    "amount":    overweight_fee,
                }).scalar_one()

                payment_inserted += 1
                linking_batch.append({
                    "baggage_unit_id":    bu_id,
                    "checkin_payment_id": checkin_payment_id,
                })

                if len(linking_batch) >= BATCH_SIZE:
                    conn.execute(text("""
                        INSERT INTO BaggageUnitCheckInPayment (baggage_unit_id, checkin_payment_id)
                        VALUES (:baggage_unit_id, :checkin_payment_id)
                    """), linking_batch)
                    linking_inserted += len(linking_batch)
                    linking_batch.clear()

            logger.info("Overweight processed: %d/%d | Payments: %d",
                        min(i + BATCH_SIZE, len(overweight_batch)), len(overweight_batch), payment_inserted)

        if linking_batch:
            conn.execute(text("""
                INSERT INTO BaggageUnitCheckInPayment (baggage_unit_id, checkin_payment_id)
                VALUES (:baggage_unit_id, :checkin_payment_id)
            """), linking_batch)
            linking_inserted += len(linking_batch)

    logger.info("CheckinInPayment inserted:          %d", payment_inserted)
    logger.info("BaggageUnitCheckInPayment inserted: %d", linking_inserted)