
import random
from collections import defaultdict
from datetime import datetime

from sqlalchemy import text

from config.db_config import engine


# Fixed simulation settings
SEED = 20261022
SIMULATION_END = datetime(2026, 11, 12, 23, 59, 59)
REDEMPTION_SAMPLE_RATE = 0.05


def next_id(connection, table, prefix):
    """Generate the next ID using the existing project ID format."""
    column = {
        "pointstransaction": "transaction_id",
        "redemption": "redemption_id",
        "expirybatch": "expiry_batch_id",
    }[table]

    result = connection.execute(
        text(
            f"""
            SELECT COALESCE(
                MAX(CAST(SUBSTRING({column}, 10) AS UNSIGNED)),
                0
            )
            FROM {table}
            WHERE {column} LIKE :pattern
            """
        ),
        {"pattern": f"{prefix}%"},
    ).scalar_one()

    return int(result) + 1


def format_id(prefix, sequence):
    return f"{prefix}{sequence:08d}"


def process():
    rng = random.Random(SEED)

    print("=" * 60)
    print("LOYALTY REDEMPTION AND EXPIRY PROCESSOR")
    print("=" * 60)
    print("Processing date:", SIMULATION_END)
    print("Redemption sample:", f"{REDEMPTION_SAMPLE_RATE:.0%}")
    print()

    with engine.begin() as connection:

        # Prevent duplicate execution.
        existing_batches = connection.execute(
            text("SELECT COUNT(*) FROM expirybatch")
        ).scalar_one()

        existing_redemptions = connection.execute(
            text("SELECT COUNT(*) FROM redemption")
        ).scalar_one()

        if existing_batches or existing_redemptions:
            raise RuntimeError(
                "Processing records already exist. "
                "The processor has stopped to prevent duplicates."
            )

        # --------------------------------------------------
        # STEP 1: FIND AND LOCK EXPIRED POINT LOTS
        # --------------------------------------------------

        expired_lots = connection.execute(
            text(
                """
                SELECT
                    lot_id,
                    account_id,
                    remaining_points
                FROM pointslot
                WHERE remaining_points > 0
                  AND expiry_date <= :cutoff
                ORDER BY expiry_date, earned_at, lot_id
                FOR UPDATE
                """
            ),
            {"cutoff": SIMULATION_END},
        ).mappings().all()

        expiry_total = sum(
            int(row["remaining_points"]) for row in expired_lots
        )

        print("STEP 1: EXPIRY PROCESSING")
        print("Eligible lots:", len(expired_lots))
        print("Points to expire:", expiry_total)

        transaction_sequence = next_id(
            connection, "pointstransaction", "PTS-2026-"
        )

        expiry_sequence = next_id(
            connection, "expirybatch", "EXP-2026-"
        )

        expiry_batch_id = f"EXP-2026-{expiry_sequence:06d}"

        connection.execute(
            text(
                """
                INSERT INTO expirybatch (
                    expiry_batch_id,
                    batch_started_at,
                    batch_status,
                    points_expired,
                    records_processed
                )
                VALUES (
                    :batch_id,
                    :started_at,
                    'STARTED',
                    0,
                    0
                )
                """
            ),
            {
                "batch_id": expiry_batch_id,
                "started_at": SIMULATION_END,
            },
        )

        expiry_transactions = []
        expiry_allocations = []
        expiry_by_account = defaultdict(int)

        for lot in expired_lots:
            points = int(lot["remaining_points"])
            transaction_id = format_id(
                "PTS-2026-", transaction_sequence
            )
            transaction_sequence += 1

            expiry_transactions.append(
                {
                    "transaction_id": transaction_id,
                    "account_id": lot["account_id"],
                    "points_change": -points,
                    "transaction_date": SIMULATION_END,
                    "expiry_batch_id": expiry_batch_id,
                    "description": "Points expired after 365 days",
                    "idempotency_key": f"EXPIRY:{lot['lot_id']}",
                }
            )

            expiry_allocations.append(
                {
                    "lot_id": lot["lot_id"],
                    "transaction_id": transaction_id,
                    "points_allocated": points,
                }
            )

            expiry_by_account[lot["account_id"]] += points

        if expiry_transactions:
            connection.execute(
                text(
                    """
                    INSERT INTO pointstransaction (
                        transaction_id,
                        account_id,
                        transaction_type,
                        points_change,
                        transaction_date,
                        expiry_batch_id,
                        description,
                        idempotency_key
                    )
                    VALUES (
                        :transaction_id,
                        :account_id,
                        'EXPIRY',
                        :points_change,
                        :transaction_date,
                        :expiry_batch_id,
                        :description,
                        :idempotency_key
                    )
                    """
                ),
                expiry_transactions,
            )

            connection.execute(
                text(
                    """
                    INSERT INTO pointsallocation (
                        lot_id,
                        transaction_id,
                        allocation_type,
                        points_allocated
                    )
                    VALUES (
                        :lot_id,
                        :transaction_id,
                        'EXPIRY',
                        :points_allocated
                    )
                    """
                ),
                expiry_allocations,
            )

            # Set status BEFORE reducing unsigned remaining_points.
            connection.execute(
                text(
                    """
                    UPDATE pointslot
                    SET
                        lot_status = 'EXPIRED',
                        remaining_points = 0
                    WHERE remaining_points > 0
                      AND expiry_date <= :cutoff
                    """
                ),
                {"cutoff": SIMULATION_END},
            )

            connection.execute(
                text(
                    """
                    UPDATE loyaltyaccount
                    SET
                        current_balance = current_balance - :points,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE account_id = :account_id
                      AND current_balance >= :points
                    """
                ),
                [
                    {"account_id": account_id, "points": points}
                    for account_id, points in expiry_by_account.items()
                ],
            )

        connection.execute(
            text(
                """
                UPDATE expirybatch
                SET
                    batch_completed_at = :completed_at,
                    batch_status = 'COMPLETED',
                    points_expired = :points,
                    records_processed = :records
                WHERE expiry_batch_id = :batch_id
                """
            ),
            {
                "completed_at": SIMULATION_END,
                "points": expiry_total,
                "records": len(expired_lots),
                "batch_id": expiry_batch_id,
            },
        )

        print("Expiry transactions:", len(expiry_transactions))
        print("Expiry allocations:", len(expiry_allocations))
        print("Expiry batch:", expiry_batch_id)
        print()

        # --------------------------------------------------
        # STEP 2: LOAD REWARDS AND UNEXPIRED POINT LOTS
        # --------------------------------------------------

        print("STEP 2: REDEMPTION PROCESSING")

        rewards = connection.execute(
            text(
                """
                SELECT
                    reward_id,
                    reward_name,
                    points_cost,
                    stock_quantity
                FROM reward
                WHERE reward_status = 'ACTIVE'
                  AND effective_from <= :cutoff
                  AND (effective_to IS NULL OR effective_to >= :cutoff)
                  AND (stock_quantity IS NULL OR stock_quantity > 0)
                ORDER BY reward_id
                FOR UPDATE
                """
            ),
            {"cutoff": SIMULATION_END},
        ).mappings().all()

        if not rewards:
            print("No active rewards available.")
            print("Redemptions skipped.")
            return

        reward_stock = {
            row["reward_id"]: row["stock_quantity"]
            for row in rewards
        }

        reward_data = {
            row["reward_id"]: row
            for row in rewards
        }

        available_lots = connection.execute(
            text(
                """
                SELECT
                    lot_id,
                    account_id,
                    remaining_points,
                    expiry_date,
                    earned_at
                FROM pointslot
                WHERE remaining_points > 0
                  AND expiry_date > :cutoff
                  AND lot_status IN ('ACTIVE', 'PARTIALLY_USED')
                ORDER BY account_id, expiry_date, earned_at, lot_id
                FOR UPDATE
                """
            ),
            {"cutoff": SIMULATION_END},
        ).mappings().all()

        lots_by_account = defaultdict(list)

        for lot in available_lots:
            lots_by_account[lot["account_id"]].append(
                {
                    "lot_id": lot["lot_id"],
                    "remaining": int(lot["remaining_points"]),
                }
            )

        eligible_accounts = []

        for account_id, lots in lots_by_account.items():
            available_points = sum(
                lot["remaining"] for lot in lots
            )

            if available_points >= min(
                int(row["points_cost"]) for row in rewards
            ):
                eligible_accounts.append(account_id)

        eligible_accounts.sort()

        sample_size = int(
            len(eligible_accounts) * REDEMPTION_SAMPLE_RATE
        )

        selected_accounts = sorted(
            rng.sample(eligible_accounts, sample_size)
        ) if sample_size else []

        redemption_sequence = next_id(
            connection, "redemption", "RDM-2026-"
        )

        redemption_records = []
        redemption_transactions = []
        redemption_allocations = []
        redemption_by_account = defaultdict(int)
        reward_redemptions = defaultdict(int)

        for account_id in selected_accounts:

            lots = lots_by_account[account_id]

            available_points = sum(
                lot["remaining"] for lot in lots
            )

            affordable_rewards = [
                row for row in rewards
                if int(row["points_cost"]) <= available_points
                and (
                    reward_stock[row["reward_id"]] is None
                    or reward_stock[row["reward_id"]] > 0
                )
            ]

            if not affordable_rewards:
                continue

            reward = rng.choice(affordable_rewards)
            reward_id = reward["reward_id"]
            points = int(reward["points_cost"])

            redemption_id = format_id(
                "RDM-2026-", redemption_sequence
            )
            redemption_sequence += 1

            transaction_id = format_id(
                "PTS-2026-", transaction_sequence
            )
            transaction_sequence += 1

            redemption_records.append(
                {
                    "redemption_id": redemption_id,
                    "account_id": account_id,
                    "reward_id": reward_id,
                    "points_redeemed": points,
                    "redemption_date": SIMULATION_END,
                    "idempotency_key": f"REDEMPTION:{redemption_id}",
                }
            )

            redemption_transactions.append(
                {
                    "transaction_id": transaction_id,
                    "account_id": account_id,
                    "points_change": -points,
                    "transaction_date": SIMULATION_END,
                    "redemption_id": redemption_id,
                    "description": (
                        f"Redeemed reward: {reward['reward_name']}"
                    ),
                    "idempotency_key": f"REDEMPTION:{redemption_id}",
                }
            )

            redemption_by_account[account_id] += points
            reward_redemptions[reward_id] += 1

            # FIFO: earliest-expiring lots are consumed first.
            points_left = points

            for lot in lots:
                if points_left == 0:
                    break

                allocated = min(lot["remaining"], points_left)

                if allocated <= 0:
                    continue

                redemption_allocations.append(
                    {
                        "lot_id": lot["lot_id"],
                        "transaction_id": transaction_id,
                        "points_allocated": allocated,
                    }
                )

                # Status is set before changing unsigned remaining_points.
                new_remaining = lot["remaining"] - allocated

                connection.execute(
                    text(
                        """
                        UPDATE pointslot
                        SET
                            lot_status = :new_status,
                            remaining_points = :remaining
                        WHERE lot_id = :lot_id
                          AND remaining_points >= :allocated
                        """
                    ),
                    {
                        "new_status": (
                            "CONSUMED"
                            if new_remaining == 0
                            else "PARTIALLY_USED"
                        ),
                        "remaining": new_remaining,
                        "lot_id": lot["lot_id"],
                        "allocated": allocated,
                    },
                )

                lot["remaining"] = new_remaining
                points_left -= allocated

            if points_left != 0:
                raise RuntimeError(
                    f"Insufficient point lots for {account_id}"
                )

            if reward_stock[reward_id] is not None:
                reward_stock[reward_id] -= 1

        if redemption_records:

            connection.execute(
                text(
                    """
                    INSERT INTO redemption (
                        redemption_id,
                        account_id,
                        reward_id,
                        points_redeemed,
                        redemption_status,
                        redemption_date,
                        idempotency_key
                    )
                    VALUES (
                        :redemption_id,
                        :account_id,
                        :reward_id,
                        :points_redeemed,
                        'COMPLETED',
                        :redemption_date,
                        :idempotency_key
                    )
                    """
                ),
                redemption_records,
            )

            connection.execute(
                text(
                    """
                    INSERT INTO pointstransaction (
                        transaction_id,
                        account_id,
                        transaction_type,
                        points_change,
                        transaction_date,
                        redemption_id,
                        description,
                        idempotency_key
                    )
                    VALUES (
                        :transaction_id,
                        :account_id,
                        'REDEMPTION',
                        :points_change,
                        :transaction_date,
                        :redemption_id,
                        :description,
                        :idempotency_key
                    )
                    """
                ),
                redemption_transactions,
            )

            connection.execute(
                text(
                    """
                    INSERT INTO pointsallocation (
                        lot_id,
                        transaction_id,
                        allocation_type,
                        points_allocated
                    )
                    VALUES (
                        :lot_id,
                        :transaction_id,
                        'REDEMPTION',
                        :points_allocated
                    )
                    """
                ),
                redemption_allocations,
            )

            connection.execute(
                text(
                    """
                    UPDATE loyaltyaccount
                    SET
                        current_balance = current_balance - :points,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE account_id = :account_id
                      AND current_balance >= :points
                    """
                ),
                [
                    {"account_id": account_id, "points": points}
                    for account_id, points in redemption_by_account.items()
                ],
            )

            for reward_id, count in reward_redemptions.items():
                if reward_stock[reward_id] is not None:
                    connection.execute(
                        text(
                            """
                            UPDATE reward
                            SET stock_quantity = :stock
                            WHERE reward_id = :reward_id
                            """
                        ),
                        {
                            "stock": reward_stock[reward_id],
                            "reward_id": reward_id,
                        },
                    )

                    if reward_stock[reward_id] == 0:
                        connection.execute(
                            text(
                                """
                                UPDATE reward
                                SET reward_status = 'OUT_OF_STOCK'
                                WHERE reward_id = :reward_id
                                """
                            ),
                            {"reward_id": reward_id},
                        )

        total_redeemed = sum(redemption_by_account.values())

        print("Eligible accounts:", len(eligible_accounts))
        print("Selected accounts:", len(selected_accounts))
        print("Completed redemptions:", len(redemption_records))
        print("Redemption allocations:", len(redemption_allocations))
        print("Points redeemed:", total_redeemed)
        print()

        # --------------------------------------------------
        # STEP 3: FINAL LEDGER RECONCILIATION
        # --------------------------------------------------

        print("STEP 3: FINAL RECONCILIATION")

        mismatches = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM loyaltyaccount a
                LEFT JOIN (
                    SELECT
                        account_id,
                        SUM(points_change) AS ledger_balance
                    FROM pointstransaction
                    GROUP BY account_id
                ) t ON t.account_id = a.account_id
                WHERE a.current_balance <> COALESCE(t.ledger_balance, 0)
                """
            )
        ).scalar_one()

        negative_balances = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM loyaltyaccount
                WHERE current_balance < 0
                """
            )
        ).scalar_one()

        if mismatches or negative_balances:
            raise RuntimeError(
                "Reconciliation failed. "
                f"Balance mismatches: {mismatches}; "
                f"negative balances: {negative_balances}"
            )

        print("Account/ledger mismatches:", mismatches)
        print("Negative account balances:", negative_balances)
        print("RECONCILIATION: PASSED")

    print()
    print("=" * 60)
    print("PROCESSING COMPLETED AND COMMITTED")
    print("=" * 60)
    print("Points expired:", expiry_total)
    print("Points redeemed:", total_redeemed)
    print("Redemptions completed:", len(redemption_records))
    print("Expiry batch:", expiry_batch_id)


if __name__ == "__main__":
    process()
