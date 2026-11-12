
import random
import pandas as pd

from datetime import datetime
from faker import Faker
from config.settings import CUSTOMER_COUNT, RANDOM_SEED


def generate_customers(count=CUSTOMER_COUNT):
    """Generate reproducible synthetic customer records."""

    fake = Faker("en_IN")
    fake.seed_instance(RANDOM_SEED)

    rng = random.Random(RANDOM_SEED)

    # Fixed date range ensures reproducibility
    start_date = datetime(2021, 11, 12)
    end_date = datetime(2026, 11, 12, 23, 59, 59)

    customers = []

    for _ in range(count):
        customer = {
            "customer_name": fake.name(),
            "email": fake.unique.email(),
            "phone": fake.phone_number()[:20],
            "registration_date": fake.date_time_between(
                start_date=start_date,
                end_date=end_date
            ),
            "customer_status": rng.choices(
                ["ACTIVE", "INACTIVE", "SUSPENDED"],
                weights=[85, 10, 5],
                k=1
            )[0]
        }

        customers.append(customer)

    return pd.DataFrame(customers)


if __name__ == "__main__":
    df = generate_customers()

    print("CUSTOMER GENERATION SUCCESSFUL")
    print("Total customers:", len(df))
    print("\nFirst five customers:")
    print(df.head())

    print("\nCustomer status distribution:")
    print(df["customer_status"].value_counts())

    print("\nDuplicate emails:", df["email"].duplicated().sum())
    print("Missing values:", df.isnull().sum().sum())

    output_path = "data/raw/customers.csv"
    df.to_csv(output_path, index=False)

    print("\nSaved to:", output_path)
