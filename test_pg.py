import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    dbname=os.getenv("PG_DB"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASS"),
    host=os.getenv("PG_HOST", "localhost"),
    port=int(os.getenv("PG_PORT", "5432")),
)

cur = conn.cursor()
cur.execute("SELECT current_database(), current_user, inet_server_port();")
print(cur.fetchone())

cur.close()
conn.close()
