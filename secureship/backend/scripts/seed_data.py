"""
Seed the database with mock customers, shipments, and packages.
Re-runnable: clears existing data before inserting.

Usage:
    docker-compose exec backend python scripts/seed_data.py
"""
import os
import sys
import uuid
import random
from datetime import date, timedelta, datetime, timezone

# Allow running from repo root or from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg2
from faker import Faker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://secureship:secureship@localhost:5432/secureship",
)

fake = Faker("en_US")
Faker.seed(42)
random.seed(42)

CARRIERS = ["MockExpress", "SwiftShip", "ParcelPro", "QuickFreight", "DayDelivery"]
STATUSES = ["label_created", "in_transit", "out_for_delivery", "delivered", "exception"]
STATUS_WEIGHTS = [5, 35, 20, 35, 5]  # realistic distribution

PACKAGE_ITEMS = [
    "Laptop", "Headphones", "Running Shoes", "Cookbook", "Bluetooth Speaker",
    "Winter Jacket", "Coffee Maker", "Phone Case", "Yoga Mat", "Desk Lamp",
    "Sunglasses", "Water Bottle", "Backpack", "Watch", "Portable Charger",
]


def random_tracking_number(carrier: str) -> str:
    prefix = carrier[:2].upper()
    return f"{prefix}{random.randint(100000000, 999999999)}"


def random_e164() -> str:
    return f"+1{random.randint(2000000000, 9999999999)}"


def random_address() -> str:
    return f"{fake.building_number()} {fake.street_name()}, {fake.city()}, {fake.state_abbr()} {fake.zipcode()}"


def seed(conn):
    cur = conn.cursor()

    # Clear in FK-safe order
    cur.execute("DELETE FROM packages")
    cur.execute("DELETE FROM shipments")
    cur.execute("DELETE FROM chat_sessions")
    cur.execute("DELETE FROM customers")

    # --- Customers (25) ---
    customers = []
    for _ in range(25):
        cid = str(uuid.uuid4())
        customers.append({
            "id": cid,
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "phone_number": random_e164(),
            "address": random_address(),
        })

    cur.executemany(
        "INSERT INTO customers (id, first_name, last_name, phone_number, address) "
        "VALUES (%(id)s, %(first_name)s, %(last_name)s, %(phone_number)s, %(address)s)",
        customers,
    )

    # --- Shipments (50) ---
    today = date.today()
    shipments = []
    for _ in range(50):
        customer = random.choice(customers)
        carrier = random.choice(CARRIERS)
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
        days_offset = random.randint(-10, 14)
        shipments.append({
            "id": str(uuid.uuid4()),
            "customer_id": customer["id"],
            "tracking_number": random_tracking_number(carrier),
            "status": status,
            "carrier": carrier,
            "origin": f"{fake.city()}, {fake.state_abbr()}",
            "destination": customer["address"],
            "estimated_delivery": today + timedelta(days=days_offset),
            "last_update": datetime.now(timezone.utc),
        })

    cur.executemany(
        "INSERT INTO shipments "
        "(id, customer_id, tracking_number, status, carrier, origin, destination, estimated_delivery, last_update) "
        "VALUES (%(id)s, %(customer_id)s, %(tracking_number)s, %(status)s, %(carrier)s, "
        "%(origin)s, %(destination)s, %(estimated_delivery)s, %(last_update)s)",
        shipments,
    )

    # --- Packages (1-3 per shipment) ---
    packages = []
    for shipment in shipments:
        for _ in range(random.randint(1, 3)):
            packages.append({
                "id": str(uuid.uuid4()),
                "shipment_id": shipment["id"],
                "description": random.choice(PACKAGE_ITEMS),
                "weight_kg": round(random.uniform(0.2, 20.0), 2),
                "declared_value": round(random.uniform(10.0, 800.0), 2),
            })

    cur.executemany(
        "INSERT INTO packages (id, shipment_id, description, weight_kg, declared_value) "
        "VALUES (%(id)s, %(shipment_id)s, %(description)s, %(weight_kg)s, %(declared_value)s)",
        packages,
    )

    conn.commit()
    cur.close()

    print(f"Seeded: {len(customers)} customers, {len(shipments)} shipments, {len(packages)} packages")

    # Print a sample for verification
    cur2 = conn.cursor()
    cur2.execute(
        "SELECT c.first_name, c.last_name, c.phone_number, COUNT(s.id) AS shipments "
        "FROM customers c LEFT JOIN shipments s ON s.customer_id = c.id "
        "GROUP BY c.id ORDER BY c.last_name LIMIT 5"
    )
    print("\nSample customers:")
    for row in cur2.fetchall():
        print(f"  {row[0]} {row[1]} | {row[2]} | {row[3]} shipment(s)")

    cur2.execute(
        "SELECT status, COUNT(*) FROM shipments GROUP BY status ORDER BY COUNT(*) DESC"
    )
    print("\nShipment status distribution:")
    for row in cur2.fetchall():
        print(f"  {row[0]:<20} {row[1]}")
    cur2.close()


if __name__ == "__main__":
    conn = psycopg2.connect(DATABASE_URL)
    try:
        seed(conn)
    finally:
        conn.close()
