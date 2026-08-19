import logging
import time
from db_connect import create_sqlalchemy_engine
from logging_config import setup_logging
from cleanup import cleanup_empty_bookings
from classification import (
    insert_classification_data,
    insert_geo_data,
    insert_baggage_pricing_rules
)
from objects import (
    insert_aaa_data,
    generate_airline_airfleet,
    generate_aircraft,
    insert_routes,
    generate_flights,
    generate_flight_schedules,
    generate_seat_layout,
    generate_flight_class,
    generate_baggage_pricing,
    generate_passengers,
    insert_flight_crew,
    generate_flight_flight_crew,
    generate_checkin_agents
)
from documentary import (
    generate_scheduled_flights,
    generate_flight_prices,
    generate_bookings,
    generate_passenger_documents,
    generate_booking_items,
    generate_baggage_options,
    update_bookings,
    generate_payments,
    generate_flight_operations,
    generate_flight_crew_operations,
    generate_checkin_agent_operations,
    generate_boarding_passes,
    generate_baggage_units
)

logger = logging.getLogger(__name__)


def _run(name, fn, engine):
    logger.info(">>> START: %s", name)
    t = time.time()
    fn(engine)
    logger.info("<<< END:   %s | %.1fs", name, time.time() - t)


def main():
    engine = create_sqlalchemy_engine()
    if not engine:
        logger.error("Failed to create DB engine")
        return

    logger.info("Engine created successfully")
    total_start = time.time()

    _run("insert_classification_data",     insert_classification_data,     engine)
    _run("insert_geo_data",                insert_geo_data,                engine)
    _run("insert_baggage_pricing_rules",   insert_baggage_pricing_rules,   engine)
    _run("insert_aaa_data",                insert_aaa_data,                engine)
    _run("insert_routes",                  insert_routes,                  engine)
    _run("generate_flights",               generate_flights,               engine)
    _run("generate_airline_airfleet",      generate_airline_airfleet,      engine)
    _run("generate_aircraft",              generate_aircraft,              engine)
    _run("generate_flight_schedules",      generate_flight_schedules,      engine)
    _run("generate_seat_layout",           generate_seat_layout,           engine)
    _run("generate_flight_class",          generate_flight_class,          engine)
    _run("generate_scheduled_flights",     generate_scheduled_flights,     engine)
    _run("generate_flight_prices",         generate_flight_prices,         engine)
    _run("generate_baggage_pricing",       generate_baggage_pricing,       engine)
    _run("generate_bookings",              generate_bookings,              engine)
    _run("generate_passengers",            generate_passengers,            engine)
    _run("generate_passenger_documents",   generate_passenger_documents,   engine)
    _run("generate_booking_items",         generate_booking_items,         engine)
    _run("cleanup_empty_bookings",         cleanup_empty_bookings,         engine)
    _run("generate_baggage_options",       generate_baggage_options,       engine)
    _run("update_bookings",                update_bookings,                engine)
    _run("generate_payments",              generate_payments,              engine)
    _run("insert_flight_crew",             insert_flight_crew,             engine)
    _run("generate_flight_flight_crew",    generate_flight_flight_crew,    engine)
    _run("generate_flight_operations",     generate_flight_operations,     engine)
    _run("generate_flight_crew_operations",generate_flight_crew_operations,engine)
    _run("generate_checkin_agents",        generate_checkin_agents,        engine)
    _run("generate_checkin_agent_operations", generate_checkin_agent_operations, engine)
    _run("generate_boarding_passes",       generate_boarding_passes,       engine)
    _run("generate_baggage_units",         generate_baggage_units,         engine)

    total = time.time() - total_start
    h     = int(total // 3600)
    m     = int((total % 3600) // 60)
    s     = int(total % 60)
    logger.info("TOTAL TIME: %dh %dm %ds", h, m, s)


if __name__ == "__main__":
    setup_logging()
    main()