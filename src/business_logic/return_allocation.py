
from decimal import Decimal, ROUND_FLOOR


def allocate_points_to_order_lines(order_points, order_lines):
    """
    Distribute an order's earned points across its order lines.

    order_lines format:
    [
        {"order_line_id": 1, "line_net_amount": 500},
        {"order_line_id": 2, "line_net_amount": 300},
        {"order_line_id": 3, "line_net_amount": 200}
    ]
    """

    if order_points < 0:
        raise ValueError("Order points cannot be negative.")

    if not order_lines:
        raise ValueError("Order must contain at least one line.")

    total_amount = sum(
        Decimal(str(line["line_net_amount"]))
        for line in order_lines
    )

    if total_amount <= 0:
        raise ValueError("Total order amount must be positive.")

    allocations = []
    allocated_total = 0

    for line in order_lines:
        amount = Decimal(str(line["line_net_amount"]))

        if amount < 0:
            raise ValueError("Line amount cannot be negative.")

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

    remaining_points = order_points - allocated_total

    # Give leftover points to the largest fractional remainders.
    # order_line_id provides a deterministic tie-breaker.
    ranked = sorted(
        allocations,
        key=lambda item: (
            -item["fraction"],
            item["order_line_id"]
        )
    )

    for item in ranked[:remaining_points]:
        item["allocated_points"] += 1

    return [
        {
            "order_line_id": item["order_line_id"],
            "allocated_points": item["allocated_points"]
        }
        for item in sorted(
            allocations,
            key=lambda item: item["order_line_id"]
        )
    ]


def calculate_cumulative_reversal(
    allocated_points,
    purchased_quantity,
    previously_returned_quantity,
    newly_returned_quantity,
    previously_reversed_points
):
    """
    Calculate the additional points to reverse for a return.

    A fully returned line always reverses all its allocated points.
    """

    if purchased_quantity <= 0:
        raise ValueError("Purchased quantity must be positive.")

    if allocated_points < 0:
        raise ValueError("Allocated points cannot be negative.")

    if previously_returned_quantity < 0:
        raise ValueError("Previously returned quantity cannot be negative.")

    if newly_returned_quantity <= 0:
        raise ValueError("New returned quantity must be positive.")

    cumulative_quantity = (
        previously_returned_quantity + newly_returned_quantity
    )

    if cumulative_quantity > purchased_quantity:
        raise ValueError("Returned quantity exceeds purchased quantity.")

    if previously_reversed_points < 0:
        raise ValueError("Previously reversed points cannot be negative.")

    target_reversal = (
        allocated_points * cumulative_quantity
    ) // purchased_quantity

    if cumulative_quantity == purchased_quantity:
        target_reversal = allocated_points

    additional_reversal = (
        target_reversal - previously_reversed_points
    )

    if additional_reversal < 0:
        raise ValueError("Previous reversal amount is inconsistent.")

    return additional_reversal


if __name__ == "__main__":

    lines = [
        {"order_line_id": 1, "line_net_amount": 500},
        {"order_line_id": 2, "line_net_amount": 300},
        {"order_line_id": 3, "line_net_amount": 200}
    ]

    result = allocate_points_to_order_lines(101, lines)

    print("ORDER POINT ALLOCATION")
    for item in result:
        print(item)

    print(
        "Total allocated:",
        sum(item["allocated_points"] for item in result)
    )

    reversal = calculate_cumulative_reversal(
        allocated_points=51,
        purchased_quantity=3,
        previously_returned_quantity=1,
        newly_returned_quantity=1,
        previously_reversed_points=17
    )

    print("\nPARTIAL RETURN TEST")
    print("Additional points to reverse:", reversal)
