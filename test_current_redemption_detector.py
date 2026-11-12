
from sqlalchemy import text
from config.db_config import engine
from src.anomalies.anomaly_detector_v2 import detect_excess_redemption

query = text("""
    SELECT
        redemption_id,
        account_id,
        points_redeemed
    FROM redemption
    WHERE redemption_status = 'COMPLETED'
    ORDER BY redemption_id
    LIMIT 15
""")

with engine.connect() as connection:
    rows = connection.execute(query).mappings().all()

    flagged = 0

    print("\nUPDATED DETECTOR - NORMAL CONTROL TEST")
    print("=" * 60)

    for row in rows:
        detected, reason = detect_excess_redemption(
            connection,
            row["account_id"],
            row["points_redeemed"],
            redemption_id=row["redemption_id"]
        )

        if detected:
            flagged += 1

        print(
            row["redemption_id"],
            "| Account:", row["account_id"],
            "| Flagged:", detected,
            "|", reason
        )

    total = len(rows)

    print("\nRESULTS")
    print("=" * 40)
    print("Total controls:", total)
    print("Incorrectly flagged:", flagged)
    print("Correctly accepted:", total - flagged)

    if total:
        print(
            "False-positive rate:",
            f"{flagged / total * 100:.2f}%"
        )
