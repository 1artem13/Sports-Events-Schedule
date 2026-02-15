"""
Unit-тесты для проверки отдельных функций
"""

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from databaseOperations import format_matches_text
from bot import format_minutes

class TestFormatFunctions:
    """Тестирование функций форматирования"""
    
    def test_format_minutes_basic(self):
        """Тест базового форматирования минут"""
        assert format_minutes(30) == "30 мин."
        assert format_minutes(60) == "1 ч."
        assert format_minutes(90) == "1 ч. 30 мин."
        assert format_minutes(120) == "2 ч."
    
    def test_format_minutes_days(self):
        """Тест форматирования дней"""
        assert format_minutes(1440) == "1 д."
        assert format_minutes(1500) == "1 д. 1 ч."
        assert format_minutes(2880) == "2 д."
    
    def test_format_minutes_rounding(self):
        """Тест округления минут"""
        assert format_minutes(30.2) == "30 мин."
        assert format_minutes(30.6) == "31 мин."
        assert format_minutes(59.9) == "1 ч."
    
    def test_format_matches_text_football(self):
        """Тест форматирования футбольных матчей"""
        matches = [
            {
                'team_home': 'Спартак',
                'team_away': 'ЦСКА',
                'start_time': datetime(2024, 12, 25, 19, 30),
                'tournament': 'РПЛ'
            }
        ]
        
        result = format_matches_text(matches, 'football')
        
        assert "⚽" in result
        assert "футбольных" in result
        assert "Спартак" in result
        assert "ЦСКА" in result
        assert "25.12.2024 19:30" in result
    
    def test_format_matches_text_basketball(self):
        """Тест форматирования баскетбольных матчей"""
        matches = [
            {
                'team_home': 'Lakers',
                'team_away': 'Warriors',
                'start_time': datetime(2024, 12, 25, 20, 0),
                'tournament': 'NBA'
            }
        ]
        
        result = format_matches_text(matches, 'basketball')
        
        assert "🏀" in result
        assert "баскетбольных" in result
        assert "Lakers" in result
        assert "Warriors" in result
        assert "NBA" in result
    
    def test_format_matches_text_empty(self):
        """Тест форматирования при пустом списке"""
        result = format_matches_text([], 'football')
        assert "не найдено" in result


class TestDatabaseFunctions:
    """Тестирование функций работы с БД (с моками)"""
    
    @patch('databaseOperations.get_db_connection')
    def test_delete_reminder_success(self, mock_get_db_connection):
        """Тест успешного удаления напоминания"""
        from databaseOperations import delete_reminder
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [1]
        
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_cursor
        mock_context.__exit__.return_value = None
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_context
        mock_get_db_connection.return_value = mock_conn
        
        result = delete_reminder(123, 456789)
        
        assert result is True
        mock_conn.commit.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
