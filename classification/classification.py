import json
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def insert_classification_data(engine):
    with open("files/classification.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    insertions = [
        ("citizenships", "Citizenship", "citizenship_name",
         "INSERT INTO Citizenship (citizenship_name) VALUES (:citizenship_name)"),

        ("documentTypes", "DocumentType", "document_type_code",
         "INSERT INTO DocumentType (document_type_name, document_type_code) VALUES (:document_type_name, :document_type_code)"),

        ("bookingStatuses", "BookingStatus", "booking_status_name",
         "INSERT INTO BookingStatus (booking_status_name) VALUES (:booking_status_name)"),

        ("baggageTypes", "BaggageType", "baggage_type_name",
         "INSERT INTO BaggageType (baggage_type_name) VALUES (:baggage_type_name)"),

        ("classes", "Class", "class_name",
         "INSERT INTO Class (class_name) VALUES (:class_name)"),

        ("flightStatuses", "FlightStatus", "flight_status_name",
         "INSERT INTO FlightStatus (flight_status_name) VALUES (:flight_status_name)"),

        ("seatTypes", "SeatType", "seat_type_name",
         "INSERT INTO SeatType (seat_type_name) VALUES (:seat_type_name)"),

        ("paymentStatuses", "PaymentStatus", "payment_status_name",
         "INSERT INTO PaymentStatus (payment_status_name) VALUES (:payment_status_name)"),

        ("paymentMethods", "PaymentMethod", "payment_method_name",
         "INSERT INTO PaymentMethod (payment_method_name) VALUES (:payment_method_name)"),

        ("daysForSchedule", "DayForSchedule", "day_name",
         "INSERT INTO DayForSchedule (day_name) VALUES (:day_name)"),

        ("airfleetsManufactures", "AirfleetManufacturer", "airfleet_manufacturer_name",
         "INSERT INTO AirfleetManufacturer (airfleet_manufacturer_name) VALUES (:airfleet_manufacturer_name)"),

        ("flightOperationStatuses", "FlightOperationStatus", "flight_operation_status_name",
         "INSERT INTO FlightOperationStatus (flight_operation_status_name) VALUES (:flight_operation_status_name)"),

        ("flightCrewPositions", "FlightCrewPosition", "flight_crew_position_name",
         "INSERT INTO FlightCrewPosition (flight_crew_position_name) VALUES (:flight_crew_position_name)"),

        ("flightCrewLicenseTypes", "FlightCrewLicenseType", "flight_crew_license_type_name",
         "INSERT INTO FlightCrewLicenseType (flight_crew_license_type_name) VALUES (:flight_crew_license_type_name)"),

        ("terminalTypes", "TerminalType", "terminal_type_name",
         "INSERT INTO TerminalType (terminal_type_name) VALUES (:terminal_type_name)"),

        ("flightOperationStates", "FlightOperationState", "flight_operation_state_description",
         "INSERT INTO FlightOperationState (flight_operation_state_description) VALUES (:flight_operation_state_description)"),
    ]

    with engine.begin() as conn:
        for json_key, table, check_field, insert_sql in insertions:
            inserted = 0
            skipped = 0

            for item in data.get(json_key, []):
                check_value = item[check_field]
                exists = conn.execute(
                    text(f"SELECT 1 FROM {table} WHERE {check_field} = :val"),
                    {"val": check_value}
                ).fetchone()

                if not exists:
                    conn.execute(text(insert_sql), item)
                    inserted += 1
                else:
                    skipped += 1

            logger.info("Table %s: inserted %d, skipped %d", table, inserted, skipped)

    logger.info("Classification data insertion completed")


    