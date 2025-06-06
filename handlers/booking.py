from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from database.db import get_connection
from config import ADMINS, PAYMENT_LINK
from datetime import datetime, timedelta

router = Router()

@router.message(F.text.contains("Записаться"))
async def show_available_trainings(message: Message):
    user_id = message.from_user.id
    now = datetime.now()

    with get_connection() as conn:
        cursor = conn.cursor()

        cutoff_date = (now - timedelta(days=1)).isoformat()

        cursor.execute("""
            SELECT t.id, t.date,
                (SELECT COUNT(*) FROM slots WHERE training_id = t.id) AS booked_count,
                (SELECT COUNT(*) FROM slots WHERE training_id = t.id AND user_id = ?) AS user_booked
            FROM trainings t
            WHERE t.status = 'open' AND datetime(t.date) > ?
            ORDER BY t.date ASC
            LIMIT 6
        """, (user_id, cutoff_date))

        trainings = cursor.fetchall()

    if not trainings:
        await message.answer("❌ Пока нет открытых тренировок.")
        return

    keyboard = []
    for training_id, date_str, booked_count, user_booked in trainings:
        date_obj = datetime.fromisoformat(date_str)
        label = date_obj.strftime("%d.%m %H:%M")

        user_booked = user_booked or 0
        booked_count = booked_count or 0

        # Пометка
        if user_booked > 0:
            label += " ✅"
        elif booked_count >= 7:  # или 5 — если известно, какая группа
            label += " ❌"

        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"select_training:{training_id}")])

    await message.answer("Выберите тренировку для записи:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("select_training:"))
async def show_group_choice(callback: CallbackQuery):
    training_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    with get_connection() as conn:
        cursor = conn.cursor()

        # Проверка: уже записан?
        cursor.execute("""
            SELECT COUNT(*) FROM slots
            WHERE training_id = ? AND user_id = ? AND status IN ('pending', 'confirmed')
        """, (training_id, user_id))
        already = cursor.fetchone()[0]

        if already:
            await callback.answer("Вы уже записаны на эту тренировку.", show_alert=True)
            return

        # Получение даты тренировки
        cursor.execute("SELECT date FROM trainings WHERE id = ?", (training_id,))
        row = cursor.fetchone()

    if not row:
        await callback.message.edit_text("❌ Тренировка не найдена.")
        return

    date_str = datetime.fromisoformat(row[0]).strftime("%d.%m.%Y %H:%M")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚡ Быстрая группа", callback_data=f"book:{training_id}:fast"),
            InlineKeyboardButton(text="🏁 Стандартная группа", callback_data=f"book:{training_id}:standard")
        ]
    ])

    await callback.message.edit_text(f"📅 Тренировка {date_str}\n\nВыбери группу:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("book:"))
async def choose_channel(callback: CallbackQuery):
    _, training_id, group = callback.data.split(":")
    training_id = int(training_id)

    # Новый список каналов для каждой группы
    GROUP_CHANNELS = {
        "fast": ["R2", "F2", "F4", "R7", "R8"],
        "standard": ["R1", "R2", "F2", "F4", "R7", "R8", "L1"]
    }

    all_channels = GROUP_CHANNELS.get(group)
    if not all_channels:
        await callback.message.edit_text("❌ Неизвестная группа.")
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT channel FROM slots
            WHERE training_id = ? AND group_name = ? AND status IN ('pending', 'confirmed')
        """, (training_id, group))
        taken = [row[0] for row in cursor.fetchall()]

    available = [ch for ch in all_channels if ch not in taken]

    if not available:
        await callback.message.edit_text("❌ В этой группе нет свободных каналов.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ch, callback_data=f"reserve:{training_id}:{group}:{ch}")]
        for ch in available
    ])

    await callback.message.edit_text(
        f"🧩 Свободные каналы в группе <b>{'Быстрая' if group == 'fast' else 'Стандартная'}</b>:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("reserve:"))
async def reserve_slot(callback: CallbackQuery):
    _, training_id, group, channel = callback.data.split(":")
    training_id = int(training_id)
    user_id = callback.from_user.id
    username = callback.from_user.username

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT subscription FROM users WHERE user_id = ?", (user_id,))
        sub = cursor.fetchone()
        sub_count = sub[0] if sub else 0

        if sub_count > 0:
            payment_type = "subscription"
        else:
            payment_type = "manual"

        cursor.execute("""
            INSERT INTO slots (training_id, user_id, group_name, channel, status, created_at, payment_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            training_id,
            user_id,
            group,
            channel,
            "pending",
            datetime.now().isoformat(),
            payment_type
        ))
        slot_id = cursor.lastrowid
        conn.commit()

    if payment_type == "subscription":
        await notify_admins_about_booking(
    callback.bot, training_id, user_id, group, channel, slot_id,
    username, payment_type, callback.from_user.full_name
)
        await callback.message.edit_text(
            f"✅ Вы забронировали <b>{channel}</b> в группе <b>{'Быстрая' if group == 'fast' else 'Стандартная'}</b>.\n"
            f"🎟 Оплата через абонемент. Ожидается подтверждение администратора."
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"confirm_payment:{slot_id}")]
        ])
        await callback.message.edit_text(
            f"✅ Вы забронировали <b>{channel}</b> в группе <b>{'Быстрая' if group == 'fast' else 'Стандартная'}</b>.\n"
            f"💳 Пожалуйста, оплатите <b>800₽</b> по ссылке: <a href='{PAYMENT_LINK}'>ОПЛАТИТЬ</a>\n"
            f"После оплаты нажмите кнопку ниже.", reply_markup=keyboard
        )

@router.callback_query(F.data.startswith("confirm_payment:"))
async def confirm_manual_payment(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    username = callback.from_user.username

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT training_id, group_name, channel FROM slots WHERE id = ?", (slot_id,))
        row = cursor.fetchone()

    if not row:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    training_id, group, channel = row
    await notify_admins_about_booking(
    callback.bot, training_id, user_id, group, channel, slot_id,
    username, "manual", callback.from_user.full_name
)
    await callback.message.edit_text("🔔 Администратор уведомлён. Ожидайте подтверждения оплаты.")

async def notify_admins_about_booking(bot, training_id, user_id, group, channel, slot_id, username, payment_type, full_name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nickname, system, subscription FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

    nickname = user[0] if user else "-"
    system = user[1] if user else "-"
    remaining = user[2] if user else 0

    # Показываем @username если он есть, иначе — кликабельное имя
    user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>{full_name}</a>"

    payment_desc = "🎟 Абонемент" if payment_type == "subscription" else "💳 Реквизиты"
    if payment_type == "subscription":
        payment_desc += f" (осталось {remaining})"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm:{slot_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{slot_id}")
    ]])

    text = (
        f"📥 Новая запись на тренировку:\n"
        f"👤 {user_link} (ID: <code>{user_id}</code>)\n"
        f"🏁 Группа: <b>{'Быстрая' if group == 'fast' else 'Стандартная'}</b>\n"
        f"📡 Канал: <b>{channel}</b>\n"
        f"🎮 OSD: <b>{nickname}</b>\n"
        f"🎥 Видео: <b>{system}</b>\n"
        f"{payment_desc}\n"
        f"⏳ Ожидает подтверждения оплаты"
    )

    for admin in ADMINS:
        await bot.send_message(admin, text, reply_markup=kb)

@router.callback_query(F.data.startswith("confirm:"))
async def confirm_booking(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])

    with get_connection() as conn:
        cursor = conn.cursor()

        # Получаем все необходимые данные
        cursor.execute("""
            SELECT s.user_id, s.group_name, s.channel, s.payment_type, t.date, u.nickname, u.system
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            JOIN users u ON s.user_id = u.user_id
            WHERE s.id = ?
        """, (slot_id,))
        row = cursor.fetchone()

    if not row:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    user_id, group, channel, payment_type, training_date, nickname, system = row
    username = callback.from_user.username  # Это админ, не участник

    # Подтвердить и списать абонемент, если нужно
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE slots SET status = 'confirmed' WHERE id = ?", (slot_id,))
        if payment_type == "subscription":
            cursor.execute("UPDATE users SET subscription = subscription - 1 WHERE user_id = ?", (user_id,))
        conn.commit()

    await callback.message.edit_text("✅ Оплата подтверждена")
    await callback.bot.send_message(user_id, "✅ Ваша запись подтверждена! Ждём вас на тренировке 🛸")

    # Формируем сообщение админу
    group_label = "⚡ Быстрая" if group == "fast" else "🏁 Стандартная"
    date_fmt = datetime.fromisoformat(training_date).strftime("%d.%m.%Y %H:%M")
    payment_text = "🎟 Абонемент" if payment_type == "subscription" else "💳 Оплата по реквизитам"
    name = callback.from_user.full_name
    user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>{name}</a>"

    admin_message = (
        f"✅ Вы подтвердили запись:\n"
        f"👤 {user_link} (ID: <code>{user_id}</code>)\n"
        f"📅 Дата: <b>{date_fmt}</b>\n"
        f"🏁 Группа: <b>{group_label}</b>\n"
        f"📡 Канал: <b>{channel}</b>\n"
        f"🎮 OSD: <b>{nickname}</b>\n"
        f"🎥 Видео: <b>{system}</b>\n"
        f"{payment_text}"
    )

    await callback.bot.send_message(callback.from_user.id, admin_message)


@router.callback_query(F.data.startswith("reject:"))
async def reject_booking(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])
    with get_connection() as conn:
        cursor = conn.cursor()

        # Получаем данные о слоте и пользователе
        cursor.execute("""
            SELECT s.user_id, s.status, s.group_name, s.channel, s.payment_type, t.date,
                   u.nickname, u.system
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            JOIN users u ON s.user_id = u.user_id
            WHERE s.id = ?
        """, (slot_id,))
        row = cursor.fetchone()

        if not row:
            await callback.answer("❌ Запись не найдена.", show_alert=True)
            return

        user_id, status, group, channel, payment_type, training_date, nickname, system = row

        if status == "confirmed":
            await callback.answer("❗ Эта запись уже подтверждена другим админом.", show_alert=True)
            return

        # Удаляем запись
        cursor.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
        conn.commit()

    # Уведомление пользователя
    await callback.message.edit_text("❌ Запись отклонена")
    await callback.bot.send_message(user_id, "❌ Ваша запись была отклонена. Попробуйте снова или свяжитесь с админом.")

    # Формируем лог для админа
    group_label = "⚡ Быстрая" if group == "fast" else "🏁 Стандартная"
    date_fmt = datetime.fromisoformat(training_date).strftime("%d.%m.%Y %H:%M")
    payment_text = "🎟 Абонемент" if payment_type == "subscription" else "💳 Оплата по реквизитам"
    name = callback.from_user.full_name
    user_link = f"<a href='tg://user?id={user_id}'>{name}</a>"

    admin_message = (
        f"❌ Вы отклонили запись:\n"
        f"👤 {user_link} (ID: <code>{user_id}</code>)\n"
        f"📅 Дата: <b>{date_fmt}</b>\n"
        f"🏁 Группа: <b>{group_label}</b>\n"
        f"📡 Канал: <b>{channel}</b>\n"
        f"🎮 OSD: <b>{nickname}</b>\n"
        f"🎥 Видео: <b>{system}</b>\n"
        f"{payment_text}"
    )

    await callback.bot.send_message(callback.from_user.id, admin_message)

@router.message(F.text.contains("Мои записи"))
async def show_my_bookings(message: Message):
    user_id = message.from_user.id

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.date, s.group_name, s.channel, s.status
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            WHERE s.user_id = ?
            ORDER BY t.date ASC
        """, (user_id,))
        rows = cursor.fetchall()

    if not rows:
        await message.answer("📭 У вас пока нет записей на тренировки.")
        return

    lines = ["📅 Ваши записи на тренировки:\n"]
    for date_str, group, channel, status in rows:
        date_fmt = datetime.fromisoformat(date_str).strftime("%d.%m.%Y %H:%M")
        group_label = "⚡ Быстрая" if group == "fast" else "🏁 Стандартная"
        status_label = "⏳ Ожидает" if status == "pending" else "✅ Подтверждена"
        lines.append(f"— {date_fmt} | {group_label} | {channel} | {status_label}")

    await message.answer("\n".join(lines))