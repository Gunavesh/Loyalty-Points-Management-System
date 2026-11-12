
import pandas as pd
from sqlalchemy import text
from config.db_config import engine

OUTPUT_FILE = "data/anomalies/redemption_control_evaluation.csv"

query = text("""
    SELECT
        r.redemption_id,
        r.account_id,
        r.points_redeemed,
        p.transaction_id,
        p.points_change,
        p.transaction_date,
        p.created_at,

        COALESCE((
            SELECT SUM(p2.points_change)
            FROM pointstransaction p2
            WHERE p2.account_id = r.account_id
              AND (
                    p2.transaction_date < p.transaction_date
                    OR (
                        p2.transaction_date = p.transaction_date
                        AND p2.created_at < p.created_at
                    )
                    OR (
                        p2.transaction_date = p.transaction_date
                        AND p2.created_at = p.created_at
                        AND p2.transaction_id < p.transaction_id
                    )
              )
        ), 0) AS balance_before_redemption

    FROM redemption r
    JOIN pointstransaction p
        ON p.redemption_id = r.redemption_id

    WHERE r.redemption_status = 'COMPLETED'
    ORDER BY r.redemption_id
    LIMIT 15
""")

with engine.connect() as connection:
    rows = connection.execute(query).mappings().all()

results = []

for row in rows:
    available = int(row["balance_before_redemption"])
    redeemed = int(row["points_redeemed"])

    valid = available >= redeemed

    results.append({
        "redemption_id": row["redemption_id"],
        "account_id": row["account_id"],
        "points_available_before": available,
        "points_redeemed": redeemed,
        "valid_redemption": valid,
        "classification": "NORMAL" if valid else "INVALID"
    })

df = pd.DataFrame(results)
df.to_csv(OUTPUT_FILE, index=False)

print("\nREDEMPTION CONTROL EVALUATION")
print("=" * 45)
print(df.to_string(index=False))
print("\nTotal records:", len(df))
print("Normal:", (df["valid_redemption"] == True).sum())
print("Invalid:", (df["valid_redemption"] == False).sum())
print("Saved to:", OUTPUT_FILE)
