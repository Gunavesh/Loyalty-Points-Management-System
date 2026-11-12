
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_FLOOR

from sqlalchemy import text

from config.db_config import engine
from config.settings import RANDOM_SEED


SIMULATION_START = datetime(2025, 1, 1)
SIMULATION_END = datetime(2026, 11, 12, 23, 59, 59)
TIER_EFFECTIVE_DATE = datetime(2026, 1, 1)

ELIGIBLE_STATUSES = ("PAID", "RETURNED", "PARTIALLY_RETURNED")


def calculate_points(amount, rate):
    return int(
        (
            Decimal(str(amount)) / Decimal("100")
            * Decimal(str(rate))
        ).to_integral_value(rounding=ROUND_FLOOR)
    )


def allocate_points(points, lines):
    total = sum(
        Decimal(str(line["line_net_amount"]))
        for line in lines
    )

    if total <= 0:
        raise ValueError("Order line total must be positive.")

    result = []
    allocated = 0

    for line in lines:
        exact = (
            Decimal(points)
            * Decimal(str(line["line_net_amount"]))
            / total
        )

        base = int(exact.to_integral_value(rounding=ROUND_FLOOR))

        result.append({
            "line_id": line["order_line_id"],
            "points": base,
            "fraction": exact - base
        })

        allocated += base

    remaining = points - allocated

    ranked = sorted(
        result,
        key=lambda item: (-item["fraction"], item["line_id"])
    )

    for item in ranked[:remaining]:
        item["points"] += 1

    return {
        item["line_id"]: item["points"]
        for item in result
    }


def calculate_reversal(
    allocated,
    purchased,
    returned,
    previous
):
    if purchased <= 0 or returned < 0 or returned > purchased:
        raise ValueError("Invalid return quantity.")

    target = allocated * returned // purchased

    if returned == purchased:
        target = allocated

    additional = target - previous

    if additional < 0:
        raise ValueError("Invalid previous reversal.")

    return additional


def next_transaction_id(sequence):
    return f"PTS-2026-{sequence:08d}"


def load_data(connection):

    tiers = [
        dict(row)
        for row in connection.execute(text("""
            SELECT
                tier_id,
                tier_name,
                minimum_qualifying_spend,
                earning_rate
            FROM tier
            WHERE tier_status = 'ACTIVE'
            ORDER BY minimum_qualifying_spend
        """)).mappings()
    ]

    orders = [
        dict(row)
        for row in connection.execute(text("""
            SELECT
                o.order_id,
                o.customer_id,
                o.order_date,
                o.net_amount,
                a.account_id
            FROM orders o
            JOIN loyaltyaccount a
                ON a.customer_id = o.customer_id
            WHERE o.order_status IN (
                'PAID',
                'RETURNED',
                'PARTIALLY_RETURNED'
            )
            AND o.order_date BETWEEN :start_date AND :end_date
            AND a.account_status = 'ACTIVE'
            ORDER BY o.order_date, o.order_id
        """), {
            "start_date": SIMULATION_START,
            "end_date": SIMULATION_END
        }).mappings()
    ]

    lines = [
        dict(row)
        for row in connection.execute(text("""
            SELECT
                ol.order_line_id,
                ol.order_id,
                ol.quantity,
                ol.line_net_amount
            FROM orderline ol
            JOIN orders o
                ON o.order_id = ol.order_id
            WHERE o.order_status IN (
                'PAID',
                'RETURNED',
                'PARTIALLY_RETURNED'
            )
            AND o.order_date BETWEEN :start_date AND :end_date
            ORDER BY ol.order_id, ol.order_line_id
        """), {
            "start_date": SIMULATION_START,
            "end_date": SIMULATION_END
        }).mappings()
    ]

    returns = [
        dict(row)
        for row in connection.execute(text("""
            SELECT
                r.return_id,
                r.return_date,
                r.order_id,
                rl.return_line_id,
                rl.order_line_id,
                rl.returned_quantity,
                rl.refund_amount,
                ol.quantity AS purchased_quantity,
                o.order_date,
                a.account_id
            FROM `returns` r
            JOIN returnline rl
                ON rl.return_id = r.return_id
            JOIN orderline ol
                ON ol.order_line_id = rl.order_line_id
            JOIN orders o
                ON o.order_id = r.order_id
            JOIN loyaltyaccount a
                ON a.customer_id = o.customer_id
            WHERE r.return_status = 'COMPLETED'
            AND a.account_status = 'ACTIVE'
            ORDER BY r.return_date, rl.return_line_id
        """)).mappings()
    ]

    return tiers, orders, lines, returns


def select_tier(tiers, spend, order_date):

    if order_date < TIER_EFFECTIVE_DATE:
        return tiers[0]

    eligible = [
        tier for tier in tiers
        if Decimal(str(tier["minimum_qualifying_spend"])) <= spend
    ]

    return eligible[-1] if eligible else tiers[0]


def process_ledger():

    print("=" * 60)
    print("LOYALTY POINTS LEDGER PROCESSOR")
    print("Seed:", RANDOM_SEED)
    print("=" * 60)

    with engine.begin() as connection:

        # Prevent duplicate processing.
        existing = connection.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM pointstransaction) +
                (SELECT COUNT(*) FROM pointslot) +
                (SELECT COUNT(*) FROM pointsallocation)
        """)).scalar_one()

        if existing:
            raise RuntimeError(
                "Points ledger is not empty. Processing stopped "
                "to prevent duplicate records."
            )

        tiers, orders, lines, returns = load_data(connection)

        if not tiers:
            raise RuntimeError("No active tiers found.")

        lines_by_order = defaultdict(list)

        for line in lines:
            lines_by_order[line["order_id"]].append(line)

        orders_by_id = {
            order["order_id"]: order
            for order in orders
        }

        valid_returns = []

        for item in returns:

            original = orders_by_id.get(item["order_id"])

            if original is None:
                continue

            if item["return_date"] < original["order_date"]:
                raise ValueError(
                    "Return occurs before original order."
                )

            valid_returns.append(item)

        # Create chronological order and return events.
        events = []

        for order in orders:
            events.append((
                order["order_date"],
                0,
                order["order_id"],
                order
            ))

        for item in valid_returns:
            events.append((
                item["return_date"],
                1,
                item["return_line_id"],
                item
            ))

        events.sort(
            key=lambda event: (
                event[0],
                event[1],
                event[2]
            )
        )

        qualifying_spend = defaultdict(Decimal)
        order_remaining_spend = {}

        line_allocations = {}
        line_returned_qty = defaultdict(int)
        line_reversed = defaultdict(int)

        line_lot_ids = {}
        line_accrual_transactions = {}

        account_balance = defaultdict(int)

        transaction_sequence = 1

        earned_total = 0
        reversed_total = 0

        accrual_count = 0
        reversal_count = 0
        allocation_count = 0

        # Find an active earning rule for each tier rate.
        earning_rules = {}

        for tier in tiers:

            rule = connection.execute(text("""
                SELECT rule_id
                FROM rule
                WHERE rule_type = 'EARNING'
                  AND rule_status = 'ACTIVE'
                  AND rule_value = :rate
                ORDER BY rule_id
                LIMIT 1
            """), {
                "rate": tier["earning_rate"]
            }).scalar()

            if rule is None:
                raise RuntimeError(
                    f"No active earning rule for tier "
                    f"{tier['tier_name']}."
                )

            earning_rules[str(tier["earning_rate"])] = rule

        # Process all events chronologically.
        for event_date, event_type, event_id, record in events:

            # --------------------------------------------------
            # ORDER ACCRUAL
            # --------------------------------------------------
            if event_type == 0:

                order = record
                order_id = order["order_id"]
                account_id = order["account_id"]

                order_lines = lines_by_order.get(order_id, [])

                if not order_lines:
                    raise RuntimeError(
                        f"Order {order_id} has no order lines."
                    )

                spend_before_order = (
                    qualifying_spend[account_id]
                    if event_date >= TIER_EFFECTIVE_DATE
                    else Decimal("0")
                )

                tier = select_tier(
                    tiers,
                    spend_before_order,
                    event_date
                )

                points = calculate_points(
                    order["net_amount"],
                    tier["earning_rate"]
                )

                allocations = allocate_points(
                    points,
                    order_lines
                )

                if sum(allocations.values()) != points:
                    raise RuntimeError(
                        "Point allocation mismatch."
                    )

                if points > 0:

                    transaction_id = next_transaction_id(
                        transaction_sequence
                    )

                    transaction_sequence += 1

                    connection.execute(text("""
                        INSERT INTO pointstransaction
                        (
                            transaction_id,
                            account_id,
                            transaction_type,
                            points_change,
                            transaction_date,
                            order_id,
                            description,
                            idempotency_key
                        )
                        VALUES (
                            :transaction_id,
                            :account_id,
                            'ACCRUAL',
                            :points,
                            :transaction_date,
                            :order_id,
                            :description,
                            :idempotency_key
                        )
                    """), {
                        "transaction_id": transaction_id,
                        "account_id": account_id,
                        "points": points,
                        "transaction_date": event_date,
                        "order_id": order_id,
                        "description": (
                            f"Points earned for order {order_id}"
                        ),
                        "idempotency_key": f"ACCRUAL:{order_id}"
                    })

                    expiry_date = event_date + timedelta(days=365)

                    lot_id = connection.execute(text("""
                        INSERT INTO pointslot
                        (
                            account_id,
                            accrual_transaction_id,
                            original_points,
                            remaining_points,
                            earned_at,
                            expiry_date,
                            lot_status
                        )
                        VALUES (
                            :account_id,
                            :transaction_id,
                            :points,
                            :points,
                            :earned_at,
                            :expiry_date,
                            'ACTIVE'
                        )
                    """), {
                        "account_id": account_id,
                        "transaction_id": transaction_id,
                        "points": points,
                        "earned_at": event_date,
                        "expiry_date": expiry_date
                    }).lastrowid

                    for line_id, allocated in allocations.items():

                        line_allocations[line_id] = allocated
                        line_lot_ids[line_id] = lot_id
                        line_accrual_transactions[line_id] = transaction_id

                    connection.execute(text("""
                        INSERT INTO ruleapplication
                        (
                            rule_id,
                            transaction_id,
                            order_id,
                            applied_at,
                            applied_value,
                            calculation_details
                        )
                        VALUES (
                            :rule_id,
                            :transaction_id,
                            :order_id,
                            :applied_at,
                            :rate,
                            :details
                        )
                    """), {
                        "rule_id": earning_rules[
                            str(tier["earning_rate"])
                        ],
                        "transaction_id": transaction_id,
                        "order_id": order_id,
                        "applied_at": event_date,
                        "rate": tier["earning_rate"],
                        "details": (
                            '{"basis":"net_amount","tier":"'
                            + tier["tier_name"] + '"}'
                        )
                    })

                    account_balance[account_id] += points
                    earned_total += points
                    accrual_count += 1

                else:
                    for line_id, allocated in allocations.items():
                        line_allocations[line_id] = allocated

                if event_date >= TIER_EFFECTIVE_DATE:

                    qualifying_spend[account_id] += Decimal(
                        str(order["net_amount"])
                    )

                    order_remaining_spend[order_id] = Decimal(
                        str(order["net_amount"])
                    )

            # --------------------------------------------------
            # RETURN REVERSAL
            # --------------------------------------------------
            else:

                item = record
                line_id = item["order_line_id"]

                if line_id not in line_allocations:
                    raise RuntimeError(
                        f"Return line {line_id} has no original accrual."
                    )

                cumulative_qty = (
                    line_returned_qty[line_id]
                    + int(item["returned_quantity"])
                )

                additional = calculate_reversal(
                    line_allocations[line_id],
                    int(item["purchased_quantity"]),
                    cumulative_qty,
                    line_reversed[line_id]
                )

                line_returned_qty[line_id] = cumulative_qty
                line_reversed[line_id] += additional

                if additional > 0:

                    transaction_id = next_transaction_id(
                        transaction_sequence
                    )

                    transaction_sequence += 1

                    original_transaction_id = (
                        line_accrual_transactions.get(line_id)
                    )

                    if original_transaction_id is None:
                        raise RuntimeError(
                            f"Original accrual transaction missing "
                            f"for order line {line_id}."
                        )

                    connection.execute(text("""
                        INSERT INTO pointstransaction
                        (
                            transaction_id,
                            account_id,
                            transaction_type,
                            points_change,
                            transaction_date,
                            order_id,
                            reference_transaction_id,
                            return_line_id,
                            description,
                            idempotency_key
                        )
                        VALUES (
                            :transaction_id,
                            :account_id,
                            'RETURN_REVERSAL',
                            :points,
                            :transaction_date,
                            :order_id,
                            :reference_transaction_id,
                            :return_line_id,
                            :description,
                            :idempotency_key
                        )
                    """), {
                        "transaction_id": transaction_id,
                        "account_id": item["account_id"],
                        "points": -additional,
                        "transaction_date": item["return_date"],
                        "order_id": item["order_id"],
                        "reference_transaction_id": original_transaction_id,
                        "return_line_id": item["return_line_id"],
                        "description": (
                            f"Points reversed for return "
                            f"{item['return_id']}"
                        ),
                        "idempotency_key": (
                            f"RETURN_REVERSAL:{item['return_line_id']}"
                        )
                    })

                    lot_id = line_lot_ids.get(line_id)

                    if lot_id is None:
                        raise RuntimeError(
                            f"Original points lot missing for line {line_id}."
                        )

                    # Record the reversal allocation.
                    connection.execute(text("""
                        INSERT INTO pointsallocation
                        (
                            lot_id,
                            transaction_id,
                            allocation_type,
                            points_allocated
                        )
                        VALUES (
                            :lot_id,
                            :transaction_id,
                            'RETURN_REVERSAL',
                            :points
                        )
                    """), {
                        "lot_id": lot_id,
                        "transaction_id": transaction_id,
                        "points": additional
                    })

                    # IMPORTANT:
                    # Update status FIRST. MySQL evaluates UPDATE
                    # assignments from left to right.
                    changed = connection.execute(text("""
                        UPDATE pointslot
                        SET
                            lot_status = CASE
                                WHEN remaining_points = :points
                                THEN 'CONSUMED'
                                ELSE 'PARTIALLY_USED'
                            END,
                            remaining_points =
                                remaining_points - :points
                        WHERE lot_id = :lot_id
                          AND remaining_points >= :points
                    """), {
                        "points": additional,
                        "lot_id": lot_id
                    }).rowcount

                    if changed != 1:
                        raise RuntimeError(
                            "Return reversal exceeds remaining lot "
                            "points. Redemption/debt processing must "
                            "be integrated before this scenario can "
                            "be processed."
                        )

                    account_balance[item["account_id"]] -= additional

                    reversed_total += additional
                    reversal_count += 1
                    allocation_count += 1

                # Adjust qualifying spend for eligible purchases.
                if item["order_date"] >= TIER_EFFECTIVE_DATE:

                    order_id = item["order_id"]

                    remaining = order_remaining_spend.get(
                        order_id,
                        Decimal("0")
                    )

                    reduction = min(
                        Decimal(str(item["refund_amount"])),
                        remaining
                    )

                    order_remaining_spend[order_id] = (
                        remaining - reduction
                    )

                    account_id = item["account_id"]

                    qualifying_spend[account_id] = max(
                        Decimal("0"),
                        qualifying_spend[account_id] - reduction
                    )

        # ------------------------------------------------------
        # UPDATE ACCOUNT BALANCES
        # ------------------------------------------------------
        for account_id in (
            set(account_balance) | set(qualifying_spend)
        ):

            connection.execute(text("""
                UPDATE loyaltyaccount
                SET
                    current_balance = :balance,
                    qualifying_spend = :spend,
                    updated_at = NOW()
                WHERE account_id = :account_id
            """), {
                "balance": account_balance[account_id],
                "spend": qualifying_spend[account_id],
                "account_id": account_id
            })

        # ------------------------------------------------------
        # LEDGER RECONCILIATION
        # ------------------------------------------------------
        mismatch = connection.execute(text("""
            SELECT COUNT(*)
            FROM loyaltyaccount a
            WHERE a.current_balance <> COALESCE(
                (
                    SELECT SUM(t.points_change)
                    FROM pointstransaction t
                    WHERE t.account_id = a.account_id
                ),
                0
            )
        """)).scalar_one()

        if mismatch:
            raise RuntimeError(
                f"Ledger reconciliation failed for "
                f"{mismatch} accounts."
            )

        print("\nPROCESSING COMPLETED")
        print("Eligible orders:", len(orders))
        print("Completed return lines:", len(valid_returns))
        print("Accrual transactions:", accrual_count)
        print("Return reversal transactions:", reversal_count)
        print("Return allocations:", allocation_count)
        print("Points earned:", earned_total)
        print("Points reversed:", reversed_total)
        print("Net points:", earned_total - reversed_total)
        print(
            "Accounts updated:",
            len(set(account_balance) | set(qualifying_spend))
        )
        print("Ledger reconciliation: PASSED")
        print("Database changes: COMMITTED")


if __name__ == "__main__":
    process_ledger()
