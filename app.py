from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime
from collections import deque
import os


app = Flask(__name__)

DATABASE = os.path.join(
    os.path.dirname(__file__),
    "parking.db"
)

# Waiting queue
waiting_queue = deque()

# Simulated barrier
barrier_state = "Closed"


# ==================================================
# DATABASE
# ==================================================

def get_db_connection():

    connection = sqlite3.connect(DATABASE)

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


# ==================================================
# PARKING SLOT
# ==================================================

def find_available_slot(connection):

    slot = connection.execute("""
        SELECT slot_number
        FROM parking_slots
        WHERE status = 'Available'
        ORDER BY id
        LIMIT 1
    """).fetchone()

    if slot:
        return slot["slot_number"]

    return None


# ==================================================
# FIND VEHICLE
# ==================================================

def find_vehicle(connection, vehicle_number):

    return connection.execute("""
        SELECT *
        FROM vehicles
        WHERE vehicle_number = ?
    """, (vehicle_number,)).fetchone()


# ==================================================
# PARKING RATE
# ==================================================

def get_cost_per_minute():

    connection = get_db_connection()

    result = connection.execute("""
        SELECT cost_per_minute
        FROM parking_settings
        WHERE id = 1
    """).fetchone()

    connection.close()

    if result is None:
        return 1

    return result["cost_per_minute"]


def set_cost_per_minute(new_rate):

    connection = get_db_connection()

    try:

        connection.execute("""
            UPDATE parking_settings
            SET cost_per_minute = ?
            WHERE id = 1
        """, (new_rate,))

        connection.commit()

        return {
            "success": True,
            "rate": new_rate,
            "message": "Parking rate updated successfully."
        }

    except Exception as error:

        connection.rollback()

        return {
            "success": False,
            "message": str(error)
        }

    finally:

        connection.close()


# ==================================================
# DURATION AND COST
# ==================================================

def calculate_duration(entry_time, exit_time):

    duration = exit_time - entry_time

    minutes = int(
        duration.total_seconds() / 60
    )

    if minutes < 1:
        minutes = 1

    return minutes


def calculate_cost(minutes):

    rate = get_cost_per_minute()

    return minutes * rate


# ==================================================
# SIMULATED PAYMENT
# ==================================================

def create_payment(
    connection,
    parking_record_id,
    amount,
    payment_method
):

    allowed_methods = [
        "Cash",
        "M-Pesa",
        "Card"
    ]

    if payment_method not in allowed_methods:

        return {
            "success": False,
            "message": "Invalid payment method."
        }

    timestamp = datetime.now().strftime(
        "%Y%m%d%H%M%S%f"
    )

    prefix = {
        "Cash": "CASH",
        "M-Pesa": "MPESA",
        "Card": "CARD"
    }

    payment_reference = (
        prefix[payment_method]
        + "-"
        + timestamp
    )

    payment_time = datetime.now().isoformat()

    # Simulated confirmation
    connection.execute("""
        INSERT INTO payments (
            parking_record_id,
            amount,
            payment_method,
            payment_status,
            payment_reference,
            payment_time
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        parking_record_id,
        amount,
        payment_method,
        "Confirmed",
        payment_reference,
        payment_time
    ))

    return {
        "success": True,
        "reference": payment_reference
    }


# ==================================================
# SIMULATED BARRIER
# ==================================================

def open_barrier():

    global barrier_state

    barrier_state = "Open"

    return {
        "success": True,
        "barrier": "Open",
        "message": "Payment confirmed. Barrier opened."
    }


# ==================================================
# ENTER VEHICLE
# ==================================================

def enter_vehicle(
    vehicle_number,
    owner_name,
    vehicle_type
):

    connection = get_db_connection()

    try:

        vehicle_number = (
            vehicle_number.strip().upper()
        )

        owner_name = owner_name.strip()
        vehicle_type = vehicle_type.strip()

        if not vehicle_number:

            return {
                "success": False,
                "message": "Vehicle number is required."
            }

        if not owner_name:

            return {
                "success": False,
                "message": "Owner name is required."
            }

        if not vehicle_type:

            return {
                "success": False,
                "message": "Vehicle type is required."
            }

        # Find existing vehicle
        vehicle = find_vehicle(
            connection,
            vehicle_number
        )

        # Create vehicle
        if vehicle is None:

            cursor = connection.execute("""
                INSERT INTO vehicles (
                    vehicle_number,
                    owner_name,
                    vehicle_type
                )
                VALUES (?, ?, ?)
            """, (
                vehicle_number,
                owner_name,
                vehicle_type
            ))

            vehicle_id = cursor.lastrowid

        else:

            vehicle_id = vehicle["id"]

        # Check if already parked
        active = connection.execute("""
            SELECT *
            FROM parking_records
            WHERE vehicle_id = ?
            AND exit_time IS NULL
        """, (vehicle_id,)).fetchone()

        if active:

            connection.rollback()

            return {
                "success": False,
                "message": "This vehicle is already parked."
            }

        # Find slot
        slot_number = find_available_slot(
            connection
        )

        # Parking full
        if slot_number is None:

            connection.commit()

            if vehicle_number not in waiting_queue:

                waiting_queue.append(
                    vehicle_number
                )

            return {
                "success": True,
                "queued": True,
                "vehicle_number": vehicle_number,
                "message":
                    "Parking is full. "
                    "Vehicle added to waiting queue."
            }

        # Entry time
        entry_time = datetime.now().isoformat()

        # Create parking record
        connection.execute("""
            INSERT INTO parking_records (
                vehicle_id,
                slot_number,
                entry_time
            )
            VALUES (?, ?, ?)
        """, (
            vehicle_id,
            slot_number,
            entry_time
        ))

        # Occupy slot
        connection.execute("""
            UPDATE parking_slots
            SET status = 'Occupied'
            WHERE slot_number = ?
        """, (slot_number,))

        connection.commit()

        return {
            "success": True,
            "queued": False,
            "vehicle_number": vehicle_number,
            "slot_number": slot_number,
            "entry_time": entry_time,
            "message":
                f"Vehicle parked successfully "
                f"in slot {slot_number}."
        }

    except Exception as error:

        connection.rollback()

        return {
            "success": False,
            "message": str(error)
        }

    finally:

        connection.close()


# ==================================================
# EXIT VEHICLE
# ==================================================

def exit_vehicle(
    vehicle_number,
    payment_method
):

    connection = get_db_connection()

    try:

        vehicle_number = (
            vehicle_number.strip().upper()
        )

        vehicle = find_vehicle(
            connection,
            vehicle_number
        )

        if vehicle is None:

            return {
                "success": False,
                "message": "Vehicle not found."
            }

        # Find active parking record
        record = connection.execute("""
            SELECT *
            FROM parking_records
            WHERE vehicle_id = ?
            AND exit_time IS NULL
            ORDER BY id DESC
            LIMIT 1
        """, (vehicle["id"],)).fetchone()

        if record is None:

            return {
                "success": False,
                "message":
                    "Vehicle is not currently parked."
            }

        entry_time = datetime.fromisoformat(
            record["entry_time"]
        )

        exit_time = datetime.now()

        duration_minutes = calculate_duration(
            entry_time,
            exit_time
        )

        cost = calculate_cost(
            duration_minutes
        )

        # Simulated payment confirmation
        payment = create_payment(
            connection,
            record["id"],
            cost,
            payment_method
        )

        if not payment["success"]:

            connection.rollback()

            return payment

        # Update parking record
        connection.execute("""
            UPDATE parking_records
            SET
                exit_time = ?,
                duration_minutes = ?,
                cost = ?
            WHERE id = ?
        """, (
            exit_time.isoformat(),
            duration_minutes,
            cost,
            record["id"]
        ))

        # Release slot
        connection.execute("""
            UPDATE parking_slots
            SET status = 'Available'
            WHERE slot_number = ?
        """, (
            record["slot_number"],
        ))

        connection.commit()

        # Open simulated barrier
        barrier = open_barrier()

        # Process waiting queue
        process_waiting_queue()

        return {
            "success": True,
            "vehicle_number": vehicle_number,
            "slot_number": record["slot_number"],
            "entry_time": record["entry_time"],
            "exit_time": exit_time.isoformat(),
            "duration_minutes": duration_minutes,
            "cost": cost,
            "payment_method": payment_method,
            "payment_reference":
                payment["reference"],
            "payment_status": "Confirmed",
            "barrier": barrier["barrier"],
            "message":
                "Payment confirmed. "
                "Barrier opened."
        }

    except Exception as error:

        connection.rollback()

        return {
            "success": False,
            "message": str(error)
        }

    finally:

        connection.close()


# ==================================================
# WAITING QUEUE
# ==================================================

def process_waiting_queue():

    while waiting_queue:

        connection = get_db_connection()

        try:

            slot_number = find_available_slot(
                connection
            )

            if slot_number is None:

                connection.close()
                return

            vehicle_number = waiting_queue[0]

            vehicle = find_vehicle(
                connection,
                vehicle_number
            )

            if vehicle is None:

                waiting_queue.popleft()
                connection.close()
                continue

            # Check if already parked
            active = connection.execute("""
                SELECT *
                FROM parking_records
                WHERE vehicle_id = ?
                AND exit_time IS NULL
            """, (
                vehicle["id"],
            )).fetchone()

            if active:

                waiting_queue.popleft()
                connection.close()
                continue

            entry_time = datetime.now().isoformat()

            connection.execute("""
                INSERT INTO parking_records (
                    vehicle_id,
                    slot_number,
                    entry_time
                )
                VALUES (?, ?, ?)
            """, (
                vehicle["id"],
                slot_number,
                entry_time
            ))

            connection.execute("""
                UPDATE parking_slots
                SET status = 'Occupied'
                WHERE slot_number = ?
            """, (
                slot_number,
            ))

            connection.commit()

            waiting_queue.popleft()

        except Exception:

            connection.rollback()
            return

        finally:

            connection.close()


# ==================================================
# SEARCH VEHICLE
# ==================================================

def search_vehicle(vehicle_number):

    connection = get_db_connection()

    try:

        vehicle_number = (
            vehicle_number.strip().upper()
        )

        vehicle = connection.execute("""
            SELECT *
            FROM vehicles
            WHERE vehicle_number = ?
        """, (
            vehicle_number,
        )).fetchone()

        if vehicle is None:

            return {
                "success": False,
                "message": "Vehicle not found."
            }

        active = connection.execute("""
            SELECT *
            FROM parking_records
            WHERE vehicle_id = ?
            AND exit_time IS NULL
            ORDER BY id DESC
            LIMIT 1
        """, (
            vehicle["id"],
        )).fetchone()

        return {
            "success": True,
            "vehicle_number":
                vehicle["vehicle_number"],
            "owner_name":
                vehicle["owner_name"],
            "vehicle_type":
                vehicle["vehicle_type"],
            "parked":
                active is not None,
            "slot_number":
                active["slot_number"]
                if active else None,
            "entry_time":
                active["entry_time"]
                if active else None
        }

    finally:

        connection.close()


# ==================================================
# ROUTES
# ==================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# -----------------------------
# ENTRY
# -----------------------------

@app.route("/entry", methods=["POST"])
def entry():

    data = request.get_json()

    if not data:

        return jsonify({
            "success": False,
            "message": "No data received."
        })

    result = enter_vehicle(
        data.get("vehicle_number", ""),
        data.get("owner_name", ""),
        data.get("vehicle_type", "")
    )

    return jsonify(result)


# -----------------------------
# EXIT
# -----------------------------

@app.route("/exit", methods=["POST"])
def exit_route():

    data = request.get_json()

    if not data:

        return jsonify({
            "success": False,
            "message": "No data received."
        })

    vehicle_number = data.get(
        "vehicle_number",
        ""
    )

    payment_method = data.get(
        "payment_method",
        ""
    )

    if not vehicle_number:

        return jsonify({
            "success": False,
            "message":
                "Vehicle number is required."
        })

    if not payment_method:

        return jsonify({
            "success": False,
            "message":
                "Payment method is required."
        })

    result = exit_vehicle(
        vehicle_number,
        payment_method
    )

    return jsonify(result)


# -----------------------------
# SEARCH
# -----------------------------

@app.route("/search", methods=["GET"])
def search():

    vehicle_number = request.args.get(
        "vehicle_number",
        ""
    )

    result = search_vehicle(
        vehicle_number
    )

    return jsonify(result)


# -----------------------------
# PARKED VEHICLES
# -----------------------------

@app.route("/vehicles", methods=["GET"])
def vehicles():

    connection = get_db_connection()

    rows = connection.execute("""
        SELECT
            v.vehicle_number,
            v.owner_name,
            v.vehicle_type,
            p.slot_number,
            p.entry_time
        FROM parking_records p
        JOIN vehicles v
        ON p.vehicle_id = v.id
        WHERE p.exit_time IS NULL
        ORDER BY p.entry_time
    """).fetchall()

    connection.close()

    return jsonify([
        dict(row)
        for row in rows
    ])


# -----------------------------
# SLOTS
# -----------------------------

@app.route("/slots", methods=["GET"])
def slots():

    connection = get_db_connection()

    rows = connection.execute("""
        SELECT
            slot_number,
            status
        FROM parking_slots
        ORDER BY id
    """).fetchall()

    connection.close()

    return jsonify([
        dict(row)
        for row in rows
    ])


# -----------------------------
# QUEUE
# -----------------------------

@app.route("/queue", methods=["GET"])
def queue():

    return jsonify({
        "queue": list(waiting_queue),
        "count": len(waiting_queue)
    })


# -----------------------------
# GET RATE
# -----------------------------

@app.route("/rate", methods=["GET"])
def get_rate():

    return jsonify({
        "success": True,
        "rate": get_cost_per_minute()
    })


# -----------------------------
# UPDATE RATE
# -----------------------------

@app.route("/rate", methods=["POST"])
def update_rate():

    data = request.get_json()

    if not data:

        return jsonify({
            "success": False,
            "message": "No data received."
        })

    try:

        new_rate = float(
            data.get("rate")
        )

        if new_rate < 0:

            return jsonify({
                "success": False,
                "message":
                    "Rate cannot be negative."
            })

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "message":
                "Please enter a valid rate."
        })

    return jsonify(
        set_cost_per_minute(new_rate)
    )


# -----------------------------
# PAYMENT HISTORY
# -----------------------------

@app.route("/payments", methods=["GET"])
def payments():

    connection = get_db_connection()

    rows = connection.execute("""
        SELECT
            p.id,
            v.vehicle_number,
            p.amount,
            p.payment_method,
            p.payment_status,
            p.payment_reference,
            p.payment_time
        FROM payments p
        JOIN parking_records r
        ON p.parking_record_id = r.id
        JOIN vehicles v
        ON r.vehicle_id = v.id
        ORDER BY p.id DESC
    """).fetchall()

    connection.close()

    return jsonify([
        dict(row)
        for row in rows
    ])


# -----------------------------
# BARRIER STATUS
# -----------------------------

@app.route("/barrier", methods=["GET"])
def barrier():

    return jsonify({
        "success": True,
        "barrier": barrier_state
    })


# ==================================================
# START SERVER
# ==================================================

if __name__ == "__main__":

    from database import cre
