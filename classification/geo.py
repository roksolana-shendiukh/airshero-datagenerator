import json
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def insert_geo_data(engine, json_path="files/geo.json"):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    with engine.begin() as conn:
        country_names = {record["country_name"].strip() for record in data["CountryCity"]}

        inserted_countries = 0
        inserted_cities = 0

        for country_name in sorted(country_names):
            exists = conn.execute(
                text("SELECT 1 FROM Country WHERE country_name = :country_name"),
                {"country_name": country_name}
            ).fetchone()

            if not exists:
                conn.execute(
                    text("INSERT INTO Country (country_name) VALUES (:country_name)"),
                    {"country_name": country_name}
                )
                inserted_countries += 1

        for record in data["CountryCity"]:
            country_name = record["country_name"].strip()
            city_name = record["city_name"].strip()

            country_id = conn.execute(
                text("SELECT TOP 1 country_id FROM Country WHERE country_name = :country_name"),
                {"country_name": country_name}
            ).scalar()

            if not country_id:
                logger.warning("Country '%s' not found, city '%s' skipped", country_name, city_name)
                continue

            exists = conn.execute(
                text("SELECT 1 FROM City WHERE city_name = :city_name AND country_id = :country_id"),
                {"city_name": city_name, "country_id": country_id}
            ).fetchone()

            if not exists:
                conn.execute(
                    text("INSERT INTO City (city_name, country_id) VALUES (:city_name, :country_id)"),
                    {"city_name": city_name, "country_id": country_id}
                )
                inserted_cities += 1

    logger.info("Country(%d)/City(%d) insertion completed", inserted_countries, inserted_cities)



    