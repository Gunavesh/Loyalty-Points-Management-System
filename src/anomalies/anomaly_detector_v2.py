
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
