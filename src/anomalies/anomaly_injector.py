
from pathlib import Path
import json
import pandas as pd

from sqlalchemy import text
from config.db_config import engine


OUTPUT_DIR = Path("data/anomalies")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_df(connection, query, params=None):
    return pd.read_sql(text(query), connection, params=params or {})


def add_case(cases, truth, scenario, entity_type, entity_id,
             field_name, clean_value, anomalous_value, evidence):
    anomaly_id = f"ANOM-{len(cases) + 1:03d}"

    cases.append({
        "anomaly_id": anomaly_id,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "field_name": field_name,
        "clean_value": str(clean_value),
        "observed_value": str(anomalous_value),
        "evidence": evidence
    })

    truth.append({
        "anomaly_id": anomaly_id,
        "scenario": scenario,
        "is_anomaly": 1,
        "expected_issue": scenario
    })


def inject_anomalies(connection):
    cases = []
    truth = []
    unavailable = []

    # 1. Account balance differs from the ledger.
    account = fetch_df(connection, """
        SELECT account_id, current_balance
        FROM loyaltyaccount
        WHERE account_status = 'ACTIVE'
        ORDER BY account_id
        LIMIT 1
    """)

    if not account.empty:
        row = account.iloc[0]
        clean = int(row["current_balance"])
        add_case(
            cases, truth,
            "ACCOUNT_BALANCE_LEDGER_MISMATCH",
            "loyaltyaccount", row["account_id"],
            "current_balance",
            clean, clean + 500,
            "Injected balance differs from the ledger by 500 points."
        )
    else:
        unavailable.append("Scenario 1: no active account found.")

    # 2. Redemption exceeds the account's available points.
    redemption_source = fetch_df(connection, """
        SELECT a.account_id, a.current_balance, r.reward_id, r.points_cost
        FROM loyaltyaccount a
        CROSS JOIN reward r
        WHERE a.account_status = 'ACTIVE'
          AND r.reward_status = 'ACTIVE'
          AND (r.stock_quantity IS NULL OR r.stock_quantity > 0)
        ORDER BY a.account_id, r.points_cost
        LIMIT 1
    """)

    if not redemption_source.empty:
        row = redemption_source.iloc[0]
        balance = int(row["current_balance"])
        injected = balance + int(row["points_cost"]) + 100

        add_case(
            cases, truth,
            "REDEMPTION_EXCEEDS_AVAILABLE_POINTS",
            "redemption", f"{row['account_id']}-TEST",
            "points_redeemed",
            balance, injected,
            "Injected redemption is greater than the account's available balance."
        )
    else:
        unavailable.append("Scenario 2: no active account/reward combination found.")

    # 3. A fully returned order retains its earned points.
    returned_order = fetch_df(connection, """
        SELECT
            o.order_id,
            pt.transaction_id,
            pt.account_id,
            pt.points_change
        FROM orders o
        JOIN returns r
          ON r.order_id = o.order_id
        JOIN returnline rl
          ON rl.return_id = r.return_id
        JOIN orderline ol
          ON ol.order_line_id = rl.order_line_id
         AND ol.order_id = o.order_id
        JOIN pointstransaction pt
          ON pt.order_id = o.order_id
         AND pt.transaction_type = 'ACCRUAL'
        WHERE o.order_status = 'RETURNED'
          AND r.return_status = 'COMPLETED'
        ORDER BY o.order_id
        LIMIT 1
    """)

    if not returned_order.empty:
        row = returned_order.iloc[0]
        earned = abs(int(row["points_change"]))

        add_case(
            cases, truth,
            "RETURNED_ORDER_POINTS_NOT_REVERSED",
            "orders", row["order_id"],
            "points_reversed",
            earned, 0,
            f"Fully returned order has an accrual of {earned} points; "
            "the injected case retains all earned points."
        )
    else:
        unavailable.append("Scenario 3: no suitable completed returned order found.")

    # 4. The same points lot is expired twice.
    expired_lot = fetch_df(connection, """
        SELECT
            pa.lot_id,
            pa.transaction_id,
            pa.points_allocated,
            pt.account_id
        FROM pointsallocation pa
        JOIN pointstransaction pt
          ON pt.transaction_id = pa.transaction_id
        WHERE pa.allocation_type = 'EXPIRY'
        ORDER BY pa.lot_id
        LIMIT 1
    """)

    if not expired_lot.empty:
        row = expired_lot.iloc[0]

        add_case(
            cases, truth,
            "DUPLICATE_POINTS_EXPIRY",
            "pointslot", row["lot_id"],
            "total_expiry_allocated",
            int(row["points_allocated"]),
            int(row["points_allocated"]) * 2,
            "Injected case expires the same points lot twice."
        )
    else:
        unavailable.append("Scenario 4: no existing expiry allocation found.")

    # 5. Tier is calculated using gross spend instead of qualifying spend.
    tier_data = fetch_df(connection, """
        SELECT
            a.account_id,
            a.customer_id,
            a.qualifying_spend,
            a.tier_id,
            t.tier_name,
            t.minimum_qualifying_spend
        FROM loyaltyaccount a
        JOIN tier t ON t.tier_id = a.tier_id
        WHERE a.account_status = 'ACTIVE'
    """)

    gross_data = fetch_df(connection, """
        SELECT
            customer_id,
            SUM(gross_amount) AS gross_spend
        FROM orders
        WHERE order_status IN ('PAID', 'RETURNED', 'PARTIALLY_RETURNED')
        GROUP BY customer_id
    """)

    all_tiers = fetch_df(connection, """
        SELECT tier_id, tier_name, minimum_qualifying_spend
        FROM tier
        WHERE tier_status = 'ACTIVE'
        ORDER BY minimum_qualifying_spend
    """)

    if not tier_data.empty and not gross_data.empty and not all_tiers.empty:
        merged = tier_data.merge(gross_data, on="customer_id", how="left")
        merged["gross_spend"] = merged["gross_spend"].fillna(0)

        chosen = None
        for _, row in merged.iterrows():
            qualifying = float(row["qualifying_spend"])
            gross = float(row["gross_spend"])

            qualifying_tier = all_tiers[
                all_tiers["minimum_qualifying_spend"] <= qualifying
            ]
            gross_tier = all_tiers[
                all_tiers["minimum_qualifying_spend"] <= gross
            ]

            if qualifying_tier.empty or gross_tier.empty:
                continue

            correct_id = int(qualifying_tier.iloc[-1]["tier_id"])
            wrong_id = int(gross_tier.iloc[-1]["tier_id"])

            if correct_id == int(row["tier_id"]) and wrong_id != correct_id:
                chosen = (row, correct_id, wrong_id, qualifying, gross)
                break

        if chosen:
            row, correct_id, wrong_id, qualifying, gross = chosen

            add_case(
                cases, truth,
                "TIER_CALCULATED_USING_GROSS_SPEND",
                "loyaltyaccount", row["account_id"],
                "tier_id",
                correct_id, wrong_id,
                f"Qualifying spend={qualifying:.2f}; "
                f"gross spend={gross:.2f}. Injected tier uses gross spend."
            )
        else:
            unavailable.append(
                "Scenario 5: no account found where gross spend changes the tier."
            )
    else:
        unavailable.append("Scenario 5: tier/account/order data unavailable.")

    # Save anomaly input separately from ground truth.
    cases_df = pd.DataFrame(cases)
    truth_df = pd.DataFrame(truth)

    cases_df.to_csv(OUTPUT_DIR / "anomaly_input.csv", index=False)
    truth_df.to_csv(OUTPUT_DIR / "ground_truth.csv", index=False)

    summary = {
        "total_anomalies_created": len(cases),
        "expected_scenarios": 5,
        "created_scenarios": [item["scenario"] for item in truth],
        "unavailable_scenarios": unavailable,
        "database_modified": False,
        "output_files": [
            "data/anomalies/anomaly_input.csv",
            "data/anomalies/ground_truth.csv"
        ]
    }

    with open(OUTPUT_DIR / "injection_summary.json", "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=4)

    return summary


def main():
    print("=" * 55)
    print("LOYALTY POINTS - ANOMALY INJECTION")
    print("=" * 55)

    with engine.connect() as connection:
        summary = inject_anomalies(connection)

    print(f"\nAnomalies created: {summary['total_anomalies_created']}")
    print(f"Expected scenarios: {summary['expected_scenarios']}")
    print(f"Database modified: {summary['database_modified']}")

    for scenario in summary["created_scenarios"]:
        print(f"CREATED: {scenario}")

    for issue in summary["unavailable_scenarios"]:
        print(f"NOT CREATED: {issue}")

    print("\nFiles saved:")
    for filename in summary["output_files"]:
        print(f"  {filename}")

    print("\nInjection completed.")


if __name__ == "__main__":
    main()
