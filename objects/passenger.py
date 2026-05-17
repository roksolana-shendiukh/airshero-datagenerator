import random
import logging
from datetime import date
from sqlalchemy import text
from names_dataset import NameDataset

logger = logging.getLogger(__name__)

TOTAL      = 2_500_000
BATCH_SIZE = 10_000

_nd = NameDataset()

def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)

_male_first_names = [
    n for n in _nd.get_top_names(n=100000, gender='male', country_alpha2='US')['US']['M']
    if _is_ascii(n) and len(n) <= 30
]

_female_first_names = [
    n for n in _nd.get_top_names(n=100000, gender='female', country_alpha2='US')['US']['F']
    if _is_ascii(n) and len(n) <= 30
]

_last_names = [
    n for n in _nd.get_top_names(n=167000, use_first_names=False, country_alpha2='US')['US']
    if _is_ascii(n) and len(n) <= 30
]


def _random_dob():
    today = date.today()
    r     = random.random()
    if r < 0.80:
        age = random.randint(20, 37)
    elif r < 0.90:
        age = random.randint(0, 19)
    else:
        age = random.randint(38, 80)
    return date(today.year - age, random.randint(1, 12), random.randint(1, 28))


def _random_email(first_name, last_name, dob):
    age = (date.today() - dob).days // 365
    if age < 2:
        return None
    r = random.random()
    if r < 0.84:   domain = "gmail.com"
    elif r < 0.91: domain = "yahoo.com"
    else:          domain = "outlook.com"
    base  = f"{first_name.replace(' ', '').replace('-', '').lower()}.{last_name.replace(' ', '').replace('-', '').lower()}{random.randint(1, 999999)}"
    email = f"{base}@{domain}"
    return email if len(email) <= 45 else None


def generate_passengers(engine):
    inserted = 0
    batch    = []

    with engine.begin() as conn:
        while inserted < TOTAL:
            sex        = random.randint(0, 1)
            first_name = random.choice(_male_first_names if sex == 1 else _female_first_names)
            last_name  = random.choice(_last_names)

            if len(first_name) > 30 or len(last_name) > 30:
                continue

            dob   = _random_dob()
            email = _random_email(first_name, last_name, dob)

            batch.append({
                "first_name": first_name,
                "last_name":  last_name,
                "sex":        sex,
                "email":      email,
                "dob":        dob,
            })

            if len(batch) >= BATCH_SIZE:
                conn.execute(text("""
                    INSERT INTO Passenger
                        (passenger_first_name, passenger_last_name, passenger_sex,
                         passenger_email, passenger_date_of_birth)
                    VALUES
                        (:first_name, :last_name, :sex, :email, :dob)
                """), batch)
                inserted += len(batch)
                logger.info("Inserted %d / %d passengers", inserted, TOTAL)
                batch.clear()

        if batch:
            conn.execute(text("""
                INSERT INTO Passenger
                    (passenger_first_name, passenger_last_name, passenger_sex,
                     passenger_email, passenger_date_of_birth)
                VALUES
                    (:first_name, :last_name, :sex, :email, :dob)
            """), batch)
            inserted += len(batch)

    logger.info("Passengers inserted: %d", inserted)

