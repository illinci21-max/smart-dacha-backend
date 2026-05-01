"""
Очистити кеш погоди щоб примусити перезавантаження з 16-денним прогнозом.
Запустити: python clear_weather_cache.py
"""
import redis
import psycopg2
from app.config import settings

# 1. Clear Redis cache
try:
    r = redis.Redis(host='localhost', port=6379, db=0)
    keys = r.keys('weather_fetch:*')
    if keys:
        r.delete(*keys)
        print(f"✅ Redis: видалено {len(keys)} ключів weather_fetch:*")
    else:
        print("✅ Redis: кеш вже порожній")
except Exception as e:
    print(f"⚠️ Redis: {e} (можливо не запущений)")

# 2. Delete old cached weather data from PostgreSQL
try:
    database_url = settings.DATABASE_SYNC_URL.replace(
        "postgresql+psycopg2://", "postgresql://"
    )
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()
    cur.execute("DELETE FROM weather_daily_cache WHERE date < CURRENT_DATE")
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    print(f"✅ PostgreSQL: видалено {deleted} старих записів погоди")
except Exception as e:
    print(f"⚠️ PostgreSQL: {e}")

print("\n🔄 Перезапустіть backend: uvicorn app.main:app --reload")
print("   Перший запит погоди завантажить 16-денний прогноз з OpenMeteo")
