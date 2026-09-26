import sqlite3


def create_database():
    connection = sqlite3.connect("parking.db")
    cursor = connection.cursor()

    # -----------------------------
    # VEHICLES
    # -----------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_number TEXT UNIQUE NOT NULL,
            owner_name TEXT NOT NULL,
            vehicle_type TEXT NOT NULL
        )
    """)

    # -----------------------------
    # PARKING SLOTS
    # -----------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parking_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_number TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL
        )
    """)

    # -----------------------------
    # PARKING RECORDS
    # -----------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parking_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL,
            slot_number TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            duration_minutes INTEGER,
            cost REAL,
            FOREIGN KEY (vehicle_id)
                REFERENCES vehicles(id)
        )
    """)

    # -----------------------------
    # PARKING SETTINGS
    # -----------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parking_settings (
            id INTEGER PRIMARY KEY,
            cost_per_minute REAL NOT NULL
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO parking_settings
        (id, cost_per_minute)
        VALUES (1, 1)
    """)

    # -----------------------------
    # PAYMENTS
    # -----------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parking_record_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            payment_reference TEXT,
            payment_time TEXT NOT NULL,
            FOREIGN KEY (parking_record_id)
                REFERENCES parking_records(id)
        )
    """)

    # -----------------------------
    # CREATE 50 PARKING SLOTS
    # -----------------------------

    for i in range(1, 51):

        slot_number = f"P{i:02d}"

        cursor.execute("""
            INSERT OR IGNORE INTO parking_slots
            (slot_number, status)
            VALUES (?, ?)
        """, (slot_number, "Available"))

    connection.commit()
    connection.close()


if __name__ == "__main__":
    create_database()
    print("Database created successfully!")
