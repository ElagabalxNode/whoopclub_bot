# Инструкции по миграции базы данных

## Проблема
Ошибка `OperationalError: no such column: s.group_name` возникает потому, что код обновлен для работы без поля `group_name`, но в продакшене база данных еще содержит это поле.

## Решение

### 1. Остановить бота
```bash
sudo systemctl stop whoopclub_bot
```

### 2. Запустить миграцию
```bash
cd /home/carrotfpv/whoopclub_bot
python3 migrate_database.py
```

### 3. Запустить бота
```bash
sudo systemctl start whoopclub_bot
```

## Что делает миграция
- Создает резервную копию базы данных
- Удаляет поле `group_name` из таблицы `slots`
- Сохраняет все остальные данные

## Проверка
После миграции команда `🔁/resend_pending` должна работать без ошибок.

## Откат (если нужно)
Если что-то пойдет не так, восстановите из резервной копии:
```bash
cp database/bot.db.backup database/bot.db
```