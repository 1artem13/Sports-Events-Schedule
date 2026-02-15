CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    sport_type VARCHAR(50) NOT NULL,
    team_home VARCHAR(255) NOT NULL,
    team_away VARCHAR(255) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    tournament VARCHAR(255),
    source_api VARCHAR(100),
    external_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sport_type, external_id)
);

CREATE TABLE IF NOT EXISTS reminders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    match_id INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    remind_before_hours FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notified BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_reminders_notified ON reminders(notified);
CREATE INDEX IF NOT EXISTS idx_matches_start_time ON matches(start_time);
CREATE INDEX IF NOT EXISTS idx_reminders_user_id ON reminders(user_id);




