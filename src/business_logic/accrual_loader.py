
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR

from sqlalchemy import text

from config.db_config import engine
from config.settings import RANDOM_SEED


# ============================================================
# CONFIGURATION
# ============================================================

SIMULATION_START = datetime(2025, 1, 1)
SIMULATION_END = datetime(2026, 11, 12, 23, 59, 59)
TIER_EFFECTIVE_DATE = datetime(2026, 1, 1)

ELIGIBLE_ORDER_STATUSES = (
    "PAID",
    "RETURNED",
    "PARTIALLY_RETURNED"
)

DRY_RUN_ONLY = True


# ============================================================
# POINT CALCULATIONS
# ============================================================

def calculate_points(net_amount, earning_rate):
    spend = Decimal(str(net_amount))
    rate = Decimal(str(earning_rate))

    return int(
        (spend / Decimal("100") * rate).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )


def allocate_points_to_lines(order_points, order_lines):
    """
    Allocate order-level points proportionally across order lines.
    Largest-remainder method ensures the exact total is preserved.
    """

    if not order_lines:
        raise ValueError("Order has no order lines.")

    total_amount = sum(
        Decimal(str(line["line_net_amount"]))
        for line in order_lines
    )

    if total_amount <= 0:
        raise ValueError("Order line total must be positive.")

    allocations = []
    allocated_total = 0

    for line in order_lines:
        amount = Decimal(str(line["line_net_amount"]))

        if amount < 0:
            raise ValueError("Negative order-line amount found.")

        exact_points = (
            Decimal(order_points) * amount / total_amount
        )

        base_points = int(
            exact_points.to_integral_value(rounding=ROUND_FLOOR)
        )

        allocations.append({
            "order_line_id": line["order_line_id"],
            "allocated_points": base_points,
            "fraction": exact_points - base_points
        })

        allocated_total += base_points

    remaining = order_points - allocated_total

    ranked = sorted(
        allocations,
        key=lambda item: (
            -item["fraction"],
            item["order_line_id"]
        )
    )

    for item in ranked[:remaining]:
        item["allocated_points"] += 1

    return {
        item["order_line_id"]: item["allocated_points"]
        for item in allocations
    }


def calculate_reversal(
    allocated_points,
    purchased_quantity,
    cumulative_returned_quantity,
    previously_reversed_points
):
    """
    Calculate the additional reversal for a return line.

    Cumulative calculation prevents rounding errors across
    multiple partial returns.
    """

    if purchased_quantity <= 0:
        raise ValueError("Purchased quantity must be positive.")

    if cumulative_returned_quantity > purchased_quantity:
        raise ValueError("Returned quantity exceeds purchased quantity.")

    if cumulative_returned_quantity < 0:
        raise ValueError("Returned quantity cannot be negative.")

    target = (
        allocated_points * cumulative_returned_quantity
    ) // purchased_quantity

    if cumulative_returned_quantity == purchased_quantity:
        target = allocated_points

    additional = target - previously_reversed_points

    if additional < 0:
        raise ValueError("Previous reversal amount is inconsistent.")

    return additional


# ============================================================
# DATABASE READ FUNCTIONS
# ============================================================

def load_tiers(connection):
    query = text("""
        SELECT
            tier_id,
            tier_name,
            minimum_qualifying_spend,
            earning_rate
        FROM tier
        WHERE tier_status = 'ACTIVE'
        ORDER BY minimum_qualifying_spend
    """)

    return [
        dict(row)
        for row in connection.execute(query).mappings()
    ]


def load_orders(connection):
    query = text("""
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
    """)

    return [
        dict(row)
        for row in connection.execute(
            query,
            {
                "start_date": SIMULATION_START,
                "end_date": SIMULATION_END
            }
        ).mappings()
    ]


def load_order_lines(connection):
    query = text("""
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
    """)

    return [
        dict(row)
        for row in connection.execute(
            query,
            {
                "start_date": SIMULATION_START,
                "end_date": SIMULATION_END
            }
        ).mappings()
    ]


def load_completed_returns(connection):
    query = text("""
        SELECT
            r.return_id,
            r.return_date,
            r.order_id,
            rl.return_line_id,
            rl.order_line_id,
            rl.returned_quantity,
            rl.refund_amount,
            ol.quantity AS purchased_quantity,
            ol.line_net_amount,
            o.customer_id,
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
    """)

    return [
        dict(row)
        for row in connection.execute(query).mappings()
    ]


# ============================================================
# TIER SELECTION
# ============================================================

def get_tier_for_spend(tiers, qualifying_spend, order_date):

    if order_date < TIER_EFFECTIVE_DATE:
        return tiers[0]

    eligible = [
        tier for tier in tiers
        if Decimal(str(tier["minimum_qualifying_spend"]))
        <= qualifying_spend
    ]

    if not eligible:
        return tiers[0]

    return eligible[-1]


# ============================================================
# MAIN DRY RUN
# ============================================================

def process_accruals():

    print("=" * 65)
    print("LOYALTY POINTS ACCRUAL AND RETURN REVERSAL")
    print("=" * 65)
    print("Mode: DRY RUN - NO DATABASE CHANGES")
    print("Seed:", RANDOM_SEED)

    with engine.connect() as connection:

        # Safety guard: do not run over an existing ledger.
        existing_transactions = connection.execute(
            text("SELECT COUNT(*) FROM pointstransaction")
        ).scalar_one()

        existing_lots = connection.execute(
            text("SELECT COUNT(*) FROM pointslot")
        ).scalar_one()

        existing_allocations = connection.execute(
            text("SELECT COUNT(*) FROM pointsallocation")
        ).scalar_one()

        if (
            existing_transactions > 0
            or existing_lots > 0
            or existing_allocations > 0
        ):
            raise RuntimeError(
                "Existing points records found. "
                "This dry-run expects an empty points ledger."
            )

        tiers = load_tiers(connection)
        orders = load_orders(connection)
        order_lines = load_order_lines(connection)
        returns = load_completed_returns(connection)

    if not tiers:
        raise RuntimeError("No active tiers found.")

    # Group order lines by order.
    lines_by_order = defaultdict(list)

    for line in order_lines:
        lines_by_order[line["order_id"]].append(line)

    # Only use returns belonging to eligible loaded orders.
    orders_by_id = {
        order["order_id"]: order
        for order in orders
    }

    valid_returns = []
    returns_without_eligible_order = 0

    for returned in returns:

        original_order = orders_by_id.get(returned["order_id"])

        if original_order is None:
            returns_without_eligible_order += 1
            continue

        if returned["return_date"] < original_order["order_date"]:
            raise ValueError(
                f"Return {returned['return_id']} occurred "
                "before its original order."
            )

        valid_returns.append(returned)

    # Build a chronological event stream.
    events = []

    for order in orders:
        events.append((
            order["order_date"],
            0,
            order["order_id"],
            order
        ))

    for returned in valid_returns:
        events.append((
            returned["return_date"],
            1,
            returned["return_line_id"],
            returned
        ))

    events.sort(key=lambda event: (
        event[0],
        event[1],
        event[2]
    ))

    print("\nORDERS LOADED:", len(orders))
    print("ORDER LINES LOADED:", len(order_lines))
    print("COMPLETED RETURN LINES:", len(valid_returns))
    print("RETURNS OUTSIDE ELIGIBLE ORDER SET:",
          returns_without_eligible_order)
    print("CHRONOLOGICAL EVENTS:", len(events))

    # Per-account simulation.
    qualifying_spend = defaultdict(Decimal)
    account_points_earned = defaultdict(int)
    account_points_reversed = defaultdict(int)

    # Original accrual allocation by order line.
    line_allocations = {}
    line_returned_quantities = defaultdict(int)
    line_reversed_points = defaultdict(int)

    # Qualifying spend remaining for each 2026 order.
    qualifying_amount_remaining = {}

    # Order-level tracking.
    order_points = {}

    # Summary counters.
    tier_counts = defaultdict(int)

    total_earned = 0
    total_reversed = 0
    total_refunds = Decimal("0")
    processed_orders = 0
    processed_return_lines = 0
    return_quantity_errors = 0
    missing_order_lines = 0

    for event_date, event_type, event_id, record in events:

        # ----------------------------------------------------
        # ORDER ACCRUAL EVENT
        # ----------------------------------------------------

        if event_type == 0:

            order = record
            order_id = order["order_id"]
            account_id = order["account_id"]
            net_amount = Decimal(str(order["net_amount"]))

            lines = lines_by_order.get(order_id, [])

            if not lines:
                missing_order_lines += 1
                continue

            if event_date < TIER_EFFECTIVE_DATE:
                current_spend = Decimal("0")
            else:
                current_spend = qualifying_spend[account_id]

            tier = get_tier_for_spend(
                tiers,
                current_spend,
                event_date
            )

            points = calculate_points(
                net_amount,
                tier["earning_rate"]
            )

            allocations = allocate_points_to_lines(
                points,
                lines
            )

            for line_id, allocated in allocations.items():
                line_allocations[line_id] = allocated

            order_points[order_id] = points

            total_earned += points
            account_points_earned[account_id] += points

            tier_counts[tier["tier_name"]] += 1
            processed_orders += 1

            # 2026 qualifying spend is updated after choosing
            # the tier for the current order.
            if event_date >= TIER_EFFECTIVE_DATE:
                qualifying_spend[account_id] += net_amount
                qualifying_amount_remaining[order_id] = net_amount

        # ----------------------------------------------------
        # COMPLETED RETURN EVENT
        # ----------------------------------------------------

        else:

            returned = record
            account_id = returned["account_id"]
            order_id = returned["order_id"]
            line_id = returned["order_line_id"]

            if line_id not in line_allocations:
                return_quantity_errors += 1
                continue

            previous_quantity = line_returned_quantities[line_id]

            new_quantity = int(returned["returned_quantity"])

            cumulative_quantity = previous_quantity + new_quantity

            purchased_quantity = int(
                returned["purchased_quantity"]
            )

            if cumulative_quantity > purchased_quantity:
                raise ValueError(
                    f"Returned quantity exceeds purchased quantity "
                    f"for order line {line_id}."
                )

            additional_reversal = calculate_reversal(
                allocated_points=line_allocations[line_id],
                purchased_quantity=purchased_quantity,
                cumulative_returned_quantity=cumulative_quantity,
                previously_reversed_points=line_reversed_points[line_id]
            )

            line_returned_quantities[line_id] = cumulative_quantity
            line_reversed_points[line_id] += additional_reversal

            account_points_reversed[account_id] += additional_reversal
            total_reversed += additional_reversal

            processed_return_lines += 1

            # Use actual stored refund amount.
            refund = Decimal(str(returned["refund_amount"]))
            total_refunds += refund

            # Only returns of 2026 purchases affect 2026
            # qualifying spend. 2025 purchases were not counted.
            original_order_date = returned["order_date"]

            if original_order_date >= TIER_EFFECTIVE_DATE:

                remaining_for_order = qualifying_amount_remaining.get(
                    order_id,
                    Decimal("0")
                )

                spend_reduction = min(
                    refund,
                    remaining_for_order
                )

                qualifying_amount_remaining[order_id] = (
                    remaining_for_order - spend_reduction
                )

                qualifying_spend[account_id] = max(
                    Decimal("0"),
                    qualifying_spend[account_id] - spend_reduction
                )

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------

    allocation_total = sum(line_allocations.values())

    if allocation_total != total_earned:
        raise RuntimeError(
            "Point allocation total does not match earned points."
        )

    if total_reversed > total_earned:
        raise RuntimeError(
            "Total reversals exceed total earned points."
        )

    for line_id, reversed_points in line_reversed_points.items():

        allocated = line_allocations[line_id]

        if reversed_points > allocated:
            raise RuntimeError(
                f"Reversal exceeds allocated points for line {line_id}."
            )

    final_qualifying_accounts = sum(
        1 for value in qualifying_spend.values()
        if value > 0
    )

    print("\n" + "-" * 65)
    print("DRY-RUN SUMMARY")
    print("-" * 65)

    print("Eligible orders processed:", processed_orders)
    print("Completed return lines processed:", processed_return_lines)
    print("Orders missing order lines:", missing_order_lines)
    print("Return quantity errors:", return_quantity_errors)

    print("\nPOINTS SUMMARY")
    print("Total points earned:", total_earned)
    print("Total points allocated:", allocation_total)
    print("Total points to reverse:", total_reversed)
    print("Net points before redemption:", total_earned - total_reversed)

    print("\nRETURN SUMMARY")
    print("Actual completed refunds:", total_refunds)

    print("\nTIER DISTRIBUTION")

    for tier_name in [
        "BRONZE",
        "SILVER",
        "GOLD",
        "PLATINUM"
    ]:
        print(
            f"{tier_name}: {tier_counts[tier_name]}"
        )

    print("\nACCOUNT SUMMARY")
    print("Accounts receiving points:", len(account_points_earned))
    print("Accounts with positive final qualifying spend:",
          final_qualifying_accounts)

    print("\nIMPORTANT LIMITATIONS")
    print("- Redemption events are not included in this run.")
    print("- Expiry events are not included in this run.")
    print("- Points debt is not yet calculated or inserted.")
    print("- No ledger transactions or lots are inserted.")
    print("- No account balances are updated.")

    print("\nDATABASE CHANGES: NONE")
    print("=" * 65)

    if missing_order_lines or return_quantity_errors:
        raise RuntimeError(
            "Dry-run validation failed. Review the errors above."
        )


if __name__ == "__main__":

    if not DRY_RUN_ONLY:
        raise RuntimeError(
            "This module is currently restricted to dry-run mode."
        )

    process_accruals()
