from pathlib import Path
from datetime import datetime
import json
import re
import subprocess
import sys

import pandas as pd
from sqlalchemy import text

from config.db_config import engine
from src.anomalies.anomaly_detector_v2 import detect_excess_redemption

ROOT = Path(".")
ANOMALY_DIR = ROOT / "data" / "anomalies"
OUTPUT_DIR = ROOT / "data" / "processed"


def add_check(checks, name, actual, expected, passed, details=""):
    checks.append({
        "check": name,
        "actual": actual,
        "expected": expected,
        "status": "PASS" if passed else "FAIL",
        "details": details
    })


def run_validation():
    checks = []

    # 1. Verify the existing database validation report.
    report_path = OUTPUT_DIR / "final_validation_report.json"
    with open(report_path, encoding="utf-8") as file:
        original = json.load(file)

    original_passed = (
        original.get("overall_status") == "PASS"
        and original.get("checks_passed") == 11
        and original.get("checks_failed") == 0
        and len(original.get("checks", [])) == 11
        and all(c.get("status") == "PASS" for c in original["checks"])
    )

    add_check(
        checks,
        "Original database validation",
        original.get("checks_passed", 0),
        "11 checks passed, 0 failed",
        original_passed,
        "Verified existing report; database checks were not rerun."
    )

    # 2. Verify the five injected anomaly detections.
    anomaly_file = ANOMALY_DIR / "anomaly_detection_results_v2.csv"
    anomalies = pd.read_csv(anomaly_file)

    anomaly_passed = (
        len(anomalies) == 5
        and anomalies["is_anomaly"].astype(str).str.lower().eq("true").all()
        and anomalies["evaluation_status"].eq("EVALUATED").all()
        and anomalies["anomaly_id"].nunique() == 5
    )

    add_check(
        checks,
        "Injected anomaly detection",
        int(anomalies["is_anomaly"].astype(str).str.lower().eq("true").sum()),
        "5 of 5 detected",
        anomaly_passed
    )

    # 3. Verify the 15 normal control records.
    control_file = ANOMALY_DIR / "redemption_control_evaluation.csv"
    controls = pd.read_csv(control_file)

    control_baseline_passed = (
        len(controls) == 15
        and controls["classification"].eq("NORMAL").all()
        and controls["valid_redemption"].astype(str).str.lower().eq("true").all()
    )

    add_check(
        checks,
        "Normal redemption control baseline",
        int(controls["classification"].eq("NORMAL").sum()),
        "15 normal records",
        control_baseline_passed
    )

    # 4. Independently run the updated detector on those 15 records.
    query = text("""
        SELECT redemption_id, account_id, points_redeemed
        FROM redemption
        WHERE redemption_status = 'COMPLETED'
        ORDER BY redemption_id
        LIMIT 15
    """)

    with engine.connect() as connection:
        rows = connection.execute(query).mappings().all()
        flagged = 0

        for row in rows:
            detected, reason = detect_excess_redemption(
                connection,
                row["account_id"],
                row["points_redeemed"],
                redemption_id=row["redemption_id"]
            )
            if detected:
                flagged += 1

    detector_controls_passed = len(rows) == 15 and flagged == 0

    add_check(
        checks,
        "Updated detector accepts normal redemptions",
        len(rows) - flagged,
        "15 accepted, 0 incorrectly flagged",
        detector_controls_passed
    )

    # 5. Run the automated test suite.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", ".\\tests", "-q"],
        capture_output=True,
        text=True
    )

    test_output = result.stdout + "\n" + result.stderr
    match = re.search(r"(\d+) passed", test_output)
    test_count = int(match.group(1)) if match else 0
    tests_passed = result.returncode == 0 and test_count == 6

    add_check(
        checks,
        "Automated test suite",
        test_count,
        "6 tests passed",
        tests_passed,
        test_output.strip()[-1000:]
    )

    passed = sum(c["status"] == "PASS" for c in checks)
    failed = sum(c["status"] == "FAIL" for c in checks)

    report = {
        "project": "Loyalty Points Management System",
        "validation_date": datetime.now().isoformat(timespec="seconds"),
        "checks_passed": passed,
        "checks_failed": failed,
        "overall_status": "PASS" if failed == 0 else "REVIEW REQUIRED",
        "checks": checks
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "enhanced_validation_report.json"

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4)

    print("\nENHANCED PROJECT VALIDATION")
    print("=" * 55)

    for check in checks:
        print(
            f"{check['status']}: {check['check']} "
            f"(Actual: {check['actual']}, Expected: {check['expected']})"
        )

    print("\nChecks passed:", passed)
    print("Checks failed:", failed)
    print("Overall status:", report["overall_status"])
    print("Report saved:", output_file)


if __name__ == "__main__":
    run_validation()
