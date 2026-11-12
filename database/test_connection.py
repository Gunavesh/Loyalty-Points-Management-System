from sqlalchemy import inspect
from config.db_config import engine

def test_database():
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        print("DATABASE CONNECTION: SUCCESS")
        print(f"Database tables found: {len(tables)}")

        for table in tables:
            print(f"- {table}")

        if len(tables) == 20:
            print("\nAll 20 tables are accessible!")
        else:
            print("\nWARNING: Expected 20 tables.")

    except Exception as error:
        print("DATABASE CONNECTION: FAILED")
        print(error)

if __name__ == "__main__":
    test_database()