
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR

from sqlalchemy import text

from config.db_config import engine
from config.settings import RANDOM_SEED


SIMULATION_START = datetime(2025, 1, 1)
SIMULATION_END = datetime(2026, 11, 12, 23, 59, 59)
TIER_EFFECTIVE_DATE = datetime(2026, 1, 1)


def calculate_points(net_amount, earning_rate):
    spend = Decimal(str(net_amount))
    rate = Decimal(str(earning_rate))

    return int(
        (spend / Decimal("100") * rate).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )


def load_tiers(connection):
    rows = connection.execute(
        text("""
            SELECT
                tier_id,
                tier_name,
                minimum_qualifying_spend,
                earning_rate
            FROM tier
            WHERE tier_status = 'ACTIVE'
            ORDER BY minimum_qualifying_spend
        """)
    ).mappings().all()

    if not rows:
        raise ValueError("No active tiers found.")

    return rows


def get_tier_for_spend(tiers, qualifying_spend, order_date):
    if order_date < TIER_EFFECTIVE_DATE:
        return next(
            tier for tier in tiers
            if tier["tier_name"] == "BRONZE"
        )

    eligible_tiers = [
        tier for tier in tiers
        if Decimal(str(tier["minimum_qualifying_spend"]))
        <= qualifying_spend
    ]

    if not eligible_tiers:
        raise ValueError(
            f"No eligible tier for qualifying spend {qualifying_spend}"
        )

    return eligible_tiers[-1]


def process_accruals():
    print("=" * 55)
    print("LOYALTY POINTS ACCRUAL - CORRECTED PREVIEW")
    print("=" * 55)
    print(f"Random seed reference: {RANDOM_SEED}")

    with engine.connect() as connection:

        transaction_count = connection.execute(
            text("SELECT COUNT(*) FROM pointstransaction")
        ).scalar_one()

        lot_count = connection.execute(
            text("SELECT COUNT(*) FROM pointslot")
        ).scalar_one()

        if transaction_count > 0 or lot_count > 0:
            raise RuntimeError(
                "Points transactions or lots already exist. "
                "Preview stopped to protect existing data."
            )

        tiers = load_tiers(connection)

        orders = connection.execute(
            text("""
                SELECT
                    o.order_id,
                    o.order_date,
                    o.net_amount,
                    a.account_id,
                    a.qualifying_spend
                FROM orders o
                JOIN loyaltyaccount a
                    ON a.customer_id = o.customer_id
                WHERE o.order_status IN (
                    'PAID',
                    'RETURNED',
                    'PARTIALLY_RETURNED'
                )
                  AND o.order_date >= :start_date
                  AND o.order_date <= :end_date
                  AND a.account_status = 'ACTIVE'
                ORDER BY o.order_date, o.order_id
            """),
            {
                "start_date": SIMULATION_START,
                "end_date": SIMULATION_END,
            },
        ).mappings().all()

        print(f"\nEligible orders found: {len(orders):,}")

        # Tier qualification starts fresh on 1 January 2026.
        spend_by_account = {}
        tier_counts = {
            "BRONZE": 0,
            "SILVER": 0,
            "GOLD": 0,
            "PLATINUM": 0,
        }

        preview_count = 0
        zero_point_count = 0
        total_points = 0
        total_2025_points = 0
        total_2026_points = 0

        for order in orders:
            account_id = order["account_id"]
            order_date = order["order_date"]
            net_amount = Decimal(str(order["net_amount"]))

            if order_date < TIER_EFFECTIVE_DATE:
                # 2025 purchases earn Bronze points.
                qualifying_spend = Decimal("0")
            else:
                if account_id not in spend_by_account:
                    spend_by_account[account_id] = Decimal("0")

                qualifying_spend = spend_by_account[account_id]

            tier = get_tier_for_spend(
                tiers,
                qualifying_spend,
                order_date,
            )

            points = calculate_points(
                net_amount,
                tier["earning_rate"],
            )

            if order_date >= TIER_EFFECTIVE_DATE:
                # Add this order's spend after determining its tier.
                spend_by_account[account_id] += net_amount
                total_2026_points += points
            else:
                total_2025_points += points

            if points > 0:
                preview_count += 1
                total_points += points
                tier_counts[tier["tier_name"]] += 1
            else:
                zero_point_count += 1

        print("\nPREVIEW RESULTS")
        print("-" * 55)
        print(f"Orders earning positive points: {preview_count:,}")
        print(f"Orders earning zero points: {zero_point_count:,}")
        print(f"Total points: {total_points:,}")
        print(f"2025 points: {total_2025_points:,}")
        print(f"2026 points: {total_2026_points:,}")

        print("\nORDERS BY EARNING TIER")
        for tier_name, count in tier_counts.items():
            print(f"{tier_name}: {count:,}")

        print("\nDATABASE CHANGES")
        print("Transactions inserted: 0")
        print("Points lots created: 0")
        print("Account balances updated: 0")
        print("Rule applications inserted: 0")

        print("\nCorrected preview completed.")
        print("No database records were modified.")


if __name__ == "__main__":
    process_accruals()
