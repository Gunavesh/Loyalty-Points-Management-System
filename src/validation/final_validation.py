
from pathlib import Path
import json
from datetime import datetime
from sqlalchemy import text

from config.db_config import engine


OUTPUT_DIR = Path("data/processed")
ANOMALY_DIR = Path("data/anomalies")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def scalar(connection, query):
    return connection.execute(text(query)).scalar() or 0


def run_validation():
    checks = []

    def add_check(name, actual, expected, passed, details=""):
        checks.append({
            "check": name,
            "actual": actual,
            "expected": expected,
            "status": "PASS" if passed else "FAIL",
            "details": details
        })

    with engine.connect() as connection:

        # 1. Core database record counts
        tables = [
            "customer", "loyaltyaccount", "orders", "orderline",
            "returns", "returnline", "pointstransaction",
            "pointslot", "pointsallocation", "redemption",
            "expirybatch", "reward", "tier", "rule"
        ]

        counts = {}
        for table in tables:
            counts[table] = int(
                scalar(connection, f"SELECT COUNT(*) FROM `{table}`")
            )

        add_check(
            "Core database tables contain records",
            sum(counts.values()),
            "> 0",
            sum(counts.values()) > 0
        )

        # 2. Account balance must equal ledger sum
        mismatches = int(scalar(connection, """
            SELECT COUNT(*)
            FROM loyaltyaccount a
            LEFT JOIN (
                SELECT account_id, SUM(points_change) AS ledger_balance
                FROM pointstransaction
                GROUP BY account_id
            ) t ON t.account_id = a.account_id
            WHERE a.current_balance <> COALESCE(t.ledger_balance, 0)
        """))

        add_check(
            "Account and ledger reconciliation",
            mismatches, 0, mismatches == 0
        )

        # 3. No negative account balances
        negative_accounts = int(scalar(connection, """
            SELECT COUNT(*)
            FROM loyaltyaccount
            WHERE current_balance < 0
        """))

        add_check(
            "No negative account balances",
            negative_accounts, 0, negative_accounts == 0
        )

        # 4. No negative points remaining in lots
        invalid_lots = int(scalar(connection, """
            SELECT COUNT(*)
            FROM pointslot
            WHERE remaining_points > original_points
               OR (lot_status = 'EXPIRED' AND remaining_points <> 0)
        """))

        add_check(
            "Points lot consistency",
            invalid_lots, 0, invalid_lots == 0
        )

        # 5. Order amount arithmetic
        invalid_orders = int(scalar(connection, """
            SELECT COUNT(*)
            FROM orders
            WHERE ABS(gross_amount - discount_amount - net_amount) > 0.01
               OR gross_amount < discount_amount
               OR discount_amount < 0
        """))

        add_check(
            "Order amount calculations",
            invalid_orders, 0, invalid_orders == 0
        )

        # 6. Order line arithmetic
        invalid_order_lines = int(scalar(connection, """
            SELECT COUNT(*)
            FROM orderline
            WHERE ABS(
                (quantity * unit_price) - discount_amount - line_net_amount
            ) > 0.01
               OR quantity <= 0
               OR discount_amount < 0
        """))

        add_check(
            "Order line calculations",
            invalid_order_lines, 0, invalid_order_lines == 0
        )

        # 7. Return quantities must not exceed purchased quantities
        excess_returns = int(scalar(connection, """
            SELECT COUNT(*)
            FROM (
                SELECT
                    ol.order_line_id,
                    ol.quantity,
                    SUM(
                        CASE
                            WHEN r.return_status = 'COMPLETED'
                            THEN rl.returned_quantity
                            ELSE 0
                        END
                    ) AS returned_quantity
                FROM orderline ol
                LEFT JOIN returnline rl
                    ON rl.order_line_id = ol.order_line_id
                LEFT JOIN returns r
                    ON r.return_id = rl.return_id
                GROUP BY ol.order_line_id, ol.quantity
                HAVING returned_quantity > ol.quantity
            ) invalid
        """))

        add_check(
            "Returned quantities do not exceed purchased quantities",
            excess_returns, 0, excess_returns == 0
        )

        # 8. Expiry batch status
        expiry_batches = int(scalar(connection, """
            SELECT COUNT(*)
            FROM expirybatch
            WHERE batch_status <> 'COMPLETED'
        """))

        add_check(
            "All expiry batches completed",
            expiry_batches, 0, expiry_batches == 0
        )

        # 9. Redemption status
        incomplete_redemptions = int(scalar(connection, """
            SELECT COUNT(*)
            FROM redemption
            WHERE redemption_status = 'PENDING'
        """))

        add_check(
            "No pending redemptions",
            incomplete_redemptions, 0,
            incomplete_redemptions == 0
        )

        # 10. Expiry and redemption totals
        transaction_totals = connection.execute(text("""
            SELECT
                transaction_type,
                COUNT(*) AS record_count,
                COALESCE(SUM(points_change), 0) AS points_change
            FROM pointstransaction
            GROUP BY transaction_type
            ORDER BY transaction_type
        """)).mappings().all()

        transaction_summary = [
            {
                "transaction_type": row["transaction_type"],
                "record_count": int(row["record_count"]),
                "points_change": int(row["points_change"])
            }
            for row in transaction_totals
        ]

    # 11. Required anomaly deliverables
    required_files = [
        ANOMALY_DIR / "anomaly_input.csv",
        ANOMALY_DIR / "ground_truth.csv",
        ANOMALY_DIR / "anomaly_detection_results.csv",
        ANOMALY_DIR / "evaluation_metrics.csv",
        ANOMALY_DIR / "evaluation_details.csv",
        ANOMALY_DIR / "injection_summary.json"
    ]

    missing_files = [
        str(path) for path in required_files if not path.exists()
    ]

    add_check(
        "Anomaly deliverable files exist",
        len(required_files) - len(missing_files),
        len(required_files),
        len(missing_files) == 0,
        "Missing: " + ", ".join(missing_files)
        if missing_files else "All required files found."
    )

    # 12. Anomaly record counts
    anomaly_count = 0
    detection_count = 0

    input_file = ANOMALY_DIR / "anomaly_input.csv"
    detection_file = ANOMALY_DIR / "anomaly_detection_results.csv"

    if input_file.exists():
        import pandas as pd
        anomaly_count = len(pd.read_csv(input_file))

    if detection_file.exists():
        import pandas as pd
        detection_count = len(pd.read_csv(detection_file))

    add_check(
        "Anomaly records and detection results match",
        detection_count,
        anomaly_count,
        detection_count == anomaly_count
    )

    passed = sum(c["status"] == "PASS" for c in checks)
    failed = sum(c["status"] == "FAIL" for c in checks)

    report = {
        "project": "Loyalty Points Management System",
        "validation_date": datetime.now().isoformat(timespec="seconds"),
        "database_record_counts": counts,
        "transaction_summary": transaction_summary,
        "anomaly_records": anomaly_count,
        "detection_records": detection_count,
        "checks_passed": passed,
        "checks_failed": failed,
        "overall_status": "PASS" if failed == 0 else "REVIEW REQUIRED",
        "checks": checks
    }

    report_path = OUTPUT_DIR / "final_validation_report.json"

    with open(report_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4, default=str)

    print("=" * 55)
    print("FINAL PROJECT VALIDATION")
    print("=" * 55)

    for check in checks:
        print(f"{check['status']}: {check['check']} "
              f"(Actual: {check['actual']}, Expected: {check['expected']})")

    print("\nDatabase record counts:")
    for table, count in counts.items():
        print(f"{table}: {count}")

    print(f"\nChecks passed: {passed}")
    print(f"Checks failed: {failed}")
    print(f"Overall status: {report['overall_status']}")
    print(f"Report saved: {report_path}")


if __name__ == "__main__":
    run_validation()
