import os
from dotenv import load_dotenv
from flask import Flask, render_template, jsonify
import psycopg2

load_dotenv() # Загружает переменные из файла .env

app = Flask(__name__)

def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "fatigue_monitor"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT", "5432")
    )
    return conn

@app.route('/')
def dashboard():
    """Главная панель диспетчера"""
    return render_template('dashboard.html')

@app.route('/api/operators')
def get_operators():
    """Получить список операторов и их статусы"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.login, s.status, s.start_time, 
               COUNT(e.id_event) as incidents
        FROM users u
        LEFT JOIN sessions s ON u.id_user = s.id_user AND s.status = 'active'
        LEFT JOIN events e ON s.id_session = e.id_session
        WHERE u.role = 'operator'
        GROUP BY u.login, s.status, s.start_time
    """)
    operators = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return jsonify([{
        'login': row[0],
        'status': row[1] if row[1] else 'offline',
        'start_time': str(row[2]) if row[2] else '-',
        'incidents': row[3]
    } for row in operators])

@app.route('/api/incidents')
def get_incidents():
    """Получить последние инциденты"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.login, e.event_type, e.event_time, e.severity
        FROM events e
        JOIN sessions s ON e.id_session = s.id_session
        JOIN users u ON s.id_user = u.id_user
        WHERE e.severity > 0
        ORDER BY e.event_time DESC
        LIMIT 20
    """)
    incidents = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return jsonify([{
        'login': row[0],
        'type': row[1],
        'time': str(row[2]),
        'severity': row[3]
    } for row in incidents])

@app.route('/api/stats')
def get_stats():
    """Получить общую статистику"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Всего операторов
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'operator'")
    total_operators = cursor.fetchone()[0]
    
    # Активные сессии
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'active'")
    active_sessions = cursor.fetchone()[0]
    
    # Инциденты сегодня
    cursor.execute("""
        SELECT COUNT(*) FROM events e
        JOIN sessions s ON e.id_session = s.id_session
        WHERE DATE(e.event_time) = CURRENT_DATE
    """)
    today_incidents = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'total_operators': total_operators,
        'active_sessions': active_sessions,
        'today_incidents': today_incidents
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
