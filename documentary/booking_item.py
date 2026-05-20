import random
import logging
from collections import defaultdict
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from sqlalchemy import text

logger = logging.getLogger(__name__)

BATCH_SIZE = 10_000


def generate_booking_items(engine):
    with engine.begin() as conn:
        logger.info("Loading data...")

        doc_type_map = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT document_type_id, document_type_code FROM DocumentType"))
        }

        REGIONAL_CODES      = {"ID", "PAS"}
        INTERNATIONAL_CODES = {"INT", "OFF"}

        regional_type_ids      = {tid for tid, code in doc_type_map.items() if code in REGIONAL_CODES}
        international_type_ids = {tid for tid, code in doc_type_map.items() if code in INTERNATIONAL_CODES}

        flight_statuses = {
            name: sid
            for sid, name in conn.execute(text("SELECT flight_status_id, flight_status_name FROM FlightStatus"))
        }
        cancelled_status = flight_statuses["Cancelled"]

        passengers_docs = [dict(r._mapping) for r in conn.execute(text("""
            SELECT p.passenger_id, p.passenger_date_of_birth,
                   pd.passenger_document_id, pd.document_type_id,
                   pd.document_date_of_expire, pd.document_date_of_issue
            FROM Passenger p
            JOIN PassengerDocument pd ON pd.passenger_id = p.passenger_id
        """))]

        bookings = [row[0] for row in conn.execute(text("SELECT booking_id FROM Booking"))]

        flight_prices = [dict(r._mapping) for r in conn.execute(text("""
            SELECT
                fp.flight_price_id,
                fp.flight_class_id,
                fp.schedule_flight_id,
                fp.ticket_price,
                fc.flight_id,
                fc.class_id,
                sf.departs_date,
                sf.flight_status_id,
                dep_city.country_id AS dep_country_id,
                arr_city.country_id AS arr_country_id,
                COUNT(sl.seat_layout_id) AS physical_seats
            FROM FlightPrice fp
            JOIN FlightClass fc     ON fc.flight_class_id = fp.flight_class_id
            JOIN ScheduledFlight sf ON sf.schedule_flight_id = fp.schedule_flight_id
            JOIN Flight f           ON f.flight_id = fc.flight_id
            JOIN Route r            ON r.route_id = f.route_id
            JOIN Airfleet a         ON a.airfleet_id = f.airfleet_id
            JOIN Airport dep_air    ON dep_air.airport_id = r.departs_airport_id
            JOIN Airport arr_air    ON arr_air.airport_id = r.arrives_airport_id
            JOIN City dep_city      ON dep_city.city_id = dep_air.city_id
            JOIN City arr_city      ON arr_city.city_id = arr_air.city_id
            JOIN SeatLayout sl      ON sl.airfleet_id = a.airfleet_id AND sl.class_id = fc.class_id
            GROUP BY fp.flight_price_id, fp.flight_class_id, fp.schedule_flight_id, fp.ticket_price,
                     fc.flight_id, fc.class_id, sf.departs_date, sf.flight_status_id,
                     dep_city.country_id, arr_city.country_id
        """))]

        logger.info("Passengers docs: %d", len(passengers_docs))
        logger.info("Bookings:        %d", len(bookings))
        logger.info("FlightPrices:    %d", len(flight_prices))

        today = date.today()

        def calc_age(dob):
            return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

        def validity_years(doc_code, age):
            if doc_code == "OFF": return 5
            return 4 if age < 16 else 10

        def validate_or_fix_doc(doc, flight_date, age):
            min_expire = flight_date + relativedelta(months=2)
            expire     = doc["document_date_of_expire"]
            if isinstance(expire, date) and expire >= min_expire:
                return doc, False
            doc_code   = doc_type_map.get(doc["document_type_id"], "INT")
            new_expire = min_expire
            new_issue  = new_expire - relativedelta(years=validity_years(doc_code, age))
            updated    = dict(doc)
            updated["document_date_of_expire"] = new_expire
            updated["document_date_of_issue"]  = new_issue
            return updated, True

        docs_by_passenger = defaultdict(list)
        age_by_passenger  = {}
        adults   = []
        children = []

        for pd in passengers_docs:
            age = calc_age(pd["passenger_date_of_birth"])
            age_by_passenger[pd["passenger_id"]] = age
            docs_by_passenger[pd["passenger_id"]].append(pd)
            if age >= 12:
                adults.append(pd["passenger_id"])
            else:
                children.append(pd["passenger_id"])

        adults   = list(set(adults))
        children = list(set(children))
        logger.info("Adults: %d, Children: %d", len(adults), len(children))

        max_sellable = {}
        for fp in flight_prices:
            key = (fp["schedule_flight_id"], fp["class_id"])
            if fp["flight_status_id"] == cancelled_status:
                usage = random.uniform(0.05, 0.15)
            else:
                usage = random.uniform(0.60, 0.85)
            max_sellable[key] = int(fp["physical_seats"] * usage)

        sold_per_key = defaultdict(int)

        regional_prices      = [fp for fp in flight_prices if fp["dep_country_id"] == fp["arr_country_id"]]
        international_prices = [fp for fp in flight_prices if fp["dep_country_id"] != fp["arr_country_id"]]

        logger.info("Regional FlightPrices:      %d", len(regional_prices))
        logger.info("International FlightPrices: %d", len(international_prices))

        def has_seats(fp):
            key = (fp["schedule_flight_id"], fp["class_id"])
            return sold_per_key[key] < max_sellable.get(key, 0)

        def pick_flight_price(candidates):
            shuffled = random.sample(candidates, min(50, len(candidates)))
            for fp in shuffled:
                if has_seats(fp):
                    return fp
            return None

        booking_batch    = []
        doc_update_batch = []
        inserted = 0
        skipped  = 0

        logger.info("Generating BookingItems...")

        for booking_idx, booking_id in enumerate(bookings):
            if (booking_idx + 1) % 10_000 == 0:
                logger.info("Progress: %d/%d | Inserted: %d", booking_idx + 1, len(bookings), inserted)

            rand = random.random()
            if rand < 0.71:
                group_size = 1
            elif rand < 0.996:
                group_size = random.randint(2, 4)
            else:
                group_size = random.randint(5, 6)

            group     = [random.choice(adults)]
            remaining = group_size - 1

            if remaining > 0:
                if random.random() < 0.4 and children:
                    num_children = random.randint(1, min(remaining, len(children)))
                    num_adults   = remaining - num_children
                else:
                    num_children = 0
                    num_adults   = remaining

                extra_adults = [p for p in random.sample(adults, min(num_adults + 5, len(adults))) if p != group[0]]
                group.extend(extra_adults[:num_adults])
                if num_children > 0:
                    group.extend(random.sample(children, min(num_children, len(children))))

            first_docs = docs_by_passenger[group[0]]
            if not first_docs:
                skipped += 1
                continue

            has_regional      = any(d["document_type_id"] in regional_type_ids      for d in first_docs)
            has_international = any(d["document_type_id"] in international_type_ids for d in first_docs)

            if has_international and has_regional:
                use_regional = random.random() < 0.43
            elif has_regional:
                use_regional = True
            else:
                use_regional = False

            candidates = regional_prices if use_regional else international_prices
            if not candidates:
                candidates = regional_prices if not use_regional else international_prices

            fp = pick_flight_price(candidates)
            if fp is None:
                skipped += 1
                continue

            key             = (fp["schedule_flight_id"], fp["class_id"])
            available_seats = max_sellable.get(key, 0) - sold_per_key[key]
            group           = group[:available_seats]

            if not group:
                skipped += 1
                continue

            is_regional = fp["dep_country_id"] == fp["arr_country_id"]
            flight_date = fp["departs_date"]

            for pid in group:
                docs = docs_by_passenger[pid]
                if not docs:
                    skipped += 1
                    continue

                regional_docs      = [d for d in docs if d["document_type_id"] in regional_type_ids]
                international_docs = [d for d in docs if d["document_type_id"] in international_type_ids]

                if is_regional and regional_docs:
                    doc = random.choice(regional_docs)
                elif not is_regional and international_docs:
                    doc = random.choice(international_docs)
                elif regional_docs:
                    doc = random.choice(regional_docs)
                elif international_docs:
                    doc = random.choice(international_docs)
                else:
                    skipped += 1
                    continue

                age          = age_by_passenger.get(pid, 30)
                doc, updated = validate_or_fix_doc(doc, flight_date, age)

                if updated:
                    doc_update_batch.append({
                        "doc_id":     doc["passenger_document_id"],
                        "new_expire": doc["document_date_of_expire"],
                        "new_issue":  doc["document_date_of_issue"],
                        "updated_at": datetime.utcnow(),
                    })

                booking_batch.append({
                    "booking_id":            booking_id,
                    "passenger_document_id": doc["passenger_document_id"],
                    "flight_price_id":       fp["flight_price_id"],
                })
                sold_per_key[key] += 1

            if doc_update_batch:
                conn.execute(text("""
                    UPDATE PassengerDocument
                    SET document_date_of_expire = :new_expire,
                        document_date_of_issue  = :new_issue,
                        updated_at              = :updated_at
                    WHERE passenger_document_id = :doc_id
                """), doc_update_batch)
                doc_update_batch.clear()

            if len(booking_batch) >= BATCH_SIZE:
                conn.execute(text("""
                    INSERT INTO BookingItem (booking_id, passenger_document_id, flight_price_id)
                    VALUES (:booking_id, :passenger_document_id, :flight_price_id)
                """), booking_batch)
                inserted += len(booking_batch)
                booking_batch.clear()

        if doc_update_batch:
            conn.execute(text("""
                UPDATE PassengerDocument
                SET document_date_of_expire = :new_expire,
                    document_date_of_issue  = :new_issue,
                    updated_at              = :updated_at
                WHERE passenger_document_id = :doc_id
            """), doc_update_batch)

        if booking_batch:
            conn.execute(text("""
                INSERT INTO BookingItem (booking_id, passenger_document_id, flight_price_id)
                VALUES (:booking_id, :passenger_document_id, :flight_price_id)
            """), booking_batch)
            inserted += len(booking_batch)

        logger.info("BookingItems inserted: %d", inserted)
        logger.info("Skipped:              %d", skipped)