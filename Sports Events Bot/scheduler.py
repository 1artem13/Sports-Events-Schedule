import schedule
import time
import threading
from datetime import datetime
from databaseOperations import save_matches_to_db, remove_past_matches

def update_all_sports():
    """Обновление всех спортивных данных"""
    print("="*50)
    print(f"🔄 НАЧАЛО ОБНОВЛЕНИЯ: {datetime.now()}")
    try:
        remove_past_matches()
        save_matches_to_db()
        print(f"✅ ОБНОВЛЕНИЕ ЗАВЕРШЕНО: {datetime.now()}")
    except Exception as e:
        print(f"❌ ОШИБКА ПРИ ОБНОВЛЕНИИ: {e}")
        
    print("="*50 + "\n")

def run_scheduler():
    """Функция для запуска планировщика в потоке"""
    schedule.every().day.at("06:00").do(update_all_sports)

    print("🚀 Планировщик запущен. Обновление каждый день в 06:00")
    print("⏳ Ожидание первого запланированного обновления...")

    update_all_sports()

    while True:
        schedule.run_pending()
        time.sleep(300)

scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

print("✅ Планировщик запущен в фоновом потоке")