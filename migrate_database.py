#!/usr/bin/env python3
"""
Миграция базы данных: удаление поля group_name из таблицы slots
"""

import sqlite3
import os

def migrate_database():
    # Путь к базе данных в продакшене
    db_path = "database/bot.db"
    
    if not os.path.exists(db_path):
        print("❌ База данных не найдена!")
        return
    
    print("🔄 Начинаем миграцию базы данных...")
    print(f"📁 База данных: {db_path}")
    
    # Создаем резервную копию
    backup_path = f"{db_path}.backup"
    if not os.path.exists(backup_path):
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"✅ Создана резервная копия: {backup_path}")
    else:
        print(f"ℹ️  Резервная копия уже существует: {backup_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли поле group_name
        cursor.execute("PRAGMA table_info(slots)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'group_name' not in columns:
            print("ℹ️  Поле group_name уже отсутствует в таблице slots")
            print("✅ Миграция не требуется")
            return
        
        print("🔍 Найдено поле group_name, начинаем миграцию...")
        
        # Создаем новую таблицу без поля group_name
        cursor.execute("""
            CREATE TABLE slots_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                training_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                payment_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (training_id) REFERENCES trainings(id)
            )
        """)
        
        # Копируем данные, исключая поле group_name
        cursor.execute("""
            INSERT INTO slots_new (id, training_id, user_id, channel, payment_type, status, created_at)
            SELECT id, training_id, user_id, channel, payment_type, status, created_at
            FROM slots
        """)
        
        # Подсчитываем количество записей
        cursor.execute("SELECT COUNT(*) FROM slots_new")
        count = cursor.fetchone()[0]
        print(f"📊 Скопировано записей: {count}")
        
        # Удаляем старую таблицу
        cursor.execute("DROP TABLE slots")
        
        # Переименовываем новую таблицу
        cursor.execute("ALTER TABLE slots_new RENAME TO slots")
        
        conn.commit()
        print("✅ Миграция завершена успешно!")
        print("📝 Поле group_name удалено из таблицы slots")
        print(f"💾 Все {count} записей сохранены")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка миграции: {e}")
        print("🔄 Восстанавливаем из резервной копии...")
        import shutil
        shutil.copy2(backup_path, db_path)
        print("✅ База данных восстановлена из резервной копии")
        raise e
    
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()