import math
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

CLASS_SHARE = {
    "First":           0.05,
    "Business":        0.15,
    "Premium Economy": 0.20,
    "Economy":         0.60
}


def _assign_seat_type(col_index, total_columns):
    left_side  = min(3, total_columns // 2)
    right_side = min(3, total_columns // 2)
    if col_index <= left_side or col_index > total_columns - right_side:
        if col_index == 1 or col_index == total_columns:
            return "Window"
        else:
            return "Aisle"
    return "Middle"


def generate_seat_layout(engine):
    with engine.begin() as conn:
        class_map     = {name: cid for cid, name in conn.execute(text("SELECT class_id, class_name FROM Class")).fetchall()}
        seat_type_map = {name: sid for sid, name in conn.execute(text("SELECT seat_type_id, seat_type_name FROM SeatType")).fetchall()}
        airfleets     = conn.execute(text("SELECT airfleet_id, aircraft_model, seat_capacity FROM Airfleet")).fetchall()

        inserted = 0

        for airfleet_id, model, seat_capacity in airfleets:
            columns        = 6
            column_letters = ["A", "B", "C", "D", "E", "F"]

            class_counts    = {}
            total_assigned  = 0

            for class_name, share in CLASS_SHARE.items():
                if class_name == "First"           and seat_capacity < 200:
                    count = 0
                elif class_name == "Business"      and seat_capacity < 150:
                    count = 0
                elif class_name == "Premium Economy" and seat_capacity < 120:
                    count = 0
                else:
                    count = int(seat_capacity * share)
                class_counts[class_name] = count
                total_assigned += count

            class_counts["Economy"] += seat_capacity - total_assigned

            row_num = 1
            for class_name, num_seats in class_counts.items():
                seats_created = 0
                while seats_created < num_seats:
                    for col_index, col_letter in enumerate(column_letters, 1):
                        if seats_created >= num_seats:
                            break
                        conn.execute(text("""
                            INSERT INTO SeatLayout (seat_type_id, class_id, airfleet_id, seat_layout_rows, seat_layout_columns)
                            VALUES (:seat_type_id, :class_id, :airfleet_id, :row, :col)
                        """), {
                            "seat_type_id": seat_type_map[_assign_seat_type(col_index, columns)],
                            "class_id":     class_map[class_name],
                            "airfleet_id":  airfleet_id,
                            "row":          row_num,
                            "col":          col_letter
                        })
                        seats_created += 1
                        inserted      += 1
                    row_num += 1

        logger.info("SeatLayout records inserted: %d", inserted)


        