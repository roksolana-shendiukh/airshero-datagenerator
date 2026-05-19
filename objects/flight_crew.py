import random
import logging
from faker import Faker
from sqlalchemy import text

logger = logging.getLogger(__name__)
fake = Faker()

PILOT_LICENSES = [
    "Private Pilot License",
    "Commercial Pilot License",
    "Airline Transport Pilot License",
]

ENGINEERS_MODEL      = "Boeing 747-400"
PILOTS_PER_FLIGHT    = 1
COPILOTS_PER_FLIGHT  = 1
ATTENDANTS_PER_SEATS = 50
ENGINEERS_PER_FLIGHT = 1

ROTATIONS    = 4
REST_FACTOR  = 1.3

BATCH_SIZE    = 5_000
PROGRESS_STEP = 10_000


def _get_size_group(seat_capacity):
    if seat_capacity <= 200:
        return "small"
    elif seat_capacity <= 350:
        return "medium"
    return "large"


def _attendants_needed(seat_capacity):
    return max(1, seat_capacity // ATTENDANTS_PER_SEATS)


def _build_crew_config(model, seat_capacity):
    attendants_per_flight = max(4, seat_capacity // ATTENDANTS_PER_SEATS)
    engineers             = 4 if model == ENGINEERS_MODEL else 0
    return {
        "pilots":     round(PILOTS_PER_FLIGHT     * ROTATIONS * REST_FACTOR),
        "copilots":   round(COPILOTS_PER_FLIGHT   * ROTATIONS * REST_FACTOR),
        "attendants": round(attendants_per_flight  * ROTATIONS * REST_FACTOR),
        "engineers":  round(engineers              * ROTATIONS * REST_FACTOR) if engineers else 0,
    }


def insert_flight_crew(engine):
    with engine.begin() as conn:
        pos_rows = conn.execute(text(
            "SELECT flight_crew_position_id, flight_crew_position_name FROM FlightCrewPosition"
        )).fetchall()
        pos_id_by_name = {name: pid for pid, name in pos_rows}
        logger.info("Positions loaded: %s", list(pos_id_by_name.keys()))

        lic_rows = conn.execute(text(
            "SELECT flight_crew_license_type_id, flight_crew_license_type_name FROM FlightCrewLicenseType"
        )).fetchall()
        lic_id_by_name = {name: lid for lid, name in lic_rows}
        logger.info("Licenses loaded: %s", list(lic_id_by_name.keys()))

        af_rows = conn.execute(text(
            "SELECT af.airfleet_id, af.aircraft_model, af.seat_capacity, aa.airline_id FROM Airfleet af JOIN AirlineAirfleet aa ON aa.airfleet_id = af.airfleet_id"
        )).fetchall()
        logger.info("Airfleets loaded: %d", len(af_rows))

        size_groups   = {"small": [], "medium": [], "large": []}
        airfleet_info = {}
        for af_id, model, seat_capacity, airline_id in af_rows:
            group = _get_size_group(seat_capacity)
            size_groups[group].append(af_id)
            airfleet_info[af_id] = {"model": model, "seat_capacity": seat_capacity, "group": group}

        conn.execute(text("DELETE FROM AirfleetFlightCrew"))
        conn.execute(text("DELETE FROM FlightCrew"))
        logger.info("Cleared FlightCrew and AirfleetFlightCrew")

        total_crew = 0
        total_afc  = 0
        afc_pairs  = set()

        for af_id, model, seat_capacity, airline_id in af_rows:
            cfg = _build_crew_config(model, seat_capacity)

            groups = [
                ("Pilot",            random.choice(PILOT_LICENSES), cfg["pilots"]),
                ("Co-Pilot",         random.choice(PILOT_LICENSES), cfg["copilots"]),
                ("Flight Attendant", None,                           cfg["attendants"]),
            ]
            if cfg["engineers"] > 0:
                groups.append(("Engineer", "Flight Engineer License", cfg["engineers"]))

            similar = [a for a in size_groups[airfleet_info[af_id]["group"]] if a != af_id]

            for pos_name, lic_name, count in groups:
                pos_id = pos_id_by_name.get(pos_name)
                if pos_id is None:
                    logger.warning("Position '%s' not found in DB, skipping", pos_name)
                    continue

                lic_id = lic_id_by_name.get(lic_name) if lic_name else None

                for _ in range(count):
                    result = conn.execute(text("""
                        INSERT INTO FlightCrew
                            (airline_id, flight_crew_position_id, flight_crew_license_type,
                             flight_crew_first_name, flight_crew_last_name,
                             flight_crew_experience_years)
                        OUTPUT INSERTED.flight_crew_id
                        VALUES (:airline_id, :pos_id, :lic_id, :first_name, :last_name, :exp)
                    """), {
                        "airline_id": airline_id,
                        "pos_id":     pos_id,
                        "lic_id":     lic_id,
                        "first_name": fake.first_name(),
                        "last_name":  fake.last_name(),
                        "exp":        random.randint(1, 35),
                    })
                    crew_id = result.fetchone()[0]
                    total_crew += 1

                    if (crew_id, af_id) not in afc_pairs:
                        conn.execute(text("""
                            INSERT INTO AirfleetFlightCrew (flight_crew_id, airfleet_id)
                            VALUES (:crew_id, :af_id)
                        """), {"crew_id": crew_id, "af_id": af_id})
                        afc_pairs.add((crew_id, af_id))
                        total_afc += 1

                    if pos_name == "Engineer":
                        continue

                    if similar:
                        extras = random.sample(similar, min(random.randint(0, 2), len(similar)))
                        for extra_af in extras:
                            if (crew_id, extra_af) not in afc_pairs:
                                conn.execute(text("""
                                    INSERT INTO AirfleetFlightCrew (flight_crew_id, airfleet_id)
                                    VALUES (:crew_id, :af_id)
                                """), {"crew_id": crew_id, "af_id": extra_af})
                                afc_pairs.add((crew_id, extra_af))
                                total_afc += 1

            logger.info("airfleet_id=%d (%s, %d seats): %d crew members",
                        af_id, model, seat_capacity, sum(g[2] for g in groups))

    logger.info("=" * 60)
    logger.info("FlightCrew inserted:         %d", total_crew)
    logger.info("AirfleetFlightCrew inserted: %d", total_afc)
    if total_crew > 0:
        logger.info("Avg airfleets per crew:      %.2f", total_afc / total_crew)
    logger.info("=" * 60)


def generate_flight_flight_crew(engine):
    with engine.begin() as conn:
        logger.info("Loading reference data...")

        pos_rows = conn.execute(text(
            "SELECT flight_crew_position_id, flight_crew_position_name FROM FlightCrewPosition"
        )).fetchall()
        pos_id = {name: pid for pid, name in pos_rows}

        pilot_id     = pos_id["Pilot"]
        copilot_id   = pos_id["Co-Pilot"]
        attendant_id = pos_id["Flight Attendant"]
        engineer_id  = pos_id.get("Engineer")

        af_rows = conn.execute(text(
            "SELECT airfleet_id, aircraft_model, seat_capacity FROM Airfleet"
        )).fetchall()
        af_info = {af_id: {"model": model, "seats": seats}
                   for af_id, model, seats in af_rows}
        logger.info("Airfleets loaded: %d", len(af_info))

        crew_pool_rows = conn.execute(text("""
            SELECT afc.airfleet_id,
                   fc.flight_crew_position_id,
                   fc.flight_crew_id
            FROM   AirfleetFlightCrew afc
            JOIN   FlightCrew         fc ON fc.flight_crew_id = afc.flight_crew_id
        """)).fetchall()

        pool: dict = {}
        for af_id, position_id, crew_id in crew_pool_rows:
            pool.setdefault((af_id, position_id), []).append(crew_id)
        logger.info("Crew pool entries: %d", len(pool))

        total_flights = conn.execute(text("SELECT COUNT(*) FROM Flight")).scalar()
        logger.info("Total flights to process: %d", total_flights)

        conn.execute(text("DELETE FROM FlightFlightCrew"))
        logger.info("Cleared FlightFlightCrew")

        batch     = []
        processed = 0
        skipped   = 0
        offset    = 0

        while offset < total_flights:
            flights = conn.execute(text("""
                SELECT f.flight_id,
                       f.airline_id,
                       al.airfleet_id
                FROM   Flight f
                CROSS APPLY (
                    SELECT TOP 1 airfleet_id
                    FROM   AirlineAirfleet
                    WHERE  airline_id = f.airline_id
                    ORDER  BY airfleet_id
                ) al
                ORDER  BY f.flight_id
                OFFSET :offset ROWS FETCH NEXT :batch_size ROWS ONLY
            """), {"offset": offset, "batch_size": BATCH_SIZE}).fetchall()

            if not flights:
                break

            for flight_id, airline_id, af_id in flights:
                info = af_info.get(af_id)
                if not info:
                    logger.warning("Flight %d → unknown airfleet_id %s, skipping", flight_id, af_id)
                    skipped += 1
                    continue

                model    = info["model"]
                seats    = info["seats"]
                assigned = set()

                def pick(position_id, count):
                    candidates = pool.get((af_id, position_id), [])
                    available  = [c for c in candidates if c not in assigned]
                    if len(available) < count:
                        logger.warning(
                            "Flight %d (airfleet %d, pos %d): need %d, only %d available",
                            flight_id, af_id, position_id, count, len(available)
                        )
                    chosen = random.sample(available, min(count, len(available)))
                    assigned.update(chosen)
                    return chosen

                for cid in pick(pilot_id, PILOTS_PER_FLIGHT):
                    batch.append({"flight_id": flight_id, "flight_crew_id": cid})

                for cid in pick(copilot_id, COPILOTS_PER_FLIGHT):
                    batch.append({"flight_id": flight_id, "flight_crew_id": cid})

                for cid in pick(attendant_id, _attendants_needed(seats)):
                    batch.append({"flight_id": flight_id, "flight_crew_id": cid})

                if model == ENGINEERS_MODEL and engineer_id:
                    for cid in pick(engineer_id, ENGINEERS_PER_FLIGHT):
                        batch.append({"flight_id": flight_id, "flight_crew_id": cid})

                processed += 1

            if batch:
                conn.execute(text("""
                    INSERT INTO FlightFlightCrew (flight_id, flight_crew_id)
                    VALUES (:flight_id, :flight_crew_id)
                """), batch)
                batch.clear()

            offset += BATCH_SIZE

            if offset % PROGRESS_STEP == 0 or offset >= total_flights:
                logger.info("Processed %d / %d flights", processed, total_flights)

    logger.info("FlightFlightCrew rows inserted: %d", processed)
    logger.info("Flights skipped (no airfleet):  %d", skipped)
    
