-- ============================================
-- Создание структуры БД для системы мониторинга усталости
-- Версия: 2.0 (объединена users + profiles)
-- ============================================

-- Удаляем старые таблицы если существуют
DROP TABLE IF EXISTS events CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Таблица пользователей (объединена с profiles)
CREATE TABLE users (
    id_user SERIAL PRIMARY KEY,
    login VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    max_ear NUMERIC(5,4) CHECK (max_ear > 0.0 AND max_ear < 0.5),
    ear_threshold NUMERIC(5,4) CHECK (ear_threshold > 0.0 AND ear_threshold < 0.5),
    profile_updated_at TIMESTAMP DEFAULT NOW(),
    role VARCHAR(20) DEFAULT 'operator' CHECK (role IN ('operator', 'dispatcher', 'admin'))
);

-- Таблица сессий
CREATE TABLE sessions (
    id_session SERIAL PRIMARY KEY,
    id_user INTEGER NOT NULL,
    start_time TIMESTAMP NOT NULL DEFAULT NOW(),
    end_time TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'finished')),
    FOREIGN KEY (id_user) REFERENCES users(id_user) ON DELETE CASCADE
);

-- Таблица событий
CREATE TABLE events (
    id_event SERIAL PRIMARY KEY,
    id_session INTEGER NOT NULL,
    event_time TIMESTAMP DEFAULT NOW(),
    event_type VARCHAR(30) NOT NULL CHECK (event_type IN ('blink', 'long_blink', 'microsleep', 'perclos_alert')),
    duration NUMERIC(6,2) DEFAULT 0,
    ear_value NUMERIC(5,4) DEFAULT 0,
    perclos_value NUMERIC(5,2) DEFAULT 0,
    severity INTEGER DEFAULT 0 CHECK (severity = 0 OR severity = 1 OR severity = 2),
    FOREIGN KEY (id_session) REFERENCES sessions(id_session) ON DELETE CASCADE
);

-- Индексы для ускорения запросов
CREATE INDEX idx_events_session ON events(id_session);
CREATE INDEX idx_events_time ON events(event_time);
CREATE INDEX idx_sessions_user ON sessions(id_user);

-- ============================================
-- Тестовые данные для проверки
-- ============================================

-- Создаём тестового пользователя
INSERT INTO users (login, password_hash, max_ear, ear_threshold, role) 
VALUES ('operator_01', 'hashed_password_123', 0.3200, 0.2560, 'operator');

-- Проверяем что создалось
SELECT * FROM users;