import random
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy import text

logger = logging.getLogger(__name__)

BATCH_SIZE = 1_000

NO_SHOW_BY_NAME = {
    "Economy":         0.02,
    "Premium Economy": 0.01,
    "Business":        0.00015,
    "First":           0.00005,
}

_existing_tickets = set()


def _generate_ticket_number():
    while True:
        ticket = f"TK{random.randint(1000000000, 9999999999)}"
        if ticket not in _existing_tickets:
            _existing_tickets.add(ticket)
            return ticket


def _issue_datetime(boarding_start, departs_date, dep_time):
    if dep_time is None:
        return None

    departs_dt = datetime.combine(departs_date, dep_time)

    if boarding_start is not None:
        start_dt = datetime.combine(departs_date, boarding_start)
    else:
        start_dt = departs_dt - timedelta(hours=2)

    end_dt = departs_dt - timedelta(minutes=30)

    if start_dt >= end_dt:
        start_dt = departs_dt - timedelta(hours=1)
    if start_dt >= end_dt:
        return departs_dt - timedelta(minutes=40)

    delta_seconds = int((end_dt - start_dt).total_seconds())
    return start_dt + timedelta(seconds=random.randint(0, delta_seconds))


def generate_boarding_passes(engine):

    with engine.begin() as conn:
        class_name_by_id = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT class_id, class_name FROM Class")).fetchall()
        }

        existing_tickets = {
            r[0] for r in conn.execute(text(
                "SELECT boarding_pass_ticket_number FROM BoardingPass"
            )).fetchall()
        }
        _existing_tickets.update(existing_tickets)
        logger.info("Existing ticket numbers loaded: %d", len(_existing_tickets))

        used_booking_items = {
            r[0] for r in conn.execute(text(
                "SELECT booking_item_id FROM BoardingPass"
            )).fetchall()
        }
        logger.info("Already used booking items: %d", len(used_booking_items))

        seats_raw = conn.execute(text(
            "SELECT airfleet_id, class_id, seat_layout_id "
            "FROM SeatLayout ORDER BY airfleet_id, class_id, seat_layout_id"
        )).fetchall()
        seats_by_airfleet_class = defaultdict(lambda: defaultdict(list))
        for af_id, class_id, seat_id in seats_raw:
            seats_by_airfleet_class[af_id][class_id].append(seat_id)
        logger.info("SeatLayout records loaded: %d", len(seats_raw))

        cafo_rows = conn.execute(text("""
            SELECT checkin_agent_flight_operation_id, flight_operation_id
            FROM CheckInAgentFlightOperation
        """)).fetchall()
        cafo_by_fo = defaultdict(list)
        for cafo_id, fo_id in cafo_rows:
            cafo_by_fo[fo_id].append(cafo_id)
        logger.info("CheckInAgentFlightOperation loaded: %d", len(cafo_rows))

        booking_items_raw = conn.execute(text("""
            SELECT
                bi.booking_item_id,
                fc.class_id,
                fp.schedule_flight_id
            FROM BookingItem bi
            JOIN Booking b        ON bi.booking_id = b.booking_id
            JOIN BookingStatus bs ON b.booking_status_id = bs.booking_status_id
            JOIN FlightPrice fp   ON bi.flight_price_id = fp.flight_price_id
            JOIN FlightClass fc   ON fp.flight_class_id = fc.flight_class_id
            WHERE bs.booking_status_name != 'Cancelled'
        """)).fetchall()

        booking_items_by_sf = defaultdict(list)
        for bi_id, class_id, sf_id in booking_items_raw:
            if bi_id not in used_booking_items:
                booking_items_by_sf[sf_id].append((bi_id, class_id))
        logger.info("BookingItems loaded: %d", len(booking_items_raw))

        flight_ops = conn.execute(text("""
            SELECT
                fo.flight_operation_id,
                fo.airfleet_id,
                fo.boarding_start_time,
                sf.departs_date,
                sf.schedule_flight_id,
                (
                    SELECT TOP 1 s.schedule_departure_time
                    FROM FlightSchedule fs
                    JOIN FlightScheduleDaySchedule fsds ON fsds.flight_schedule_id = fs.flight_schedule_id
                    JOIN DaySchedule ds ON ds.day_schedule_id = fsds.day_schedule_id
                    JOIN Schedule s    ON s.schedule_id = ds.schedule_id
                    WHERE fs.flight_id = sf.flight_id
                ) AS schedule_departure_time
            FROM FlightOperation fo
            JOIN ScheduledFlight sf ON sf.schedule_flight_id = fo.schedule_flight_id
            WHERE fo.boarding_start_time IS NOT NULL
            ORDER BY sf.departs_date
        """)).fetchall()
        logger.info("FlightOperations to process: %d", len(flight_ops))

        stats          = defaultdict(int)
        agent_usage    = defaultdict(int)
        batch          = []
        total_inserted = 0

        for fo_idx, fo in enumerate(flight_ops):
            fo_id        = fo.flight_operation_id
            airfleet_id  = fo.airfleet_id
            board_start  = fo.boarding_start_time
            departs_date = fo.departs_date
            sf_id        = fo.schedule_flight_id
            dep_time     = fo.schedule_departure_time

            cafo_ids = cafo_by_fo.get(fo_id, [])
            if not cafo_ids:
                stats["skipped_no_cafo"] += 1
                continue

            booking_items = booking_items_by_sf.get(sf_id, [])
            if not booking_items:
                stats["skipped_no_bookings"] += 1
                continue

            seats_by_class      = seats_by_airfleet_class.get(airfleet_id, {})
            seat_index_by_class = defaultdict(int)

            for bi_id, class_id in booking_items:
                if bi_id in used_booking_items:
                    continue

                class_name   = class_name_by_id.get(class_id, "Economy")
                no_show_rate = NO_SHOW_BY_NAME.get(class_name, 0.02)
                if random.random() < no_show_rate:
                    stats["no_show"] += 1
                    continue

                seats_list = seats_by_class.get(class_id, [])
                idx        = seat_index_by_class[class_id]
                if idx >= len(seats_list):
                    stats["skipped_no_seats"] += 1
                    continue

                seat_id = seats_list[idx]
                seat_index_by_class[class_id] += 1

                cafo_id = min(cafo_ids, key=lambda c: agent_usage.get(c, 0))
                agent_usage[cafo_id] += 1

                issue_dt = _issue_datetime(board_start, departs_date, dep_time)

                batch.append({
                    "cafo_id":    cafo_id,
                    "seat_id":    seat_id,
                    "bi_id":      bi_id,
                    "ticket":     _generate_ticket_number(),
                    "issue_dt":   issue_dt,
                })
                used_booking_items.add(bi_id)
                stats["boarding_passes_created"] += 1

                if len(batch) >= BATCH_SIZE:
                    conn.execute(text("""
                        INSERT INTO BoardingPass (
                            checkin_agent_flight_operation_id, seat_layout_id,
                            booking_item_id, boarding_pass_ticket_number,
                            boarding_pass_issue_date_time
                        ) VALUES (
                            :cafo_id, :seat_id,
                            :bi_id, :ticket,
                            :issue_dt
                        )
                    """), batch)
                    total_inserted += len(batch)
                    batch.clear()

            if (fo_idx + 1) % 500 == 0:
                logger.info("Processed %d/%d ops | inserted: %d | no-show: %d | no-seats: %d",
                            fo_idx + 1, len(flight_ops), total_inserted,
                            stats["no_show"], stats["skipped_no_seats"])

        if batch:
            conn.execute(text("""
                INSERT INTO BoardingPass (
                    checkin_agent_flight_operation_id, seat_layout_id,
                    booking_item_id, boarding_pass_ticket_number,
                    boarding_pass_issue_date_time
                ) VALUES (
                    :cafo_id, :seat_id,
                    :bi_id, :ticket,
                    :issue_dt
                )
            """), batch)
            total_inserted += len(batch)

    logger.info("BoardingPass inserted:        %d", total_inserted)
    logger.info("No-show:                      %d", stats["no_show"])
    logger.info("Skipped (no seats):           %d", stats["skipped_no_seats"])
    logger.info("Skipped (no cafo):            %d", stats["skipped_no_cafo"])
    logger.info("Skipped (no bookings):        %d", stats["skipped_no_bookings"])


    