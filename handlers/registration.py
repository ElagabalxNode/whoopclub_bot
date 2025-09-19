from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from database.db import get_connection
from keyboards.menu import get_main_keyboard
from config import REQUIRED_CHAT_ID

router = Router()

class Registration(StatesGroup):
    enter_nickname = State()
    select_system = State()

#Для добычы id чата
#@router.message()
#async def debug_chat_id(message: Message):
#    await message.answer(f"Chat ID: <code>{message.chat.id}</code>", parse_mode="HTML")

@router.message(F.text == "/start")
async def start_registration(message: Message, state: FSMContext):
    user_id = message.from_user.id

    # 🔒 Проверка на членство в чате
    try:
        chat_member = await message.bot.get_chat_member(REQUIRED_CHAT_ID, user_id)
        print(f"DEBUG: User {user_id} status in chat {REQUIRED_CHAT_ID}: {chat_member.status}")
        if chat_member.status in ("left", "kicked"):
            raise ValueError("Not in group")
    except Exception as e:
        print(f"DEBUG: Error checking chat membership: {e}")
        await message.answer(
            "❌ Чтобы зарегистрироваться, вступи в наш чат:\n"
            "👉 https://t.me/+R3Bjy51_7admMDY6",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # Проверка регистрации
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nickname, system FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

    if row:
        nickname, system = row
        await message.answer(
            f"👋 Ты уже зарегистрирован!\n\n"
            f"👤 Никнейм: {nickname}\n"
            f"🛠️ Система: {system}",
            reply_markup=get_main_keyboard()
        )
        return

    # Если не зарегистрирован — начинаем регистрацию
    await message.answer("👋 Привет! Назови свой никнейм / OSD:")
    await state.set_state(Registration.enter_nickname)

@router.message(Registration.enter_nickname)
async def process_nickname(message: Message, state: FSMContext):
    await state.update_data(nickname=message.text)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="HDZero"), KeyboardButton(text="Аналог")],
            [KeyboardButton(text="DJI"), KeyboardButton(text="WS")]
        ],
        resize_keyboard=True
    )
    await message.answer("🚁 Выбери систему, на которой ты летаешь:", reply_markup=keyboard)
    await state.set_state(Registration.select_system)

@router.message(Registration.select_system)
async def finish_registration(message: Message, state: FSMContext):
    data = await state.update_data(system=message.text)
    await state.clear()

    user_id = message.from_user.id
    nickname = data["nickname"]
    system = data["system"]

    # Сохраняем в БД
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, nickname, system) VALUES (?, ?, ?)",
            (user_id, nickname, system)
        )
        conn.commit()

    await message.answer(
        f"✅ Регистрация завершена!\n\n"
        f"👤 Никнейм: {nickname}\n"
        f"🛠️ Система: {system}",
        reply_markup=get_main_keyboard()
    )
    welcome_message = (
    "👋 Добро пожаловать во ВупКлуб Казань!\n\n"
    "🏁 Здесь ты можешь:\n"
    "• 🗓 Записаться на тренировку\n"
    "• 🎟 Забронировать место\n"
    "• 👥 Встретить других пилотов\n"
    "• 🚁 Отточить навыки вуп-рейсинга\n\n"
    "📍 Где проходят тренировки?\n"
    "🏢 Центр «Сотворение»\n"
    "📍 Адрес: проспект Бурхана Шахиди, д.17\n"
    "🗺 Инструкция по проходу — в закрепленном видео\n"
    "🗺 <a href='https://yandex.ru/maps/-/CLeIZMm9'>Открыть в Яндекс.Картах</a>\n\n"
    "🕘 Когда мы летаем?\n"
    "📅 Каждый вторник 19:00–21:00\n"
    "📅 Каждый четверг 18:00–20:00\n"
    "👉 Актуальные тренировки доступны по кнопке <b>«Записаться»</b> в меню.\n\n"
    "👟 Важно: ковер на полу → сменка не нужна.\n"
    "🪑 Для удобства — столы и стулья есть!\n\n"
    "⚡️ Есть много удлинителей, розеток точно хватит\n\n"
    "⚡ Регламент:\n"
    "• 1S вупы 65–75 мм\n"
    "• Поддержка Walksnail, Analog, HDZero\n"
)

    await message.answer(welcome_message, parse_mode="HTML")