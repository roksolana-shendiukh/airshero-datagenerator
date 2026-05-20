import logging
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
    update_bookings,
    generate_payments,
    generate_flight_operations,
    generate_flight_crew_operations
)

logger = logging.getLogger(__name__)

def main():
    engine = create_sqlalchemy_engine()
    if engine:
        logger.info("Engine created successfully")
        #insert_classification_data(engine)
        #insert_geo_data(engine)
        #insert_baggage_pricing_rules(engine)
        #insert_aaa_data(engine)
        #insert_routes(engine)
        #generate_flights(engine)
        #generate_airline_airfleet(engine)
        #generate_flight_schedules(engine)
        #generate_seat_layout(engine)
        #generate_flight_class(engine)
        #generate_scheduled_flights(engine)
        #generate_flight_prices(engine)    
        #generate_baggage_pricing(engine)    
        #generate_bookings(engine)
        #generate_passengers(engine)
        #generate_passenger_documents(engine)
        #generate_booking_items(engine)
        #cleanup_empty_bookings(engine)
        #update_bookings(engine)
        #generate_payments(engine)
        #insert_flight_crew(engine)
        #generate_flight_flight_crew(engine)
        #generate_flight_operations(engine)
        #generate_flight_crew_operations(engine)
        generate_checkin_agents(engine)
    else:
        logger.error("Failed to create DB engine")

if __name__ == "__main__":
    setup_logging()
    main()



