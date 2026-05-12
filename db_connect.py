import sqlalchemy as sa
from sqlalchemy.engine import URL
import configparser
import logging

logger = logging.getLogger(__name__)

def create_sqlalchemy_engine():
    config = configparser.ConfigParser()
    config.read('db_config.ini')
    db = config['SQL_SERVER_AIRSHERO']

    DRIVER = db['DRIVER']
    SERVER = db['SERVER']
    DATABASE = db['DATABASE']
    UID = db['UID']
    PWD = db['PWD']

    connection_url = URL.create(
        "mssql+pyodbc",
        username=UID,
        password=PWD,
        host=SERVER,
        database=DATABASE,
        query={
            "driver": DRIVER,
            "TrustServerCertificate": "yes", 
        }
    )

    try:
        engine = sa.create_engine(connection_url)
        with engine.connect() as conn:
            result = conn.execute(sa.text("SELECT DB_NAME() AS db, SUSER_SNAME() AS user_name"))
            db_name, user_name = result.fetchone()
            
        logger.info('Successful connection to DB (%s, %s)', db_name, user_name)
        return engine
    except Exception as e:
        logger.error("Error SQLAlchemy connection: %s", e, exc_info=True)
        return None

