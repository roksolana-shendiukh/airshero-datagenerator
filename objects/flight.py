import json
import random
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

HUB_AIRPORTS = {
    "KBP", "LHR", "CDG", "FRA", "IST",
    "DXB", "JFK", "LAX", "ORD", "GRU",
    "PEK", "PVG", "CAN", "SYD", "AUH",
    "FCO", "MUC", "WAW", "MAN", "BER",
    "MXP", "CGH", "GIG", "IAH", "MIA",
    "MEL", "CAI", "SHA"
}

SHORT_RANGE = 2000
LONG_RANGE  = 5000


def _duration_str(flight_range: float, aircraft_speed: float) -> str:
    total_minutes = round((flight_range / aircraft_speed) * 60)
    hours   = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}:00"


def generate_flights(engine, json_path="files/aaaa.json"):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    airline_types = {a["iata_code"]: a["type"] for a in data["airlines"]}
    aircraft_speeds = {a["model"]: a["speed_kmh"] for a in data["aircrafts"]}

    with engine.begin() as conn:
        airlines = [dict(r._mapping) for r in conn.execute(text(
            "SELECT airline_id, iata_code FROM Airline"
        ))]
        airline_map = {r["iata_code"]: r["airline_id"] for r in airlines}

        airfleets = [dict(r._mapping) for r in conn.execute(text(
            "SELECT airfleet_id, aircraft_speed FROM Airfleet"
        ))]
        airfleet_speed = {r["airfleet_id"]: float(r["aircraft_speed"]) for r in airfleets}
        all_airfleet_ids = list(airfleet_speed.keys())

        aa_pairs = [dict(r._mapping) for r in conn.execute(text(
            "SELECT airline_id, airfleet_id FROM AirlineAirfleet"
        ))]
        airline_airfleets = {}
        for p in aa_pairs:
            airline_airfleets.setdefault(p["airline_id"], []).append(p["airfleet_id"])

        routes = [dict(r._mapping) for r in conn.execute(text("""
            SELECT r.route_id, r.flight_range,
                   a1.airport_code AS dep_code,
                   a2.airport_code AS arr_code
            FROM Route r
            JOIN Airport a1 ON a1.airport_id = r.departs_airport_id
            JOIN Airport a2 ON a2.airport_id = r.arrives_airport_id
        """))]

        existing_flights = set(
            (row[0], row[1])
            for row in conn.execute(text("SELECT airline_id, route_id FROM Flight"))
        )

        flight_counters = {iata: 101 for iata in airline_types}

        inserted = 0
        routes_covered  = set()
        airlines_with_flights = set()

        for route in routes:
            flight_range = float(route["flight_range"])
            dep_code     = route["dep_code"]
            arr_code     = route["arr_code"]
            is_popular   = dep_code in HUB_AIRPORTS and arr_code in HUB_AIRPORTS

            count = random.randint(4, 5) if is_popular else random.randint(2, 3)

            candidates = []
            for iata, atype in airline_types.items():
                if atype == "lowcost"  and flight_range > SHORT_RANGE:
                    continue
                if atype == "longhaul" and flight_range < LONG_RANGE:
                    continue
                airline_id = airline_map.get(iata)
                if not airline_id:
                    continue
                candidates.append((iata, airline_id))

            if not candidates:
                logger.warning("No candidates for route %s->%s", dep_code, arr_code)
                continue

            selected = random.sample(candidates, min(count, len(candidates)))

            for iata, airline_id in selected:
                if (airline_id, route["route_id"]) in existing_flights:
                    continue

                avail_airfleets = airline_airfleets.get(airline_id) or all_airfleet_ids
                airfleet_id     = random.choice(avail_airfleets)
                speed           = airfleet_speed.get(airfleet_id, 850.0)
                duration        = _duration_str(flight_range, speed)
                flight_number   = f"{iata}{flight_counters[iata]}"
                flight_counters[iata] += 1

                conn.execute(text("""
                    INSERT INTO Flight (airline_id, route_id, airfleet_id, flight_number, flight_duration, is_deleted)
                    VALUES (:airline_id, :route_id, :airfleet_id, :flight_number, :flight_duration, 0)
                """), {
                    "airline_id":      airline_id,
                    "route_id":        route["route_id"],
                    "airfleet_id":     airfleet_id,
                    "flight_number":   flight_number,
                    "flight_duration": duration
                })

                inserted += 1
                existing_flights.add((airline_id, route["route_id"]))
                routes_covered.add(route["route_id"])
                airlines_with_flights.add(airline_id)

        all_route_ids   = {r["route_id"] for r in routes}
        all_airline_ids = {r["airline_id"] for r in airlines}

        uncovered_routes    = all_route_ids - routes_covered
        airlines_no_flights = all_airline_ids - airlines_with_flights

        logger.info("Flights inserted: %d", inserted)

        if uncovered_routes:
            logger.warning("Routes without any flight (%d): %s", len(uncovered_routes), uncovered_routes)
        else:
            logger.info("All routes have at least one flight")

        if airlines_no_flights:
            uncovered_iata = [r["iata_code"] for r in airlines if r["airline_id"] in airlines_no_flights]
            logger.warning("Airlines without any flight (%d): %s", len(airlines_no_flights), uncovered_iata)
        else:
            logger.info("All airlines have at least one flight")


