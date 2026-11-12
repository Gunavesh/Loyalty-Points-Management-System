
import random
import pandas as pd

from datetime import datetime, timedelta
from sqlalchemy import text

from config.db_config import engine
from config.settings import ORDER_COUNT, RANDOM_SEED


def generate_orders(count=ORDER_COUNT):
    """Generate reproducible synthetic orders for existing customers."""

    rng = random.Random(RANDOM_SEED)

    with engine.connect() as connection:
        customers = pd.read_sql(
            text("""
                SELECT customer_id
                FROM customer
                ORDER BY customer_id
            """),
            connection
        )

    if customers.empty:
        raise ValueError("No customers found. Load customers first.")

    customer_ids = customers["customer_id"].tolist()

    start_date = datetime(2025, 1, 1)
    end_date = datetime(2026, 11, 12)

    orders = []

    days_range = (end_date - start_date).days

    for number in range(1, count + 1):
        customer_id = rng.choice(customer_ids)

        order_date = start_date + timedelta(
            days=rng.randint(0, days_range),
            seconds=rng.randint(0, 86399)
        )

        gross_amount = round(rng.uniform(300, 15000), 2)

        discount_amount = round(
            gross_amount * rng.uniform(0, 0.20), 2
        )

        net_amount = round(gross_amount - discount_amount, 2)

        order_status = rng.choices(
            [
                "PAID",
                "CANCELLED",
                "RETURNED",
                "PARTIALLY_RETURNED",
                "PLACED"
            ],
            weights=[75, 5, 7, 5, 8],
            k=1
        )[0]

        orders.append({
            "order_id": f"ORD-2026-{number:06d}",
            "customer_id": customer_id,
            "order_date": order_date,
            "order_status": order_status,
            "gross_amount": gross_amount,
            "discount_amount": discount_amount,
            "net_amount": net_amount,
            "currency": "INR"
        })

    return pd.DataFrame(orders)


def save_orders():
    df = generate_orders()

    if df["order_id"].duplicated().any():
        raise ValueError("Duplicate order IDs found.")

    if (df["net_amount"] < 0).any():
        raise ValueError("Negative order amount found.")

    reconciliation = (
        df["gross_amount"] - df["discount_amount"]
    ).round(2)

    if not reconciliation.equals(df["net_amount"]):
        raise ValueError("Order amount reconciliation failed.")

    records = df.to_dict(orient="records")

    with engine.begin() as connection:

        existing_count = connection.execute(
            text("SELECT COUNT(*) FROM orders")
        ).scalar_one()

        if existing_count > 0:
            raise ValueError(
                f"Orders table already contains {existing_count} records. "
                "Loading stopped to prevent duplicate insertion."
            )

        insert_query = text("""
            INSERT INTO orders (
                order_id,
                customer_id,
                order_date,
                order_status,
                gross_amount,
                discount_amount,
                net_amount,
                currency
            )
            VALUES (
                :order_id,
                :customer_id,
                :order_date,
                :order_status,
                :gross_amount,
                :discount_amount,
                :net_amount,
                :currency
            )
        """)

        for start in range(0, len(records), 1000):
            batch = records[start:start + 1000]
            connection.execute(insert_query, batch)

    print("ORDER GENERATION SUCCESSFUL")
    print("Total orders:", len(df))
    print("Unique order IDs:", df["order_id"].nunique())
    print("Duplicate order IDs:", df["order_id"].duplicated().sum())
    print("Total gross amount:", round(df["gross_amount"].sum(), 2))
    print("Total discounts:", round(df["discount_amount"].sum(), 2))
    print("Total net amount:", round(df["net_amount"].sum(), 2))

    print("\nOrder status distribution:")
    print(df["order_status"].value_counts())


if __name__ == "__main__":
    save_orders()
