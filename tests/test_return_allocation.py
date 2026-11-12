
import pytest

from src.business_logic.return_allocation import (
    allocate_points_to_order_lines,
    calculate_cumulative_reversal
)


def test_points_are_distributed_correctly():
    lines = [
        {"order_line_id": 1, "line_net_amount": 500},
        {"order_line_id": 2, "line_net_amount": 300},
        {"order_line_id": 3, "line_net_amount": 200}
    ]

    result = allocate_points_to_order_lines(101, lines)

    assert [item["allocated_points"] for item in result] == [51, 30, 20]
    assert sum(item["allocated_points"] for item in result) == 101


def test_full_return_reverses_all_allocated_points():
    reversal = calculate_cumulative_reversal(
        allocated_points=51,
        purchased_quantity=3,
        previously_returned_quantity=0,
        newly_returned_quantity=3,
        previously_reversed_points=0
    )

    assert reversal == 51


def test_multiple_partial_returns_reverse_exact_total():
    first_reversal = calculate_cumulative_reversal(
        allocated_points=51,
        purchased_quantity=3,
        previously_returned_quantity=0,
        newly_returned_quantity=1,
        previously_reversed_points=0
    )

    second_reversal = calculate_cumulative_reversal(
        allocated_points=51,
        purchased_quantity=3,
        previously_returned_quantity=1,
        newly_returned_quantity=1,
        previously_reversed_points=first_reversal
    )

    final_reversal = calculate_cumulative_reversal(
        allocated_points=51,
        purchased_quantity=3,
        previously_returned_quantity=2,
        newly_returned_quantity=1,
        previously_reversed_points=first_reversal + second_reversal
    )

    assert first_reversal + second_reversal + final_reversal == 51


def test_return_quantity_cannot_exceed_purchased_quantity():
    with pytest.raises(ValueError):
        calculate_cumulative_reversal(
            allocated_points=51,
            purchased_quantity=3,
            previously_returned_quantity=2,
            newly_returned_quantity=2,
            previously_reversed_points=34
        )


def test_negative_order_points_are_rejected():
    lines = [
        {"order_line_id": 1, "line_net_amount": 500}
    ]

    with pytest.raises(ValueError):
        allocate_points_to_order_lines(-10, lines)


def test_zero_order_amount_is_rejected():
    lines = [
        {"order_line_id": 1, "line_net_amount": 0}
    ]

    with pytest.raises(ValueError):
        allocate_points_to_order_lines(10, lines)
