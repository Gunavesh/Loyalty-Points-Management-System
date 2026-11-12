import os
from sqlalchemy import create_engine
from urllib.parse import quote_plus

DB_USER = "root"
DB_PASSWORD = os.getenv("LOYALTY_DB_PASSWORD")
DB_HOST = "localhost"
DB_PORT = "3306"
DB_NAME = "loyalty_points_db"

if not DB_PASSWORD:
    raise ValueError("Please set LOYALTY_DB_PASSWORD environment variable.")

DATABASE_URL = (
    f"mysql+mysqlconnector://{DB_USER}:"
    f"{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600
)