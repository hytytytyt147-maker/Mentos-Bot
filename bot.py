import io
import os
import time
import sqlite3
import zipfile
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Вставляем ваш точный рабочий токен
TOKEN = "8947024615:AAHf9RX5nl70knZ3aKy_4WRuhn5f83vHkIs"
ADMIN_ID = 1924047464

bot = Bot(token=TOKEN)
dp = Dispatcher()

if not os.path.exists("temp_photos"):
    os.makedirs("temp_photos")


def init_db():
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS orders ("
        "order_number TEXT PRIMARY KEY, "
        "status TEXT DEFAULT 'готовится', "
        "photo_count INTEGER DEFAULT 0, "
        "user_name TEXT, "
        "user_id INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS settings ("
        "key TEXT PRIMARY KEY, value TEXT)"
    )
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) "
        "VALUES ('target_chat', ?)",
        (str(ADMIN_ID),),
    )
    conn.commit()
    conn.close()


init_db()


def get_target_chat():
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT value FROM settings WHERE key='target_chat'"
    )
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else ADMIN_ID


def update_target_chat(new_id):
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) "
        "VALUES ('target_chat', ?)",
        (str(new_id),),
    )
    conn.commit()
    conn.close()
class ClientStates(StatesGroup):
    waiting_for_wb_number = State()
    sending_photos = State()


class AdminStates(StatesGroup):
    waiting_for_chat_id = State()
    waiting_for_order_id = State()


def get_client_main_kb():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="📥 Отправить фотографии"))
    builder.add(types.KeyboardButton(text="📦 Проверить мой заказ"))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def get_client_upload_kb():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="✅ Завершить и отправить"))
    builder.add(types.KeyboardButton(text="❌ Отменить всё"))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def get_admin_kb():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="📊 Все заказы WB"))
    builder.add(types.KeyboardButton(text="🔄 Изменить статус"))
    builder.add(types.KeyboardButton(text="⚙️ Настройка чата"))
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)


def get_status_inline(order_id):
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(
            text="⏳ Готовится",
            callback_data=f"st_prep_{order_id}",
        )
    )
    builder.add(
        types.InlineKeyboardButton(
            text="✅ Готово (Уведомить)",
            callback_data=f"st_done_{order_id}",
        )
    )
    builder.adjust(2)
    return builder.as_markup()


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "Приветствуем, владелец магазина!\n"
            "Это ваша рабочая админ-панель заказа фото.",
            reply_markup=get_admin_kb(),
        )
    else:
        await message.answer(
            f"Привет, {message.from_user.first_name}!\n"
            "Добро пожаловать в бота печати фотографий.\n"
            "Здесь вы можете передать ваши фото по заказу WB.",
            reply_markup=get_client_main_kb(),
        )


@dp.message(F.text == "📥 Отправить фотографии")
async def client_start_upload(
    message: types.Message, state: FSMContext
):
    await state.set_state(ClientStates.waiting_for_wb_number)
    await message.answer(
        "Шаг 1: Введите номер вашего заказа (сборочного задания) WB:",
        reply_markup=types.ReplyKeyboardRemove(),
    )


@dp.message(ClientStates.waiting_for_wb_number)
async def client_get_number(
    message: types.Message, state: FSMContext
):
    # Исправлено: жесткая защита от не-текстовых сообщений (фотографий)
    if not message.text:
        await message.answer(
            "⚠️ Ошибка! Пожалуйста, отправьте номер заказа "
            "обычным текстом (только цифры):"
        )
        return

    num = message.text.strip()
    if not num.isdigit() or len(num) < 4:
        await message.answer("Неверный номер заказа. Введите только цифры:")
        return

    await state.update_data(wb_num=num, photo_paths=[])
    await state.set_state(ClientStates.sending_photos)
    await message.answer(
        f"Заказ №{num} успешно привязан!\n\n"
        "Шаг 2: Начните отправлять мне фотографии.\n"
        "Когда отправите ВСЕ фотографии, нажмите кнопку ниже:",
        reply_markup=get_client_upload_kb(),
    )
@dp.message(ClientStates.sending_photos, F.photo)
async def client_handle_photo(
    message: types.Message, state: FSMContext
):
    data = await state.get_data()
    paths = data.get("photo_paths", [])

    photo_id = message.photo[-1].file_id
    file_info = await bot.get_file(photo_id)

    local_path = f"temp_photos/{photo_id}.jpg"
    await bot.download_file(file_info.file_path, local_path)

    paths.append(local_path)
    await state.update_data(photo_paths=paths)

    if len(paths) % 5 == 0 or len(paths) == 1:
        await message.answer(f"Принято фотографий: {len(paths)} шт.")


@dp.message(
    ClientStates.sending_photos, F.text == "✅ Завершить и отправить"
)
async def client_finish_upload(
    message: types.Message, state: FSMContext
):
    data = await state.get_data()
    paths = data.get("photo_paths", [])
    num = data.get("wb_num")

    if not paths:
        await message.answer("Вы не отправили ни одной фотографии!")
        return

    await message.answer(
        "⏳ Создаю архив и отправляю владельцу магазина... Подождите."
    )

    zip_name = f"Order_{num}.zip"
    with zipfile.ZipFile(
        zip_name, "w", zipfile.ZIP_DEFLATED
    ) as zipf:
        for p in paths:
            if os.path.exists(p):
                zipf.write(p, os.path.basename(p))
                os.remove(p)

    user_info = (
        f"{message.from_user.full_name} "
        f"(@{message.from_user.username})"
    )
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO orders "
        "(order_number, status, photo_count, user_name, user_id) "
        "VALUES (?, 'готовится', ?, ?, ?)",
        (num, len(paths), user_info, message.from_user.id),
    )
    conn.commit()
    conn.close()

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    report_text = (
        f"📥 **НОВЫЙ ЗАКАЗ НА ПЕЧАТЬ ФОТО!**\n\n"
        f"📦 **Номер заказа WB:** `{num}`\n"
        f"📸 **Количество фото:** {len(paths)} шт.\n"
        f"📅 **Дата отправки:** {now_str}\n"
        f"👤 **Кто заказал:** {user_info}\n"
    )

    target = get_target_chat()
    try:
        input_file = types.FSInputFile(zip_name)
        # Исправлено: добавлен обязательный аргумент text / caption
        await bot.send_document(
            chat_id=target, document=input_file, caption=report_text
        )
    except Exception as e:
        await bot.send_message(
            chat_id=ADMIN_ID, text=f"Ошибка отправки архива: {e}"
        )

    if os.path.exists(zip_name):
        os.remove(zip_name)

    await state.clear()
    await message.answer(
        "🎉 Ваш заказ успешно отправлен в обработку!\n"
        "Мы известим вас здесь, когда фотографии будут распечатаны.",
        reply_markup=get_client_main_kb(),
    )


@dp.message(ClientStates.sending_photos, F.text == "❌ Отменить всё")
async def client_cancel(message: types.Message, state: FSMContext):
    data = await state.get_data()
    paths = data.get("photo_paths", [])
    for p in paths:
        if os.path.exists(p):
            os.remove(p)
    await state.clear()
    await message.answer(
        "Загрузка отменена. Все файлы стерты.",
        reply_markup=get_client_main_kb(),
    )


@dp.message(F.text == "📦 Проверить мой заказ")
async def client_check_order_start(message: types.Message):
    await message.answer("Введите номер вашего заказа WB для проверки:")


@dp.message(F.text == "📊 Все заказы WB")
async def admin_all_orders(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT order_number, status, photo_count FROM orders"
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("📋 База заказов пуста.")
        return

    text = "📋 **Текущие заказы на печать:**\n\n"
    for r in rows:
        text += (
            f"📦 №`{r[0]}` | Статус: *{r[1]}* | "
            f"Фото: {r[2]} шт.\n"
        )
    await message.answer(text, parse_mode="Markdown")


@dp.message(F.text == "🔄 Изменить статус")
async def admin_change_status_start(
    message: types.Message, state: FSMContext
):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_for_order_id)
    await message.answer("Введите номер заказа для смены статуса:")


@dp.message(AdminStates.waiting_for_order_id)
async def admin_change_status_get_id(
    message: types.Message, state: FSMContext
):
    if message.from_user.id != ADMIN_ID:
        return
    order_id = message.text.strip()
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT order_number FROM orders WHERE order_number=?",
        (order_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        await message.answer("❌ Заказ с таким номером не найден.")
        await state.clear()
        return

    await state.clear()
    await message.answer(
        f"Выберите новый статус для заказа №{order_id}:",
        reply_markup=get_status_inline(order_id),
    )


@dp.callback_query(F.data.startswith("st_"))
async def admin_confirm_status(callback: types.CallbackQuery):
    data = callback.data.split("_")
    action = data[1]
    order_id = data[2]

    new_status = "готовится" if action == "prep" else "готово"

    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE orders SET status=? WHERE order_number=?",
        (new_status, order_id),
    )
    cursor.execute(
        "SELECT user_id FROM orders WHERE order_number=?", (order_id,)
    )
    user_row = cursor.fetchone()
    conn.close()

    await callback.answer(f"Статус изменен на '{new_status}'")
    await callback.message.edit_text(
        f"✅ Статус заказа №`{order_id}` изменен на *{new_status}*.",
        parse_mode="Markdown",
    )

    if action == "done" and user_row and user_row[0]:
        try:
            await bot.send_message(
                chat_id=int(user_row[0]),
                text=f"🎉 **Отличные новости!**\n"
                f"Ваш заказ фотографий №`{order_id}` распечатан "
                f"и готов к отправке через Wildberries!",
                parse_mode="Markdown",
            )
        except Exception:
            pass


@dp.message(F.text == "⚙️ Настройка чата")
async def admin_cfg_chat(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_for_chat_id)
    await message.answer(
        "Введите ID чата для отправки ZIP-архивов.\n"
        f"Текущий ID: `{get_target_chat()}`"
    )


@dp.message(AdminStates.waiting_for_chat_id)
async def admin_save_chat(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    new_id = message.text.strip()
    try:
        update_target_chat(int(new_id))
        await message.answer(
            f"✅ Чат для архивов изменен на `{new_id}`!"
        )
    except Exception:
        await message.answer("Ошибка. Введите корректный числовой ID.")
    await state.clear()


@dp.message(F.text)
async def client_check_any_order(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        return
    text = message.text.strip()
    if not text.isdigit():
        return
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status, photo_count FROM orders WHERE order_number=?",
        (text,),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        await message.answer(
            f"📦 **Статус заказа №{text}:**\n\n"
            f"Состояние: *{row[0]}*\n"
            f"Всего фотографий: {row[1]} шт.",
            parse_mode="Markdown",
        )
    else:
        await message.answer(
            "❌ Заказ с таким номером пока не найден в системе."
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(dp.start_polling(bot))
