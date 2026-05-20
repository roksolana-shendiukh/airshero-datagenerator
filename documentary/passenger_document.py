import random
import logging
from datetime import date, timedelta
from sqlalchemy import text

logger = logging.getLogger(__name__)

BATCH_SIZE = 10_000

_used_numbers = set()


def _random_document_number(doc_code):
    while True:
        if doc_code in ("PAS", "INT"):
            num = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=2)) + str(random.randint(1000000, 9999999))
        elif doc_code == "OFF":
            num = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + str(random.randint(1000000, 9999999))
        else:
            num = str(random.randint(100000000, 999999999))
        if num not in _used_numbers:
            _used_numbers.add(num)
            return num


def _issue_and_expire_dates(dob, age, doc_code, max_issue_date):
    min_date   = date(max(dob.year + 1, max_issue_date.year - 10), 1, 1)
    if min_date > max_issue_date:
        min_date = max_issue_date.replace(month=1, day=1)
    days_range = (max_issue_date - min_date).days
    issue_date = min_date + timedelta(days=random.randint(0, max(days_range, 0)))

    validity_years = 5 if doc_code == "OFF" else (4 if age < 16 else 10)
    try:
        expire_date = date(issue_date.year + validity_years, issue_date.month, issue_date.day)
    except ValueError:
        expire_date = date(issue_date.year + validity_years, issue_date.month, 28)

    return issue_date, expire_date


def _document_codes_for_passenger(age):
    docs = []
    if random.random() < 0.95:
        rand = random.random()
        if age < 14:
            docs.append("ID")
        elif age < 25:
            if rand < 0.85:   docs.append("INT")
            elif rand < 0.95: docs.append("ID")
            else:             docs.append("OFF")
        elif age < 50:
            if rand < 0.75:   docs.append("INT")
            elif rand < 0.90: docs.append("PAS")
            elif rand < 0.97: docs.append("ID")
            else:             docs.append("OFF")
        else:
            if rand < 0.45:   docs.append("PAS")
            elif rand < 0.80: docs.append("INT")
            elif rand < 0.95: docs.append("ID")
            else:             docs.append("OFF")
    else:
        docs.append("INT")
        if age < 14:                docs.append("ID")
        elif age >= 50:             docs.append("PAS")
        elif random.random() < 0.6: docs.append("PAS")
        else:                       docs.append("ID")
    return docs


def generate_passenger_documents(engine):
    with engine.connect() as conn:
        doc_type_map = {
            code: tid
            for tid, code in conn.execute(text("SELECT document_type_id, document_type_code FROM DocumentType"))
        }

        popular_countries = list(conn.execute(text("""
            SELECT citizenship_id FROM Citizenship
            WHERE citizenship_name IN ('Ukrainian', 'British', 'American')
        """)).scalars().all())

        all_countries = list(conn.execute(text(
            "SELECT citizenship_id FROM Citizenship"
        )).scalars().all())

        max_issue_date = conn.execute(text(
            "SELECT CAST(MAX(departs_date) AS DATE) FROM ScheduledFlight"
        )).scalar()
        logger.info("Max flight date: %s", max_issue_date)

        passenger_data = conn.execute(text("""
            SELECT passenger_id,
                   DATEDIFF(year, passenger_date_of_birth, GETDATE()) AS age,
                   passenger_date_of_birth
            FROM Passenger
        """)).fetchall()

    total_passengers = len(passenger_data)
    logger.info("Passengers loaded: %d", total_passengers)

    inserted        = 0
    batch           = []
    doc_count_stats = {1: 0, 2: 0}

    with engine.begin() as conn:
        for passenger_id, age, dob in passenger_data:
            doc_codes = _document_codes_for_passenger(age)
            docs      = []

            for code in doc_codes:
                if code in ("PAS", "INT", "OFF"):
                    citizenship_id = random.choices(
                        popular_countries + all_countries,
                        weights=[8] * len(popular_countries) + [1] * len(all_countries),
                        k=1
                    )[0]
                else:
                    citizenship_id = random.choice(all_countries)

                issue_date, expire_date = _issue_and_expire_dates(dob, age, code, max_issue_date)

                docs.append({
                    "passenger_id":            passenger_id,
                    "citizenship_id":          citizenship_id,
                    "document_type_id":        doc_type_map[code],
                    "document_number":         _random_document_number(code),
                    "document_date_of_issue":  issue_date,
                    "document_date_of_expire": expire_date,
                })

            batch.extend(docs)
            doc_count_stats[min(len(docs), 2)] += 1

            if len(batch) >= BATCH_SIZE:
                conn.execute(text("""
                    INSERT INTO PassengerDocument
                        (passenger_id, citizenship_id, document_type_id, document_number,
                         document_date_of_issue, document_date_of_expire)
                    VALUES
                        (:passenger_id, :citizenship_id, :document_type_id, :document_number,
                         :document_date_of_issue, :document_date_of_expire)
                """), batch)
                inserted += len(batch)
                logger.info("Inserted %d documents...", inserted)
                batch.clear()

        if batch:
            conn.execute(text("""
                INSERT INTO PassengerDocument
                    (passenger_id, citizenship_id, document_type_id, document_number,
                     document_date_of_issue, document_date_of_expire)
                VALUES
                    (:passenger_id, :citizenship_id, :document_type_id, :document_number,
                     :document_date_of_issue, :document_date_of_expire)
            """), batch)
            inserted += len(batch)

    logger.info("PassengerDocument inserted: %d", inserted)
    logger.info("Average docs/passenger: %.2f", inserted / total_passengers if total_passengers else 0)
    logger.info("1 document:  %d (%.1f%%)", doc_count_stats[1], doc_count_stats[1] / total_passengers * 100)
    logger.info("2 documents: %d (%.1f%%)", doc_count_stats[2], doc_count_stats[2] / total_passengers * 100)