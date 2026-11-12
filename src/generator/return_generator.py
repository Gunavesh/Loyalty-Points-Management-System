
import random
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
from sqlalchemy import text

from config.db_config import engine
from config.settings import RANDOM_SEED


RETURN_REASONS = [
    "DAMAGED_PRODUCT",
    "WRONG_PRODUCT",
    "SIZE_OR_FIT_ISSUE",
    "QUALITY_ISSUE",
    "CUSTOMER_CHANGED_MIND",
]

SIMULATION_END = pd.Timestamp("2026-11-12 23:59:59")


def money(value):
    """Round money to two decimal places."""
    return Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )


def generate_returns():
    rng = random.Random(RANDOM_SEED + 100)

    with engine.connect() as connection:
        orders = pd.read_sql(
            text("""
                SELECT
                    o.order_id,
                    o.customer_id,
                    o.order_date,
                    o.order_status
                FROM orders o
                WHERE o.order_status IN (
                    'RETURNED',
                    'PARTIALLY_RETURNED'
                )
                ORDER BY o.order_id
            """),
            connection
        )

        order_lines = pd.read_sql(
            text("""
                SELECT
                    ol.order_line_id,
                    ol.order_id,
                    ol.quantity,
                    ol.line_net_amount
                FROM orderline ol
                ORDER BY ol.order_id, ol.order_line_id
            """),
            connection
        )

    order_map = orders.set_index("order_id").to_dict("index")

    lines_by_order = {
        order_id: group.to_dict("records")
        for order_id, group in order_lines.groupby("order_id")
    }

    return_records = []
    return_line_records = []

    return_number = 1

    for order_id, order in order_map.items():
        lines = lines_by_order.get(order_id, [])

        if not lines:
            continue

        order_date = pd.Timestamp(order["order_date"])

        # Skip orders dated after the simulation end.
        if order_date > SIMULATION_END:
            continue

        selected_lines = rng.sample(
            lines,
            k=rng.randint(1, len(lines))
        )

        return_id = f"RET-2026-{return_number:06d}"
        return_number += 1

        # Keep every return after its order and within simulation dates.
        latest_return_date = min(
            order_date + pd.Timedelta(days=30),
            SIMULATION_END
        )

        days_available = max(
            0,
            (latest_return_date - order_date).days
        )

        return_date = (
            order_date
            + pd.Timedelta(days=rng.randint(0, days_available))
        )

        return_status = rng.choices(
            ["COMPLETED", "APPROVED", "REQUESTED", "REJECTED"],
            weights=[75, 10, 10, 5],
            k=1
        )[0]

        return_records.append({
            "return_id": return_id,
            "order_id": order_id,
            "customer_id": int(order["customer_id"]),
            "return_date": return_date.to_pydatetime(),
            "return_status": return_status,
            "reason": rng.choice(RETURN_REASONS),
        })

        for line in selected_lines:
            original_quantity = int(line["quantity"])

            if original_quantity == 1:
                returned_quantity = 1
            else:
                returned_quantity = rng.randint(
                    1, original_quantity
                )

            original_amount = money(line["line_net_amount"])

            original_cents = int(original_amount * 100)

            refund_cents = (
                original_cents * returned_quantity
                // original_quantity
            )

            if returned_quantity == original_quantity:
                refund_cents = original_cents

            refund_amount = Decimal(refund_cents) / 100

            return_line_records.append({
                "return_id": return_id,
                "order_line_id": int(line["order_line_id"]),
                "returned_quantity": returned_quantity,
                "refund_amount": refund_amount,
            })

    return (
        pd.DataFrame(return_records),
        pd.DataFrame(return_line_records)
    )


def save_returns():
    returns, return_lines = generate_returns()

    if returns.empty:
        raise ValueError("No eligible orders found for return generation.")

    if return_lines.empty:
        raise ValueError("No return lines were generated.")

    if returns["return_id"].duplicated().any():
        raise ValueError("Duplicate return IDs detected.")

    if return_lines["return_id"].isna().any():
        raise ValueError("A return line has no return ID.")

    if return_lines["returned_quantity"].le(0).any():
        raise ValueError("Invalid returned quantity detected.")

    if return_lines["refund_amount"].lt(0).any():
        raise ValueError("Negative refund detected.")

    with engine.begin() as connection:
        existing_returns = connection.execute(
            text("SELECT COUNT(*) FROM returns")
        ).scalar_one()

        existing_lines = connection.execute(
            text("SELECT COUNT(*) FROM returnline")
        ).scalar_one()

        if existing_returns > 0 or existing_lines > 0:
            raise ValueError(
                "Return tables already contain data. "
                "Stopping to prevent duplicate insertion."
            )

        connection.execute(
            text("""
                INSERT INTO returns (
                    return_id,
                    order_id,
                    customer_id,
                    return_date,
                    return_status,
                    reason
                )
                VALUES (
                    :return_id,
                    :order_id,
                    :customer_id,
                    :return_date,
                    :return_status,
                    :reason
                )
            """),
            returns.to_dict(orient="records")
        )

        connection.execute(
            text("""
                INSERT INTO returnline (
                    return_id,
                    order_line_id,
                    returned_quantity,
                    refund_amount
                )
                VALUES (
                    :return_id,
                    :order_line_id,
                    :returned_quantity,
                    :refund_amount
                )
            """),
            return_lines.to_dict(orient="records")
        )

    print("RETURN GENERATION SUCCESSFUL")
    print("Total returns:", len(returns))
    print("Total return lines:", len(return_lines))
    print(
        "Duplicate return IDs:",
        returns["return_id"].duplicated().sum()
    )
    print(
        "Invalid returned quantities:",
        (return_lines["returned_quantity"] <= 0).sum()
    )
    print(
        "Negative refunds:",
        (return_lines["refund_amount"] < 0).sum()
    )
    print(
        "Returns after simulation end:",
        (returns["return_date"] > SIMULATION_END).sum()
    )

    print("\nReturn status distribution:")
    print(returns["return_status"].value_counts())


if __name__ == "__main__":
    save_returns()
