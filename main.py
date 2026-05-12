import logging
from db_connect import create_sqlalchemy_engine
from logging_config import setup_logging
from classification import insert_classification_data

logger = logging.getLogger(__name__)

def main():
    engine = create_sqlalchemy_engine()
    if engine:
        logger.info("Engine created successfully")
        insert_classification_data(engine)
    else:
        logger.error("Failed to create DB engine")

if __name__ == "__main__":
    setup_logging()
    main()



    