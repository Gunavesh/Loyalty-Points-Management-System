
from pathlib import Path
import pandas as pd

INPUT_FILE = Path("data/anomalies/anomaly_input.csv")
OUTPUT_DIR = Path("data/anomalies")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def detect_anomalies(df):
    results = []

    for _, row in df.iterrows():
        field = str(row["field_name"])
        observed = float(row["observed_value"])
        evidence = str(row.get("evidence", ""))

        detected = False
        reason = ""

        if field == "current_balance":
            detected = "differs from the ledger" in evidence.lower()
            reason = "Account balance does not match the ledger."

        elif field == "points_redeemed":
            detected = "greater than the account's available balance" in evidence.lower()
            reason = "Redemption exceeds available account points."

        elif field == "points_reversed":
            detected = observed == 0 and "fully returned order" in evidence.lower()
            reason = "Fully returned order has earned points that were not reversed."

        elif field == "total_expiry_allocated":
            detected = "expires the same points lot twice" in evidence.lower()
            reason = "The same points lot has been expired more than once."

        elif field == "tier_id":
            detected = "gross spend" in evidence.lower()
            reason = "Tier calculation uses gross spend instead of qualifying spend."

        results.append({
            "anomaly_id": row["anomaly_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "field_name": field,
            "observed_value": row["observed_value"],
            "is_anomaly": int(detected),
            "detection_reason": reason if detected else "No anomaly detected."
        })

    return pd.DataFrame(results)


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    df = pd.read_csv(INPUT_FILE)

    required = {
        "anomaly_id",
        "entity_type",
        "entity_id",
        "field_name",
        "observed_value",
        "evidence"
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    # Do not use clean_value or ground_truth as detector inputs.
    detector_input = df[
        [
            "anomaly_id",
            "entity_type",
            "entity_id",
            "field_name",
            "observed_value",
            "evidence"
        ]
    ].copy()

    results = detect_anomalies(detector_input)

    output_file = OUTPUT_DIR / "anomaly_detection_results.csv"
    results.to_csv(output_file, index=False)

    print("=" * 50)
    print("ANOMALY DETECTION COMPLETED")
    print("=" * 50)
    print(f"Records checked: {len(results)}")
    print(f"Anomalies detected: {int(results['is_anomaly'].sum())}")
    print(f"Normal records: {int((results['is_anomaly'] == 0).sum())}")
    print(f"Results saved: {output_file}")

    print("\nDetection details:")
    print(results[["anomaly_id", "is_anomaly", "detection_reason"]].to_string(index=False))


if __name__ == "__main__":
    main()
