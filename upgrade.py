import psycopg2
from app.config import settings

database_url = settings.DATABASE_SYNC_URL.replace(
    "postgresql+psycopg2://", "postgresql://"
)
conn = psycopg2.connect(database_url)
cur = conn.cursor()

# Спочатку подивимось хто є
cur.execute("SELECT email, subscription_tier, plots_limit FROM users")
print("Всі користувачі:")
for row in cur.fetchall():
    print(f"  {row[0]} | {row[1]} | ліміт: {row[2]}")

# Оновити
cur.execute("""
    UPDATE users SET
        subscription_tier = 'premium_plus',
        subscription_expires_at = '2030-12-31 23:59:59+00',
        plots_limit = 999,
        plants_limit = 9999
    WHERE email = 'illinci21@gmail.com'
    RETURNING email, subscription_tier, plots_limit, plants_limit
""")

row = cur.fetchone()
if row:
    print(f"\n✅ Оновлено: {row[0]} → {row[1]} (ділянок: {row[2]}, рослин: {row[3]})")
else:
    print("\n❌ Користувача illinci21@gmail.com не знайдено")

conn.commit()
conn.close()
