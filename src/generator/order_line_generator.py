
import random
from decimal import Decimal
import pandas as pd
from sqlalchemy import text

from config.db_config import engine
from config.settings import RANDOM_SEED


PRODUCTS = [
    ("PRD-001", "Electronics"),
    ("PRD-002", "Fashion"),
    ("PRD-003", "Home and Kitchen"),
    ("PRD-004", "Beauty"),
    ("PRD-005", "Sports"),
    ("PRD-006", "Books"),
    ("PRD-007", "Grocery"),
    ("PRD-008", "Accessories"),
    ("PRD-009", "Footwear"),
    ("PRD-010", "Toys"),
]


def to_cents(amount):
    """Convert a money amount into integer paise/cents."""
    return int(
        (Decimal(str(amount)) * 100).quantize(Decimal("1"))
    )


def generate_order_lines():
    rng = random.Random(RANDOM_SEED)

    with engine.connect() as connection:
        orders = pd.read_sql(
            text("""
                SELECT order_id, net_amount
                FROM orders
                ORDER BY order_id
            """),
            connection
        )

    records = []

    for order in orders.itertuples(index=False):
        total_cents = to_cents(order.net_amount)

        # Divide each order into exactly three positive line amounts.
        first = rng.randint(1, total_cents - 2)
        second = rng.randint(1, total_cents - first - 1)
        third = total_cents - first - second

        for line_cents in (first, second, third):
            quantity = rng.randint(1, 3)

            # Round unit price UP so the discount can never be negative.
            unit_price_cents = (
                line_cents + quantity - 1
            ) // quantity

            discount_cents = (
                unit_price_cents * quantity - line_cents
            )

            unit_price = Decimal(unit_price_cents) / 100
            discount = Decimal(discount_cents) / 100
            line_net = Decimal(line_cents) / 100

            product_code, product_name = rng.choice(PRODUCTS)

            records.append({
                "order_id": order.order_id,
                "product_code": product_code,
                "product_name": product_name,
                "quantity": quantity,
                "unit_price": unit_price,
                "discount_amount": discount,
                "line_net_amount": line_net
            })

    return pd.DataFrame(records)


def save_order_lines():
    lines = generate_order_lines()

    if lines.empty:
        raise ValueError("No order lines were generated.")

    if lines["discount_amount"].lt(0).any():
        raise ValueError("Negative discount detected.")

    if lines["quantity"].le(0).any():
        raise ValueError("Invalid quantity detected.")

    calculated = (
        lines["unit_price"] * lines["quantity"]
        - lines["discount_amount"]
    ).round(2)

    if not calculated.equals(lines["line_net_amount"].round(2)):
        raise ValueError("Order-line arithmetic validation failed.")

    with engine.begin() as connection:
        existing_count = connection.execute(
            text("SELECT COUNT(*) FROM orderline")
        ).scalar_one()

        if existing_count > 0:
            raise ValueError(
                f"Orderline already contains {existing_count} rows. "
                "Stopping to prevent duplicate insertion."
            )

        records = lines.to_dict(orient="records")

        insert_query = text("""
            INSERT INTO orderline (
                order_id,
                product_code,
                product_name,
                quantity,
                unit_price,
                discount_amount,
                line_net_amount
            )
            VALUES (
                :order_id,
                :product_code,
                :product_name,
                :quantity,
                :unit_price,
                :discount_amount,
                :line_net_amount
            )
        """)

        batch_size = 1000

        for start in range(0, len(records), batch_size):
            connection.execute(
                insert_query,
                records[start:start + batch_size]
            )

    print("ORDER LINE GENERATION SUCCESSFUL")
    print("Total order lines:", len(lines))
    print("Unique orders:", lines["order_id"].nunique())
    print("Unique products:", lines["product_code"].nunique())
    print("Negative discounts:", (lines["discount_amount"] < 0).sum())
    print("Invalid quantities:", (lines["quantity"] <= 0).sum())
    print("Arithmetic validation: PASSED")


if __name__ == "__main__":
    save_order_lines()
