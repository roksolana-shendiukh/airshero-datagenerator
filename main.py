import logging
from db_connect import create_sqlalchemy_engine
from logging_config import setup_logging
from classification import (
    insert_classification_data, 
    insert_geo_data, 
    insert_baggage_pricing_rules
)
from objects import (
    insert_aaa_data,
    generate_airline_airfleet,
    insert_routes,
    generate_flights
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
        generate_airline_airfleet(engine)
    else:
        logger.error("Failed to create DB engine")

if __name__ == "__main__":
    setup_logging()
    main()



