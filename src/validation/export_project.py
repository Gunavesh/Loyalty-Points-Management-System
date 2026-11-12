
from pathlib import Path
import json
import pandas as pd
from sqlalchemy import text
from config.db_config import engine

CSV_DIR = Path("exports/csv")
JSON_DIR = Path("exports/json")
SQL_DIR = Path("exports/sql")

for folder in [CSV_DIR, JSON_DIR, SQL_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

TABLES = [
    "customer",
    "loyaltyaccount",
    "tier",
    "rule",
    "orders",
    "orderline",
    "returns",
    "returnline",
    "pointstransaction",
    "pointslot",
    "pointsallocation",
    "reward",
    "redemption",
    "expirybatch",
    "pointsdebt",
    "pointsdebtsettlement",
    "ruleapplication",
    "customertierhistory",
    "processedrequest",
    "auditevent"
]


def main():
    summary = {}

    with engine.connect() as connection:
        existing_tables = set(
            connection.execute(text("SHOW TABLES")).scalars().all()
        )

        for table in TABLES:
            if table not in existing_tables:
                print(f"SKIPPED: {table} (table not found)")
                continue

            df = pd.read_sql(
                text(f"SELECT * FROM `{table}`"),
                connection
            )

            csv_path = CSV_DIR / f"{table}.csv"
            json_path = JSON_DIR / f"{table}.json"

            df.to_csv(csv_path, index=False)

            records = json.loads(
                df.to_json(
                    orient="records",
                    date_format="iso",
                    force_ascii=False
                )
            )

            with open(json_path, "w", encoding="utf-8") as file:
                json.dump(records, file, indent=2, ensure_ascii=False)

            summary[table] = {
                "records": len(df),
                "csv_file": str(csv_path),
                "json_file": str(json_path)
            }

            print(f"EXPORTED: {table} - {len(df)} records")

    summary_path = JSON_DIR / "export_summary.json"

    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=4)

    print("\nEXPORT COMPLETED")
    print(f"Tables exported: {len(summary)}")
    print(f"Total records: {sum(x['records'] for x in summary.values())}")
    print(f"CSV folder: {CSV_DIR}")
    print(f"JSON folder: {JSON_DIR}")


if __name__ == "__main__":
    main()
