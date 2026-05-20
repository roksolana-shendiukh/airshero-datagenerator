import random
import logging
from datetime import datetime, timedelta
from sqlalchemy import text

logger = logging.getLogger(__name__)

TOTAL_PROBLEM_RATE = 0.15
BATCH_SIZE         = 5_000


def generate_flight_operations(engine):
    with engine.begin() as conn:
        flight_op_statuses = {
            name: sid
            for sid, name in conn.execute(text(
                "SELECT flight_operation_status_id, flight_operation_status_name FROM FlightOperationStatus"
            ))
        }

        flight_op_states = [
            row[0] for row in conn.execute(text(
                "SELECT flight_operation_state_id FROM FlightOperationState "
                "WHERE flight_operation_state_description IS NOT NULL "
                "AND flight_operation_state_description != ''"
            ))
        ]

        flights = conn.execute(text("""
            SELECT
                sf.schedule_flight_id,
                sf.departs_date,
                f.airfleet_id,
                r.departs_airport_id,
                r.flight_range,
                a.seat_capacity,
                (
                    SELECT TOP 1 s.schedule_departure_time
                    FROM FlightSchedule fs
                    JOIN FlightScheduleDaySchedule fsds ON fsds.flight_schedule_id = fs.flight_schedule_id
                    JOIN DaySchedule ds ON ds.day_schedule_id = fsds.day_schedule_id
                    JOIN Schedule s    ON s.schedule_id = ds.schedule_id
                    WHERE fs.flight_id = f.flight_id
                ) AS schedule_departure_time,
                (
                    SELECT TOP 1 s.schedule_arrival_time
                    FROM FlightSchedule fs
                    JOIN FlightScheduleDaySchedule fsds ON fsds.flight_schedule_id = fs.flight_schedule_id
                    JOIN DaySchedule ds ON ds.day_schedule_id = fsds.day_schedule_id
                    JOIN Schedule s    ON s.schedule_id = ds.schedule_id
                    WHERE fs.flight_id = f.flight_id
                ) AS schedule_arrival_time
            FROM ScheduledFlight sf
            JOIN Flight f         ON f.flight_id = sf.flight_id
            JOIN Route r          ON r.route_id = f.route_id
            JOIN Airfleet a       ON a.airfleet_id = f.airfleet_id
            JOIN FlightStatus fst ON fst.flight_status_id = sf.flight_status_id
            WHERE fst.flight_status_name = 'Completed'
        """)).fetchall()

        logger.info("Total completed flights: %d", len(flights))

        batch           = []
        inserted        = 0
        skipped_no_gate = 0

        for f in flights:
            flight_range  = float(f.flight_range)
            seat_capacity = int(f.seat_capacity)
            departs_date  = f.departs_date
            dep_time      = f.schedule_departure_time
            arr_time      = f.schedule_arrival_time

            if dep_time is None or arr_time is None:
                skipped_no_gate += 1
                continue

            scheduled_departure = datetime.combine(departs_date, dep_time)
            scheduled_arrival   = datetime.combine(departs_date, arr_time)
            if scheduled_arrival <= scheduled_departure:
                scheduled_arrival += timedelta(days=1)

            is_short = flight_range <= 1500

            gate_result = conn.execute(text("""
                SELECT TOP 1 g.gate_id
                FROM Gate g
                JOIN Terminal t ON g.terminal_id = t.terminal_id
                WHERE t.airport_id = :airport_id
                ORDER BY NEWID()
            """), {"airport_id": f.departs_airport_id}).fetchone()

            if gate_result is None:
                skipped_no_gate += 1
                continue

            gate_id = gate_result.gate_id

            if random.random() < TOTAL_PROBLEM_RATE:
                delay_minutes = random.randint(30, 300)
                state_id      = random.choice(flight_op_states)
            else:
                state_id = None
                if is_short and random.random() < 0.10:
                    delay_minutes = -random.randint(5, 30)
                else:
                    delay_minutes = random.randint(5, 35)

            makeup_minutes   = random.randint(0, 5) if is_short else random.randint(10, 40)
            actual_departure = scheduled_departure + timedelta(minutes=delay_minutes)
            actual_arrival   = scheduled_arrival + timedelta(minutes=delay_minutes) - timedelta(minutes=makeup_minutes)

            if seat_capacity < 100:   boarding_offset = 45
            elif seat_capacity < 200: boarding_offset = 60
            elif seat_capacity < 300: boarding_offset = 90
            else:                     boarding_offset = 120

            boarding_start = actual_departure - timedelta(minutes=boarding_offset)
            boarding_end   = actual_departure - timedelta(minutes=random.randint(5, 10))
            baggage_start  = boarding_start   - timedelta(minutes=random.randint(20, 30))
            baggage_end    = boarding_start   - timedelta(minutes=random.randint(5, 10))

            batch.append({
                "sf_id":     f.schedule_flight_id,
                "af_id":     f.airfleet_id,
                "gate_id":   gate_id,
                "op_status": flight_op_statuses["Completed"],
                "op_state":  state_id,
                "act_dep":   actual_departure,
                "act_arr":   actual_arrival,
                "board_s":   boarding_start.time(),
                "board_e":   boarding_end.time(),
                "bag_s":     baggage_start.time(),
                "bag_e":     baggage_end.time(),
            })

            if len(batch) >= BATCH_SIZE:
                conn.execute(text("""
                    INSERT INTO FlightOperation (
                        schedule_flight_id, airfleet_id, gate_id,
                        flight_operation_status_id, flight_operation_state_id,
                        actual_departure_date_time, actual_arrival_date_time,
                        boarding_start_time, boarding_end_time,
                        baggage_loading_start_time, baggage_loading_end_time
                    ) VALUES (
                        :sf_id, :af_id, :gate_id,
                        :op_status, :op_state,
                        :act_dep, :act_arr,
                        :board_s, :board_e,
                        :bag_s, :bag_e
                    )
                """), batch)
                inserted += len(batch)
                logger.info("Inserted %d flight operations...", inserted)
                batch.clear()

        if batch:
            conn.execute(text("""
                INSERT INTO FlightOperation (
                    schedule_flight_id, airfleet_id, gate_id,
                    flight_operation_status_id, flight_operation_state_id,
                    actual_departure_date_time, actual_arrival_date_time,
                    boarding_start_time, boarding_end_time,
                    baggage_loading_start_time, baggage_loading_end_time
                ) VALUES (
                    :sf_id, :af_id, :gate_id,
                    :op_status, :op_state,
                    :act_dep, :act_arr,
                    :board_s, :board_e,
                    :bag_s, :bag_e
                )
            """), batch)
            inserted += len(batch)

        logger.info("FlightOperation inserted: %d", inserted)
        if skipped_no_gate > 0:
            logger.warning("Skipped due to missing gate or schedule: %d", skipped_no_gate)
            