import pytest
import sys
import os
from datetime import datetime, timedelta
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from databaseOperations import (
    save_user_if_not_exists,
    save_reminder,
    get_user_reminders,
    delete_reminder,
    get_match_by_id,
    get_db_connection,
    mark_reminder_as_notified
)


class TestReminderIntegration:
    """Интеграционные тесты для напоминаний"""
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Подготовка и очистка тестовых данных"""
        self.test_telegram_id = 999999999
        self.test_username = "test_user"
        
        self.cleanup_test_data()
        
        yield 
        
        self.cleanup_test_data()
    
    def cleanup_test_data(self):
        """Очистка тестовых данных"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM reminders 
                WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)
            """, (self.test_telegram_id,))
            
            cursor.execute("DELETE FROM users WHERE telegram_id = %s", (self.test_telegram_id,))
            
            cursor.execute("DELETE FROM matches WHERE external_id LIKE 'test_match_%'")
            
            conn.commit()
            cursor.close()
            conn.close()
        except:
            pass
    
    def create_test_match(self):
        """Создает тестовый матч в БД"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        match_time = datetime.now() + timedelta(hours=24)
        external_id = f"test_match_{int(time.time())}"
        
        try:
            cursor.execute("""
                INSERT INTO matches 
                (sport_type, team_home, team_away, start_time, tournament, source_api, external_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                "football",
                "Тест Хоум",
                "Тест Эвей",
                match_time,
                "Тестовый турнир",
                "test_api",
                external_id
            ))
            
            result = cursor.fetchone()
            conn.commit()
            match_id = result[0]
            
            return match_id
        except Exception as e:
            print(f"Ошибка создания матча: {e}")
            conn.rollback()
            return None
        finally:
            cursor.close()
            conn.close()
    
    def test_user_creation(self):
        """Тест 1: Создание пользователя"""
        save_user_if_not_exists(self.test_telegram_id, self.test_username)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", 
                      (self.test_telegram_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        assert user is not None, "Пользователь должен быть создан"
    
    def test_reminder_creation_and_deletion(self):
        """Тест 2: Создание и удаление напоминания"""
        save_user_if_not_exists(self.test_telegram_id, self.test_username)
        
        match_id = self.create_test_match()
        assert match_id is not None, "Матч должен создаться"
        
        reminder_id = save_reminder(self.test_telegram_id, match_id, 2.0)
        assert reminder_id is not None, "Напоминание должно создаться"
        
        reminders = get_user_reminders(self.test_telegram_id)
        assert len(reminders) > 0, "У пользователя должны быть напоминания"
        
        result = delete_reminder(reminder_id, self.test_telegram_id)
        assert result is True, "Удаление должно быть успешным"
        
        reminders_after = get_user_reminders(self.test_telegram_id)
        for rem in reminders_after:
            assert rem['id'] != reminder_id, "Напоминание не должно существовать после удаления"
    
    def test_reminder_notification_flag(self):
        """Тест 3: Отметка напоминания как отправленного"""
        save_user_if_not_exists(self.test_telegram_id, self.test_username)
        
        match_id = self.create_test_match()
        reminder_id = save_reminder(self.test_telegram_id, match_id, 2.0)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT notified FROM reminders WHERE id = %s", (reminder_id,))
        notified = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        assert notified is False, "Новое напоминание не должно быть отмеченным"
        
        mark_reminder_as_notified(reminder_id)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT notified FROM reminders WHERE id = %s", (reminder_id,))
        notified = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        assert notified is True, "После отметки notified должен быть True"
