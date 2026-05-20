import random
import logging
from datetime import datetime, timedelta
from sqlalchemy import text

logger = logging.getLogger(__name__)

BATCH_SIZE = 5_000


def generate_checkin_agent_operations(engine):
    with engine.begin() as conn:
        agents_by_airport = {}
        for row in conn.execute(text("SELECT checkin_agent_id, airport_id FROM CheckInAgent")):
            agents_by_airport.setdefault(row.airport_id, []).append(row.checkin_agent_id)

        operations = conn.execute(text("""
            SELECT
                fo.flight_operation_id,
                fo.boarding_start_time,
                fo.boarding_end_time,
                fo.actual_departure_date_time,
                g.terminal_id,
                t.airport_id
            FROM FlightOperation fo
            JOIN Gate g     ON g.gate_id = fo.gate_id
            JOIN Terminal t ON t.terminal_id = g.terminal_id
            WHERE fo.boarding_start_time IS NOT NULL
              AND fo.boarding_end_time IS NOT NULL
              AND fo.actual_departure_date_time IS NOT NULL
        """)).fetchall()

        logger.info("FlightOperations to process: %d", len(operations))

        agent_schedule = {}

        batch    = []
        inserted = 0

        for op in operations:
            fo_id      = op.flight_operation_id
            dep_dt     = op.actual_departure_date_time
            airport_id = op.airport_id

            board_start = datetime.combine(dep_dt.date(), op.boarding_start_time)
            board_end   = datetime.combine(dep_dt.date(), op.boarding_end_time)

            work_start = board_start - timedelta(minutes=random.randint(30, 60))
            work_end   = board_end   + timedelta(minutes=random.randint(15, 30))

            available_agents = [
                a for a in agents_by_airport.get(airport_id, [])
                if all(
                    work_end <= s or work_start >= e
                    for s, e in agent_schedule.get(a, [])
                )
            ]

            if not available_agents:
                logger.warning("No available agents for flight_operation_id=%d", fo_id)
                continue

            num_agents = min(random.randint(2, 4), len(available_agents))
            selected   = random.sample(available_agents, num_agents)

            for agent_id in selected:
                batch.append({
                    "agent_id": agent_id,
                    "fo_id":    fo_id,
                    "start":    work_start,
                    "end":      work_end,
                })
                agent_schedule.setdefault(agent_id, []).append((work_start, work_end))

            if len(batch) >= BATCH_SIZE:
                conn.execute(text("""
                    INSERT INTO CheckInAgentFlightOperation
                        (checkin_agent_id, flight_operation_id, start_work_datetime, end_work_datetime)
                    VALUES
                        (:agent_id, :fo_id, :start, :end)
                """), batch)
                inserted += len(batch)
                logger.info("Inserted %d records...", inserted)
                batch.clear()

        if batch:
            conn.execute(text("""
                INSERT INTO CheckInAgentFlightOperation
                    (checkin_agent_id, flight_operation_id, start_work_datetime, end_work_datetime)
                VALUES
                    (:agent_id, :fo_id, :start, :end)
            """), batch)
            inserted += len(batch)

        logger.info("CheckInAgentFlightOperation inserted: %d", inserted)

        