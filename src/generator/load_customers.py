
import pandas as pd
from sqlalchemy import text

from config.db_config import engine

CSV_PATH = "data/raw/customers.csv"


def load_customers():
    # Read the generated customer CSV
    df = pd.read_csv(
        CSV_PATH,
        dtype={"phone": "string"},
        parse_dates=["registration_date"]
    )

    required_columns = [
        "customer_name",
        "email",
        "phone",
        "registration_date",
        "customer_status"
    ]

    if list(df.columns) != required_columns:
        raise ValueError("Customer CSV columns do not match the expected structure.")

    if df["email"].duplicated().any():
        raise ValueError("Duplicate emails found in customer CSV.")

    if df.isnull().any().any():
        raise ValueError("Missing values found in customer CSV.")

    records = df.to_dict(orient="records")

    # Insert customers safely in one database transaction
    with engine.begin() as connection:

        existing_count = connection.execute(
            text("SELECT COUNT(*) FROM customer")
        ).scalar_one()

        if existing_count > 0:
            raise ValueError(
                f"Customer table already contains {existing_count} records. "
                "Loading stopped to prevent duplicate insertion."
            )

        insert_query = text("""
            INSERT INTO customer (
                customer_name,
                email,
                phone,
                registration_date,
                customer_status
            )
            VALUES (
                :customer_name,
                :email,
                :phone,
                :registration_date,
                :customer_status
            )
        """)

        for start in range(0, len(records), 1000):
            batch = records[start:start + 1000]
            connection.execute(insert_query, batch)

        final_count = connection.execute(
            text("SELECT COUNT(*) FROM customer")
        ).scalar_one()

        if final_count != len(df):
            raise ValueError(
                f"Expected {len(df)} customers, but found {final_count}."
            )

    print("CUSTOMER DATA LOADED SUCCESSFULLY")
    print("CSV records:", len(df))
    print("Database records:", final_count)


if __name__ == "__main__":
    load_customers()
