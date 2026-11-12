
import pandas as pd
from sqlalchemy import text

from config.db_config import engine


def generate_accounts():
    """Create one loyalty account for every customer."""

    with engine.connect() as connection:
        customers = pd.read_sql(
            text("""
                SELECT customer_id, registration_date
                FROM customer
                ORDER BY customer_id
            """),
            connection
        )

        bronze = connection.execute(
            text("""
                SELECT tier_id
                FROM tier
                WHERE tier_name = 'BRONZE'
            """)
        ).scalar_one()

    accounts = pd.DataFrame({
        "account_id": customers["customer_id"].apply(
            lambda customer_id: f"LOY-{customer_id}"
        ),
        "customer_id": customers["customer_id"],
        "tier_id": bronze,
        "current_balance": 0,
        "qualifying_spend": 0.00,
        "account_status": "ACTIVE",
        "opened_at": customers["registration_date"]
    })

    return accounts


def save_accounts():
    accounts = generate_accounts()

    with engine.begin() as connection:
        for record in accounts.to_dict(orient="records"):
            connection.execute(
                text("""
                    INSERT INTO loyaltyaccount (
                        account_id,
                        customer_id,
                        tier_id,
                        current_balance,
                        qualifying_spend,
                        account_status,
                        opened_at
                    )
                    VALUES (
                        :account_id,
                        :customer_id,
                        :tier_id,
                        :current_balance,
                        :qualifying_spend,
                        :account_status,
                        :opened_at
                    )
                    ON DUPLICATE KEY UPDATE
                        account_id = VALUES(account_id)
                """),
                record
            )

    print("LOYALTY ACCOUNT GENERATION SUCCESSFUL")
    print("Total accounts:", len(accounts))
    print("Unique customer IDs:", accounts["customer_id"].nunique())
    print("Duplicate account IDs:", accounts["account_id"].duplicated().sum())
    print("Initial balance:", accounts["current_balance"].sum())
    print("Initial qualifying spend:", accounts["qualifying_spend"].sum())


if __name__ == "__main__":
    save_accounts()
