import json
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def insert_aaa_data(engine, json_path="files/aaaa.json"):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    with engine.begin() as conn:
        inserted_airfleets = 0
        inserted_airlines  = 0
        inserted_alliances = 0
        inserted_airports  = 0
        inserted_terminals = 0
        inserted_gates     = 0

        for aircraft in data.get("aircrafts", []):
            manufacturer_id = conn.execute(
                text("SELECT TOP 1 airfleet_manufacturer_id FROM AirfleetManufacturer WHERE airfleet_manufacturer_name = :name"),
                {"name": aircraft["manufacturer"]}
            ).scalars().first()
            if not manufacturer_id:
                logger.warning("Manufacturer not found: %s", aircraft["manufacturer"])
                continue

            result = conn.execute(text("""
                INSERT INTO Airfleet (
                    airfleet_manufacturer_id, aircraft_model, aircraft_range_km,
                    aircraft_speed, seat_capacity, baggage_capacity, aircraft_fuel_consumption
                )
                SELECT
                    :airfleet_manufacturer_id, :aircraft_model, :aircraft_range_km,
                    :aircraft_speed, :seat_capacity, :baggage_capacity, :aircraft_fuel_consumption
                WHERE NOT EXISTS (SELECT 1 FROM Airfleet WHERE aircraft_model = :aircraft_model)
            """), {
                "airfleet_manufacturer_id":  manufacturer_id,
                "aircraft_model":            aircraft["model"],
                "aircraft_range_km":         aircraft["range_km"],
                "aircraft_speed":            aircraft["speed_kmh"],
                "seat_capacity":             aircraft["seat_capacity"],
                "baggage_capacity":          aircraft["baggage_capacity_kg"],
                "aircraft_fuel_consumption": aircraft["fuel_consumption_lph"]
            })
            if result.rowcount > 0:
                inserted_airfleets += 1

        for alliance in data.get("alliances", []):
            result = conn.execute(text("""
                INSERT INTO Alliance (alliance_name, alliance_founded_year)
                SELECT :name, :founded_year
                WHERE NOT EXISTS (SELECT 1 FROM Alliance WHERE alliance_name = :name)
            """), {
                "name":         alliance["name"],
                "founded_year": alliance["founded_year"]
            })
            if result.rowcount > 0:
                inserted_alliances += 1

        for airline in data.get("airlines", []):
            country_id = conn.execute(
                text("SELECT TOP 1 country_id FROM Country WHERE country_name = :name"),
                {"name": airline["country"]}
            ).scalars().first()
            if not country_id:
                logger.warning("Country not found: %s", airline["country"])
                continue

            alliance_id = None
            if airline.get("alliance"):
                alliance_id = conn.execute(
                    text("SELECT TOP 1 airline_alliance_id FROM Alliance WHERE alliance_name = :name"),
                    {"name": airline["alliance"]}
                ).scalars().first()
                if not alliance_id:
                    logger.warning("Alliance not found: %s", airline["alliance"])

            result = conn.execute(text("""
                INSERT INTO Airline (airline_name, iata_code, country_id, alliance_id)
                SELECT :airline_name, :iata_code, :country_id, :alliance_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM Airline WHERE airline_name = :airline_name AND country_id = :country_id
                )
            """), {
                "airline_name": airline["name"],
                "iata_code":    airline["iata_code"],
                "country_id":   country_id,
                "alliance_id":  alliance_id
            })
            if result.rowcount > 0:
                inserted_airlines += 1

        for airport in data.get("airports", []):
            city_id = conn.execute(
                text("SELECT TOP 1 city_id FROM City WHERE city_name = :name"),
                {"name": airport["city"]}
            ).scalars().first()
            if not city_id:
                logger.warning("City not found: %s", airport["city"])
                continue

            result = conn.execute(text("""
                INSERT INTO Airport (airport_name, airport_code, airport_address, city_id)
                SELECT :airport_name, :airport_code, :airport_address, :city_id
                WHERE NOT EXISTS (SELECT 1 FROM Airport WHERE airport_code = :airport_code)
            """), {
                "airport_name":    airport["name"],
                "airport_code":    airport["code"],
                "airport_address": airport["address"],
                "city_id":         city_id
            })
            if result.rowcount > 0:
                inserted_airports += 1

            airport_id = conn.execute(
                text("SELECT TOP 1 airport_id FROM Airport WHERE airport_code = :code"),
                {"code": airport["code"]}
            ).scalars().first()

            for term in airport.get("terminals", []):
                terminal_type_id = conn.execute(
                    text("SELECT TOP 1 terminal_type_id FROM TerminalType WHERE terminal_type_name = :name"),
                    {"name": term["type"]}
                ).scalars().first()
                if not terminal_type_id:
                    logger.warning("TerminalType not found: %s", term["type"])
                    continue

                result = conn.execute(text("""
                    INSERT INTO Terminal (airport_id, terminal_type_id, terminal_code, terminal_size)
                    SELECT :airport_id, :terminal_type_id, :terminal_code, :terminal_size
                    WHERE NOT EXISTS (
                        SELECT 1 FROM Terminal WHERE airport_id = :airport_id AND terminal_code = :terminal_code
                    )
                """), {
                    "airport_id":       airport_id,
                    "terminal_type_id": terminal_type_id,
                    "terminal_code":    term["code"],
                    "terminal_size":    float(term["size_m2"])
                })
                if result.rowcount > 0:
                    inserted_terminals += 1

                terminal_id = conn.execute(
                    text("SELECT TOP 1 terminal_id FROM Terminal WHERE airport_id = :airport_id AND terminal_code = :terminal_code"),
                    {"airport_id": airport_id, "terminal_code": term["code"]}
                ).scalars().first()
                if not terminal_id:
                    continue

                for gate_code in term.get("gates", []):
                    result = conn.execute(text("""
                        INSERT INTO Gate (terminal_id, gate_code)
                        SELECT :terminal_id, :gate_code
                        WHERE NOT EXISTS (
                            SELECT 1 FROM Gate WHERE terminal_id = :terminal_id AND gate_code = :gate_code
                        )
                    """), {
                        "terminal_id": terminal_id,
                        "gate_code":   gate_code
                    })
                    if result.rowcount > 0:
                        inserted_gates += 1

    logger.info(
        "Inserted — Airfleets: %d, Alliances: %d, Airlines: %d, Airports: %d, Terminals: %d, Gates: %d",
        inserted_airfleets, inserted_alliances, inserted_airlines,
        inserted_airports, inserted_terminals, inserted_gates
    )

