import pandas as pd
from sqlalchemy import text

from config.db_config import engine
from config.tier_rules import TIERS, TIER_EFFECTIVE_FROM


def generate_tiers():
    df = pd.DataFrame(TIERS)

    df["effective_from"] = TIER_EFFECTIVE_FROM
    df["effective_to"] = None
    df["tier_status"] = "ACTIVE"

    return df


def save_tiers():
    df = generate_tiers()

    with engine.begin() as connection:
        for _, row in df.iterrows():
            connection.execute(
                text("""
                    INSERT INTO tier (
                        tier_name,
                        minimum_qualifying_spend,
                        earning_rate,
                        effective_from,
                        effective_to,
                        tier_status
                    )
                    VALUES (
                        :tier_name,
                        :minimum_qualifying_spend,
                        :earning_rate,
                        :effective_from,
                        :effective_to,
                        :tier_status
                    )
                    ON DUPLICATE KEY UPDATE
                        minimum_qualifying_spend =
                            VALUES(minimum_qualifying_spend),
                        earning_rate = VALUES(earning_rate),
                        effective_from = VALUES(effective_from),
                        effective_to = VALUES(effective_to),
                        tier_status = VALUES(tier_status)
                """),
                row.to_dict()
            )

    print("TIER GENERATION SUCCESSFUL")
    print(df.to_string(index=False))


if __name__ == "__main__":
    save_tiers()