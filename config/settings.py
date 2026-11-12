from pathlib import Path

# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Database settings
DATABASE_NAME = "loyalty_points_db"

# Synthetic data generation settings
RANDOM_SEED = 20261022

CUSTOMER_COUNT = 20_000
ORDER_COUNT = 100_000
POINTS_TRANSACTION_COUNT = 300_000

# Data directories
DATA_DIR = BASE_DIR / "data"

RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
GROUND_TRUTH_DIR = DATA_DIR / "ground_truth"

# Export directories
EXPORT_DIR = BASE_DIR / "exports"

CSV_EXPORT_DIR = EXPORT_DIR / "csv"
JSON_EXPORT_DIR = EXPORT_DIR / "json"
SQL_EXPORT_DIR = EXPORT_DIR / "sql"

# Create directories if they do not exist
for directory in [
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    GROUND_TRUTH_DIR,
    CSV_EXPORT_DIR,
    JSON_EXPORT_DIR,
    SQL_EXPORT_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)

print("Project settings loaded successfully!")