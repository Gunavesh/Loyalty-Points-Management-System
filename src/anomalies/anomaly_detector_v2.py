from pathlib import Path
import pandas as pd
from sqlalchemy import text
from config.db_config import engine

INPUT_FILE = Path("data/anomalies/anomaly_input.csv")
OUTPUT_FILE = Path("data/anomalies/anomaly_detection_results_v2.csv")


def detect_balance_mismatch(connection, account_id, observed):
    query = text("""
        SELECT a.current_balance,
               COALESCE(SUM(p.points_change), 0) AS ledger_balance
        FROM loyaltyaccount a
        LEFT JOIN pointstransaction p ON a.account_id = p.account_id
        WHERE a.account_id = :account_id
        GROUP BY a.account_id, a.current_balance
    """)
    row = connection.execute(query, {"account_id": account_id}).mappings().first()

    if row is None:
        return None, "Account not found."

    actual = int(row["ledger_balance"])
    return float(observed) != actual, (
        f"Observed balance: {observed}; actual ledger balance: {actual}."
    )


def detect_wrong_tier(connection, account_id, observed):
    account = connection.execute(
        text("SELECT qualifying_spend FROM loyaltyaccount WHERE account_id=:id"),
        {"id": account_id}
    ).mappings().first()

    if account is None:
        return None, "Account not found."

    tiers = connection.execute(text("""
        SELECT tier_id, minimum_qualifying_spend
        FROM tier
        WHERE tier_status = 'ACTIVE'
        ORDER BY minimum_qualifying_spend
    """)).mappings().all()

    spend = float(account["qualifying_spend"])
    eligible = [
        t for t in tiers
        if float(t["minimum_qualifying_spend"]) <= spend
    ]

    if not eligible:
        return None, "No eligible tier found."

    expected = int(eligible[-1]["tier_id"])
    return float(observed) != expected, (
        f"Qualifying spend: {spend}; expected tier: {expected}; "
        f"observed tier: {observed}."
    )


def detect_excess_redemption(connection, entity_id, observed):
    account_id = entity_id.removesuffix("-TEST")

    row = connection.execute(
        text("""
            SELECT current_balance
            FROM loyaltyaccount
            WHERE account_id = :id
        """),
        {"id": account_id}
    ).mappings().first()

    if row is None:
        return None, "Account not found."

    available = int(row["current_balance"])
    detected = float(observed) > available

    return detected, (
        f"Redemption points: {observed}; "
        f"account available balance: {available}."
    )


def detect_duplicate_expiry(connection, lot_id, observed):
    row = connection.execute(
        text("""
            SELECT COALESCE(SUM(points_allocated), 0) AS actual_expiry
            FROM pointsallocation
            WHERE lot_id = :lot_id
              AND allocation_type = 'EXPIRY'
        """),
        {"lot_id": lot_id}
    ).mappings().first()

    actual = int(row["actual_expiry"])
    detected = float(observed) > actual

    return detected, (
        f"Observed expiry total: {observed}; "
        f"actual recorded expiry allocation: {actual}."
    )


def detect_missing_return_reversal(connection, order_id, observed):
    row = connection.execute(text("""
        SELECT
            o.order_id,
            o.order_status,

            (
                SELECT COUNT(*)
                FROM orderline ol
                WHERE ol.order_id = o.order_id
            ) AS order_line_count,

            (
                SELECT COUNT(*)
                FROM orderline ol
                WHERE ol.order_id = o.order_id
                  AND COALESCE((
                      SELECT SUM(rl.returned_quantity)
                      FROM `returns` r
                      JOIN returnline rl
                          ON rl.return_id = r.return_id
                      WHERE r.order_id = o.order_id
                        AND r.return_status = 'COMPLETED'
                        AND rl.order_line_id = ol.order_line_id
                  ), 0) <> ol.quantity
            ) AS incomplete_return_lines,

            (
                SELECT COALESCE(SUM(points_change), 0)
                FROM pointstransaction
                WHERE order_id = o.order_id
                  AND transaction_type = 'ACCRUAL'
            ) AS earned_points,

            (
                SELECT COALESCE(SUM(ABS(points_change)), 0)
                FROM pointstransaction
                WHERE order_id = o.order_id
                  AND transaction_type = 'RETURN_REVERSAL'
            ) AS reversed_points

        FROM orders o
        WHERE o.order_id = :order_id
    """), {"order_id": order_id}).mappings().first()

    if row is None:
        return None, "Order not found."

    if row["order_status"] != "RETURNED":
        return None, (
            f"Order is not fully returned. "
            f"Current status: {row['order_status']}."
        )

    if row["order_line_count"] == 0 or row["incomplete_return_lines"] > 0:
        return None, "Order lines are not all fully returned."

    earned = int(row["earned_points"])
    actual_reversed = int(row["reversed_points"])
    observed_value = float(observed)

    if earned <= 0:
        return None, "No original accrual found for the order."

    detected = observed_value != actual_reversed

    return detected, (
        f"Order fully returned; earned points: {earned}; "
        f"observed reversed points: {observed_value}; "
        f"actual database reversals: {actual_reversed}."
    )


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(INPUT_FILE)

    df = pd.read_csv(INPUT_FILE)
    results = []

    with engine.connect() as connection:
        for _, row in df.iterrows():
            field = row["field_name"]
            entity_id = str(row["entity_id"])
            observed = row["observed_value"]

            detected = None
            reason = "Scenario not yet supported."
            status = "NOT_EVALUATED"

            if field == "current_balance":
                detected, reason = detect_balance_mismatch(
                    connection, entity_id, observed
                )

            elif field == "tier_id":
                detected, reason = detect_wrong_tier(
                    connection, entity_id, observed
                )

            elif field == "points_redeemed":
                detected, reason = detect_excess_redemption(
                    connection, entity_id, observed
                )

            elif field == "total_expiry_allocated":
                detected, reason = detect_duplicate_expiry(
                    connection, entity_id, observed
                )

            elif field == "points_reversed":
                detected, reason = detect_missing_return_reversal(
                    connection, entity_id, observed
                )

            if detected is not None:
                status = "EVALUATED"

            results.append({
                "anomaly_id": row["anomaly_id"],
                "entity_type": row["entity_type"],
                "entity_id": entity_id,
                "field_name": field,
                "observed_value": observed,
                "is_anomaly": detected,
                "evaluation_status": status,
                "detection_reason": reason
            })

    output = pd.DataFrame(results)
    output.to_csv(OUTPUT_FILE, index=False)

    print("=" * 50)
    print("V2 ANOMALY DETECTION COMPLETED")
    print("=" * 50)
    print(f"Records checked: {len(output)}")
    print(f"Evaluated: {(output['evaluation_status'] == 'EVALUATED').sum()}")
    print(f"Not evaluated: {(output['evaluation_status'] == 'NOT_EVALUATED').sum()}")
    print(f"Anomalies detected: {output['is_anomaly'].eq(True).sum()}")
    print(f"Results saved: {OUTPUT_FILE}")
    print("\nDetection details:")
    print(output[
        ["anomaly_id", "is_anomaly", "evaluation_status", "detection_reason"]
    ].to_string(index=False))


if __name__ == "__main__":
    main()
