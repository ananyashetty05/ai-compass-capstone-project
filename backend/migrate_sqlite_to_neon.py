import sqlite3
import psycopg
from app.core.config import settings

SQLITE_PATH = "../aicompass.db"

TABLES = {
    "users": [
        "user_id", "name", "email", "password_hash", "user_group",
        "routing_preferences", "accessibility_preferences",
        "theme_preference", "preferences_customized", "created_at"
    ],
    "feedback": [
        "feedback_id", "user_id", "routing_id", "model_id", "model_name",
        "query_summary", "task_type", "domain", "rating", "thumbs",
        "reasons", "comment", "created_at"
    ],
    "model_satisfaction": [
        "user_id", "model_id", "sum_ratings", "sample_count", "last_updated"
    ],
}

source = sqlite3.connect(SQLITE_PATH)
source.row_factory = sqlite3.Row

target = psycopg.connect(settings.DATABASE_URL)

try:
    with target.transaction():
        for table, columns in TABLES.items():
            rows = source.execute(f"SELECT * FROM {table}").fetchall()

            column_sql = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))

            query = f"""
                INSERT INTO {table} ({column_sql})
                VALUES ({placeholders})
                ON CONFLICT DO NOTHING
            """

            inserted = 0

            for row in rows:
                values = tuple(row[column] for column in columns)
                cursor = target.execute(query, values)
                inserted += cursor.rowcount

            print(
                f"{table}: source={len(rows)}, "
                f"inserted={inserted}, skipped={len(rows)-inserted}"
            )

    print("\nMigration completed successfully.")

finally:
    source.close()
    target.close()
