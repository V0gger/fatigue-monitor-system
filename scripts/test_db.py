import psycopg2
import os
from dotenv import load_dotenv
import sys

# Загружаем переменные окружения
load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "fatigue_monitor"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT", "5432")
    )
    cursor = conn.cursor()
    
    # Проверка подключения
    cursor.execute("SELECT version();")
    print("✅ Подключение успешно!")
    print(f"PostgreSQL: {cursor.fetchone()[0][:50]}")
    
    # Проверка таблиц
    cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public';")
    tables = cursor.fetchall()
    print(f"✅ Таблицы в схеме public: {[t[0] for t in tables]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Ошибка подключения к БД: {e}")
    sys.exit(1)