import random
import logging
from faker import Faker
from sqlalchemy import text

logger = logging.getLogger(__name__)

COUNTRY_LOCALE = {
    "China":                "zh_CN",
    "France":               "fr_FR",
    "Germany":              "de_DE",
    "Italy":                "it_IT",
    "Poland":               "pl_PL",
    "Turkey":               "tr_TR",
    "Ukraine":              "uk_UA",
    "United Arab Emirates": "en_US",
    "United Kingdom":       "en_GB",
    "United States":        "en_US",
    "Egypt":                "en_US",
    "Australia":            "en_AU",
    "Brazil":               "pt_BR"
}

_fake_en = Faker("en_US")


def _is_ascii(s):
    return all(ord(c) < 128 for c in s)


def _agents_count(terminal_size):
    if terminal_size < 50_000:
        return random.randint(15, 30)
    elif terminal_size < 150_000:
        return random.randint(30, 60)
    elif terminal_size < 300_000:
        return random.randint(60, 100)
    else:
        return random.randint(100, 150)


def _generate_agent(country_name):
    fake = Faker(COUNTRY_LOCALE.get(country_name, "en_US"))

    for _ in range(20):
        try:
            first_name = _fake_en.first_name()
            last_name  = _fake_en.last_name()

            if not (_is_ascii(first_name) and _is_ascii(last_name)):
                continue
            if len(first_name) > 30 or len(last_name) > 30:
                continue

            phone = fake.phone_number()
            if not _is_ascii(phone):
                phone = _fake_en.phone_number()
            if len(phone) > 15:
                phone = phone[:15]

            return first_name, last_name, phone
        except Exception:
            continue

    return (
        _fake_en.first_name(),
        _fake_en.last_name(),
        _fake_en.phone_number()[:15]
    )


def generate_checkin_agents(engine):
    with engine.begin() as conn:
        airports = conn.execute(text("SELECT airport_id, city_id FROM Airport")).fetchall()

        total_inserted = 0

        for airport in airports:
            city = conn.execute(
                text("SELECT country_id FROM City WHERE city_id = :cid"),
                {"cid": airport.city_id}
            ).fetchone()

            country = conn.execute(
                text("SELECT country_name FROM Country WHERE country_id = :cid"),
                {"cid": city.country_id}
            ).fetchone()

            country_name = country.country_name
            if country_name not in COUNTRY_LOCALE:
                country_name = "United States"

            terminals = conn.execute(
                text("SELECT terminal_size FROM Terminal WHERE airport_id = :aid"),
                {"aid": airport.airport_id}
            ).fetchall()

            if not terminals:
                logger.warning("No terminals for airport_id=%d, skipping", airport.airport_id)
                continue

            batch = []

            for terminal in terminals:
                num_agents = _agents_count(float(terminal.terminal_size))
                for _ in range(num_agents):
                    first_name, last_name, phone = _generate_agent(country_name)
                    batch.append({
                        "airport_id": airport.airport_id,
                        "first_name": first_name,
                        "last_name":  last_name,
                        "phone":      phone,
                    })

            if batch:
                conn.execute(text("""
                    INSERT INTO CheckInAgent
                        (airport_id, checkin_agent_first_name,
                        checkin_agent_last_name, checkin_agent_phone_number)
                    VALUES
                        (:airport_id, :first_name, :last_name, :phone)
                """), batch)
                total_inserted += len(batch)
                logger.info("Inserted %d agents so far...", total_inserted)

    logger.info("CheckInAgent inserted: %d", total_inserted)


