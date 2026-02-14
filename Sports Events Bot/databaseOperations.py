import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta
import requests

def get_db_connection():
    """Возвращает соединение с БД"""
    return psycopg2.connect(
        dbname="sports_events",
        user="postgres",
        password="rodion2005",
        host="localhost",
        client_encoding='UTF8'
    )

def save_user_if_not_exists(telegram_id, username):
    """Сохраняет пользователя в БД, если его ещё нет"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO users (telegram_id, username)
            VALUES (%s, %s)
            ON CONFLICT (telegram_id) DO NOTHING
        """, (telegram_id, username))
        conn.commit()
    except Exception as e:
        print(f"Ошибка сохранения пользователя: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def save_reminder(user_id, match_id, remind_before_hours):
    """Сохраняет напоминание в БД"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
        user_db_id = cursor.fetchone()
        
        if not user_db_id:
            print(f"Пользователь {user_id} не найден в БД")
            return None
        
        cursor.execute("""
            SELECT id FROM reminders 
            WHERE user_id = %s AND match_id = %s AND remind_before_hours = %s AND notified = FALSE
        """, (user_db_id[0], match_id, remind_before_hours))
        
        existing = cursor.fetchone()
        
        if existing:
            print(f"Напоминание уже существует: ID {existing[0]}")
            return existing[0]
        
        cursor.execute("SELECT start_time FROM matches WHERE id = %s", (match_id,))
        match_time = cursor.fetchone()[0]
        
        cursor.execute("""
            INSERT INTO reminders (user_id, match_id, remind_before_hours, notified)
            VALUES (%s, %s, %s::double precision, FALSE)
            RETURNING id;
        """, (user_db_id[0], match_id, remind_before_hours))
        
        reminder_id = cursor.fetchone()[0]
        conn.commit()
        
        total_minutes = remind_before_hours * 60
        print(f"✅ Создано напоминание ID {reminder_id}")
        print(f"  В часах: {remind_before_hours}")
        print(f"  В минутах: {total_minutes}")
        print(f"  Время матча: {match_time}")
        print(f"  Напомнить в: {match_time - timedelta(hours=remind_before_hours)}")
        
        return reminder_id
        
    except Exception as e:
        print(f"❌ Ошибка сохранения напоминания: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()



def get_user_reminders(telegram_id):
    """Получает все напоминания пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute("""
        SELECT r.id, r.remind_before_hours, r.created_at, r.notified,
               m.id as match_id, m.team_home, m.team_away, m.start_time, m.tournament, m.sport_type
        FROM reminders r
        JOIN users u ON r.user_id = u.id
        JOIN matches m ON r.match_id = m.id
        WHERE u.telegram_id = %s AND r.notified = FALSE AND m.start_time > NOW()
        ORDER BY m.start_time ASC;
    """, (telegram_id,))
    
    reminders = []
    for row in cursor.fetchall():
        remind_before_hours = float(row['remind_before_hours'])
        total_minutes = remind_before_hours * 60
        
        print(f"Загрузка напоминания ID {row['id']}: {remind_before_hours} ч. = {total_minutes} мин.")
        
        reminders.append({
            'id': row['id'],
            'remind_before_hours': remind_before_hours,
            'created_at': row['created_at'],
            'match_id': row['match_id'],
            'team_home': row['team_home'],
            'team_away': row['team_away'],
            'start_time': row['start_time'],
            'tournament': row['tournament'],
            'sport_type': row['sport_type'],
            'notified': row['notified']
        })
    
    cursor.close()
    conn.close()
    return reminders

def delete_reminder(reminder_id, telegram_id):
    """Удаляет напоминание"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM reminders 
            WHERE id = %s AND user_id = (SELECT id FROM users WHERE telegram_id = %s)
            RETURNING id;
        """, (reminder_id, telegram_id))
        
        deleted = cursor.fetchone()
        conn.commit()
        return deleted is not None
    except Exception as e:
        print(f"Ошибка удаления напоминания: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def delete_all_user_reminders(telegram_id):
    """Удаляет все напоминания пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM reminders 
            WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)
            RETURNING id;
        """, (telegram_id,))
        
        deleted = cursor.fetchall()
        count = len(deleted)
        conn.commit()
        return count
    except Exception as e:
        print(f"Ошибка удаления всех напоминаний: {e}")
        conn.rollback()
        return 0
    finally:
        cursor.close()
        conn.close()

def get_matches_for_reminders():
    """Получает матчи, по которым нужно отправить напоминания"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute("""
        SELECT m.id, m.team_home, m.team_away, m.start_time, m.tournament, m.sport_type,
               u.telegram_id, r.remind_before_hours, r.id as reminder_id
        FROM matches m
        JOIN reminders r ON m.id = r.match_id
        JOIN users u ON r.user_id = u.id
        WHERE r.notified = FALSE 
          AND m.start_time > NOW()
        ORDER BY m.start_time ASC;
    """)
    
    reminders_to_send = []
    current_time = datetime.now()
    
    for row in cursor.fetchall():
        match_time = row['start_time']
        remind_before = float(row['remind_before_hours'])
        
        # ИЗМЕНЕНИЕ: добавляем 1 минуту к времени напоминания
        # Было: remind_time = match_time - timedelta(hours=remind_before)
        # Стало: 
        remind_time = match_time - timedelta(hours=remind_before) + timedelta(minutes=1)
        
        time_diff_seconds = (current_time - remind_time).total_seconds()
        
        print(f"Проверка напоминания ID {row['reminder_id']}:")
        print(f"  remind_before: {remind_before} ч. ({remind_before*60} мин.)")
        print(f"  match_time: {match_time}")
        print(f"  remind_time (с задержкой 1 мин): {remind_time}")
        print(f"  current_time: {current_time}")
        print(f"  time_diff: {time_diff_seconds} сек.")
        
        # Отправляем, если время наступило (в пределах 30 секунд)
        if -30 <= time_diff_seconds <= 30:
            print(f"  ✅ ПОРА ОТПРАВЛЯТЬ!")
            reminders_to_send.append({
                'telegram_id': row['telegram_id'],
                'match': {
                    'team_home': row['team_home'],
                    'team_away': row['team_away'],
                    'start_time': match_time,
                    'tournament': row['tournament'],
                    'sport_type': row['sport_type']
                },
                'remind_before_hours': remind_before,
                'reminder_id': row['reminder_id']
            })
        elif time_diff_seconds < -30:
            print(f"  ⏳ Еще не время (через {-time_diff_seconds} сек.)")
        else:
            print(f"  ⏰ Опоздали на {time_diff_seconds} сек.")
    
    cursor.close()
    conn.close()
    return reminders_to_send


def mark_reminder_as_notified(reminder_id):
    """Отмечает напоминание как отправленное"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE reminders SET notified = TRUE 
            WHERE id = %s
        """, (reminder_id,))
        conn.commit()
        print(f"✅ Напоминание {reminder_id} отмечено как отправленное")
    except Exception as e:
        print(f"Ошибка обновления напоминания: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def get_match_by_id(match_id):
    """Получает информацию о матче по ID"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute("""
        SELECT id, team_home, team_away, start_time, tournament, sport_type
        FROM matches
        WHERE id = %s;
    """, (match_id,))
    
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if row:
        return {
            'id': row['id'],
            'team_home': row['team_home'],
            'team_away': row['team_away'],
            'start_time': row['start_time'],
            'tournament': row['tournament'],
            'sport_type': row['sport_type']
        }
    return None

def get_matches_by_sport_for_selection(sport, limit=20):
    """Получает матчи для выбора в напоминании"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute("""
        SELECT id, team_home, team_away, start_time, tournament
        FROM matches
        WHERE sport_type = %s AND start_time > NOW()
        ORDER BY start_time ASC
        LIMIT %s;
    """, (sport, limit))
    
    matches = []
    for row in cursor.fetchall():
        matches.append({
            'id': row['id'],
            'team_home': row['team_home'],
            'team_away': row['team_away'],
            'start_time': row['start_time'],
            'tournament': row['tournament']
        })
    
    cursor.close()
    conn.close()
    return matches

def get_matches_as_dicts(sport):
    """Получает матчи для отображения"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute("""
        SELECT team_home, team_away, start_time, tournament
        FROM matches
        WHERE start_time > NOW() and sport_type = %s
        ORDER BY start_time ASC;
    """, (sport,))
    
    matches = []
    for row in cursor.fetchall():
        matches.append({
            'team_home': row['team_home'],
            'team_away': row['team_away'],
            'start_time': row['start_time'],
            'tournament': row['tournament']
        })
    
    cursor.close()
    conn.close()
    return matches

def format_matches_text(matches, sport_type):
    """Форматирует список матчей в читаемый текст"""
    if not matches:
        return f"😕 Ближайших {sport_type} матчей не найдено"
    
    emoji = "⚽" if sport_type == "football" else "🏀"
    sport_name = "футбольных" if sport_type == "football" else "баскетбольных"
    
    text = f"{emoji} *Ближайшие {sport_name} матчи:*\n\n"
    
    for i, match in enumerate(matches, 1):
        if isinstance(match['start_time'], datetime):
            match_time = match['start_time'].strftime('%d.%m.%Y %H:%M')
        else:
            match_time = str(match['start_time'])
        
        text += (
            f"{i}. *{match['team_home']}* 🆚 *{match['team_away']}*\n"
            f"   🏆 {match['tournament']}\n"
            f"   📅 {match_time}\n\n"
        )
    
    return text

def data_to_db(matches):
    """Сохраняет матчи в БД"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    for match in matches:
        try:
            cursor.execute("""
                INSERT INTO matches 
                (sport_type, team_home, team_away, start_time, tournament, source_api, external_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (sport_type, external_id) DO NOTHING
            """, (
                match["sport_type"],
                match["team_home"],
                match["team_away"],
                match["start_time"],
                match.get("tournament", ""),
                "football_api" if match["sport_type"] == "football" else "basketball_api", 
                match["external_id"]
            ))
        except Exception as e:
            print(f"Ошибка при сохранении матча {match['external_id']}: {e}")
    
    conn.commit()
    cursor.close()
    conn.close()

def remove_past_matches():
    """Удаляет прошедшие матчи"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("TRUNCATE TABLE matches RESTART IDENTITY CASCADE;")
        conn.commit()
        print("✅ Таблица matches очищена")
    except Exception as e:
        print(f"Ошибка при удалении матчей: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def save_matches_to_db():
    """Получает матчи из API и сохраняет в БД"""
    url_football = "https://api.football-data.org/v4/matches"
    headers_football = {"X-Auth-Token": "30747c81b0b04c1eb15510de935206ab"}
    response_football = requests.get(url_football, headers=headers_football)
    print(f"Football API Status: {response_football.status_code}")
    
    if response_football.status_code == 200:
        data_football = response_football.json()
        matches_football = []
        for match in data_football.get("matches", []):
            matches_football.append({
                "sport_type": "football",
                "team_home": match["homeTeam"]["name"],
                "team_away": match["awayTeam"]["name"],
                "start_time": match["utcDate"], 
                "tournament": match["competition"]["name"],
                "external_id": str(match["id"])
            })    
        data_to_db(matches_football) 
        print(f"Добавлено {len(matches_football)} футбольных матчей")
    else:
        print(f"Football API Error: {response_football.text[:200]}")
           
    url_basketball = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    response_basketball = requests.get(url_basketball, timeout=10)
    print(f"Basketball API Status: {response_basketball.status_code}")
    
    if response_basketball.status_code == 200:
        data_basketball = response_basketball.json()
        matches_basketball = []
        for event in data_basketball.get("events", []):
            home_team = away_team = None
            if event.get("competitions"):
                for competitor in event["competitions"][0].get("competitors", []):
                    if competitor.get("homeAway") == "home":
                        home_team = competitor["team"]["displayName"]
                    else:
                        away_team = competitor["team"]["displayName"]
        
            if not home_team or not away_team:
                name = event.get("name", "")
                if " at " in name:
                    away_team, home_team = name.split(" at ", 1)
                elif " vs " in name:
                    home_team, away_team = name.split(" vs ", 1)
                else:
                    continue 
        
            matches_basketball.append({
                "sport_type": "basketball",
                "team_home": home_team,
                "team_away": away_team,
                "start_time": event.get("date", ""),
                "tournament": "NBA", 
                "external_id": str(event.get("id", ""))
            })
    
        data_to_db(matches_basketball)
        print(f"Добавлено {len(matches_basketball)} баскетбольных матчей")
    else:
        print(f"Basketball API Error: {response_basketball.text[:200]}")
    
    print("Обновление данных завершено!")