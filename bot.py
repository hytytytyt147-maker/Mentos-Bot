import io
import os
import time
import sqlite3
import zipfile
import shutil
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram import BaseMiddleware
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = "8947024615:AAHf9RX5nl70knZ3aKy_4WRuhn5f83v4bIs"
SUPER_ADMIN = 1924047464

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

if not os.path.exists("temp_photos"):
    os.makedirs("temp_photos")
def init_db():
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS orders ("
        "order_number TEXT PRIMARY KEY, "
        "status TEXT DEFAULT 'готовится', "
        "photo_count TEXT DEFAULT '0', "
        "user_name TEXT, "
        "user_id INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS settings ("
        "key TEXT PRIMARY KEY, value TEXT)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS admins ("
        "user_id INTEGER PRIMARY KEY)"
    )
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) "
        "VALUES ('target_chat', ?)",
        (str(SUPER_ADMIN),),
    )
    cursor.execute(
        "INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
        (SUPER_ADMIN,),
    )
    conn.commit()
    conn.close()


init_db()
def is_admin(user_id):
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id FROM admins WHERE user_id=?", (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def add_admin_db(user_id):
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,)
    )
    conn.commit()
    conn.close()


def remove_admin_db(user_id):
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM admins WHERE user_id=?", (user_id,)
    )
    conn.commit()
    conn.close()


# ОШИБКА ИСПРАВЛЕНА ТУТ: Берется точный индекс элемента из кортежа row[0]
def get_target_chat():
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT value FROM settings WHERE key='target_chat'"
    )
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else SUPER_ADMIN
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


async def daily_clean_job():
    if os.path.exists("temp_photos"):
        shutil.rmtree("temp_photos")
        os.makedirs("temp_photos")


scheduler.add_job(daily_clean_job, "interval", hours=24)


@dp.startup()
async def on_startup():
    scheduler.start()


class AntiSpamMiddleware(BaseMiddleware):

    def __init__(self, limit: int = 2):
        self.limit = limit
        self.storage = {}
        super().__init__()
    async def __call__(self, handler, event: types.Message, data: dict):
        if not event.from_user:
            return await handler(event, data)
        if event.photo:
            return await handler(event, data)
        user_id = event.from_user.id
        now = time.time()
        if user_id in self.storage:
            last_time = self.storage[user_id]
            if now - last_time < self.limit:
                if not is_admin(user_id):
                    return await event.answer(
                        "⚠️ Пожалуйста, не спамьте запросами!"
                    )
                return
        self.storage[user_id] = now
        return await handler(event, data)


dp.message.middleware(AntiSpamMiddleware(limit=1))


class ClientStates(StatesGroup):
    waiting_for_wb_number = State()
    sending_photos = State()


class AdminStates(StatesGroup):
    waiting_for_chat_id = State()
    waiting_for_new_admin = State()
    waiting_for_del_admin = State()


def get_client_main_kb():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="📥 Отправить фотографии"))
    builder.add(types.KeyboardButton(text="📦 Проверить мой заказ"))
    builder.add(types.KeyboardButton(text="🆘 Помощь / Поддержка"))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)
def get_client_upload_kb():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="✅ Завершить и отправить"))
    builder.add(types.KeyboardButton(text="❌ Отменить всё"))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def get_confirm_upload_inline():
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="🚀 Да, отправить", callback_data="confirm_force_send"))
    builder.add(types.InlineKeyboardButton(text="📸 Нет, дозагрузить", callback_data="confirm_keep_upload"))
    builder.adjust(1)
    return builder.as_markup()


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if is_admin(message.from_user.id):
        await message.answer("Админ-панель запущена.", reply_markup=get_admin_kb())
    else:
        await message.answer(f"Привет, {message.from_user.first_name}!\nДобро пожаловать в бота печати фотографий WB.", reply_markup=get_client_main_kb())


@dp.message(F.text == "🆘 Помощь / Поддержка")
async def client_support(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="🤝 Написать менеджеру", url="https://t.me"))
    await message.answer("👋 Возникли трудности или появились вопросы по заказу?\n\nНажмите кнопку ниже, и мы с радостью поможем решить ваш вопрос в кратчайшие сроки!", reply_markup=builder.as_markup())
@dp.message(F.text == "📥 Отправить фотографии")
async def client_start_upload(message: types.Message, state: FSMContext):
    await state.set_state(ClientStates.waiting_for_wb_number)
    await message.answer("Введите номер вашего заказа WB:", reply_markup=types.ReplyKeyboardRemove())


@dp.message(ClientStates.waiting_for_wb_number)
async def client_get_number(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ Отправьте номер обычным текстом:")
        return
    num = message.text.strip()
    if not num.isdigit() or len(num) < 4:
        await message.answer("Неверный номер. Введите только цифры:")
        return
    await state.update_data(wb_num=num, photo_paths=[])
    await state.set_state(ClientStates.sending_photos)
    await message.answer(f"Заказ №{num} привязан!\n\nШаг 2: Начните отправлять фотографии ИЛИ просто пришлите интернет-ссылку на файлы/облако.", reply_markup=get_client_upload_kb())


@dp.message(ClientStates.sending_photos, F.photo)
async def client_handle_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    paths = data.get("photo_paths", [])
    photo_id = message.photo[-1].file_id
    file_info = await bot.get_file(photo_id)
    local_path = f"temp_photos/{photo_id}.jpg"
    await bot.download_file(file_info.file_path, local_path)
    paths.append(local_path)
    await state.update_data(photo_paths=paths)
@dp.message(ClientStates.sending_photos, F.text.startswith("http"))
async def client_handle_any_link(message: types.Message, state: FSMContext):
    data = await state.get_data()
    num = data.get("wb_num")
    link = message.text.strip()
    user_info = f"{message.from_user.full_name} (@{message.from_user.username})"
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO orders VALUES (?, 'готовится', 'По ссылке', ?, ?)", (num, user_info, message.from_user.id))
    conn.commit()
    conn.close()
    report_text = f"📥 **НОВЫЙ ЗАКАЗ ПО ССЫЛКЕ!**\n\n📦 **WB:** `{num}`\n🌐 **Ссылка:** {link}\n📅 **Дата заказа:** {now_str}\n👤 **Клиент:** {user_info}\n"
    target = get_target_chat()
    try:
        await bot.send_message(chat_id=target, text=report_text, disable_web_page_preview=False)
    except Exception as e:
        await bot.send_message(chat_id=SUPER_ADMIN, text=f"Ошибка отправки: {e}")
    await state.clear()
    await message.answer("🎉 Ваша ссылка успешно принята! Мы известим вас о готовности заказа.", reply_markup=get_client_main_kb())


@dp.message(ClientStates.sending_photos, F.text == "✅ Завершить и отправить")
async def client_pre_validate_upload(message: types.Message, state: FSMContext):
    data = await state.get_data()
    paths = data.get("photo_paths", [])
    if not paths:
        await message.answer("Вы не отправили ни одной фотографии! Если вы хотите отправить ссылку, просто вставьте её в чат.")
        return
    count = len(paths)
    target_tariff = 25
    if count >= 30 and count <= 70: target_tariff = 50
    elif count > 70: target_tariff = 100
    diff = count - target_tariff
    if diff != 0:
        word = "больше" if diff > 0 else "меньше"
        msg = f"📊 **Контроль количества фотографий:**\n\nВы отправили: `{count}` шт.\nТариф: `{target_tariff}` шт.\n\n⚠️ Это на `{abs(diff)}` шт {word}. Отправить заказ продавцу?"
        await message.answer(msg, reply_markup=get_confirm_upload_inline(), parse_mode="Markdown")
    else:
        msg = f"📊 **Контроль количества фотографий:**\n\nВы отправили ровно: `{count}` шт.\nВсе лимиты тарифа совпадают! Отправить заказ продавцу?"
        await message.answer(msg, reply_markup=get_confirm_upload_inline(), parse_mode="Markdown")


async def execute_final_upload(message: types.Message, state: FSMContext):
    data = await state.get_data()
    paths = data.get("photo_paths", [])
    num = data.get("wb_num")
    await message.answer("⏳ Создаю ZIP-архив... Подождите.", reply_markup=get_client_main_kb())
    zip_name = f"Order_{num}.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zipf:
        for p in paths:
            if os.path.exists(p):
                zipf.write(p, os.path.basename(p))
                os.remove(p)
    user_info = f"{message.from_user.full_name} (@{message.from_user.username})"
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO orders VALUES (?, 'готовится', ?, ?, ?)", (num, str(len(paths)), user_info, message.from_user.id))
    conn.commit()
    conn.close()
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    report_text = f"📥 **НОВЫЙ ЗАКАЗ (АРХИВ)!**\n\n📦 **WB:** `{num}`\n📸 **Фото:** {len(paths)} шт.\n📅 **Дата заказа:** {now_str}\n👤 **Клиент:** {user_info}\n"
    target = get_target_chat()
    try:
        input_file = types.FSInputFile(zip_name)
        await bot.send_document(chat_id=target, document=input_file, caption=report_text, parse_mode="Markdown")
    except Exception as e:
        await bot.send_message(chat_id=SUPER_ADMIN, text=f"Ошибка отправки: {e}")
    if os.path.exists(zip_name): os.remove(zip_name)
    await state.clear()
    await message.answer("🎉 Ваш заказ успешно отправлен продавцу!")


@dp.callback_query(F.data == "confirm_force_send")
async def cb_force_send(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    await execute_final_upload(callback.message, state)


@dp.callback_query(F.data == "confirm_keep_upload")
async def cb_keep_upload(callback: types.CallbackQuery):
    await callback.answer()
    await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    await callback.message.answer("Продолжайте отправку фотографий.")


@dp.message(ClientStates.sending_photos, F.text == "❌ Отменить всё")
async def client_cancel(message: types.Message, state: FSMContext):
    data = await state.get_data()
    paths = data.get("photo_paths", [])
    for p in paths:
        if os.path.exists(p): os.remove(p)
    await state.clear()
    await message.answer("Загрузка отменена.", reply_markup=get_client_main_kb())


@dp.message(F.text == "📦 Проверить мой заказ")
async def client_check_order_start(message: types.Message):
    await message.answer("Введите номер вашего заказа WB для проверки:")
def get_admin_kb():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="📊 Все заказы WB"))
    builder.add(types.KeyboardButton(text="🔄 Изменить статус"))
    builder.add(types.KeyboardButton(text="👥 Админы / Чат"))
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)


def get_admin_panel_inline():
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="📁 Изменить чат архивов", callback_data="adm_setchat"))
    builder.add(types.InlineKeyboardButton(text="➕ Добавить администратора", callback_data="adm_addnew"))
    builder.add(types.InlineKeyboardButton(text="❌ Удалить администратора", callback_data="adm_delold"))
    builder.adjust(1)
    return builder.as_markup()


def get_cancel_inline():
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="❌ Отмена", callback_data="adm_cancel_input"))
    return builder.as_markup()


def get_status_inline(order_id):
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="⏳ Готовится", callback_data=f"st_prep_{order_id}"))
    builder.add(types.InlineKeyboardButton(text="✅ Готово", callback_data=f"st_done_{order_id}"))
    builder.add(types.InlineKeyboardButton(text="🗑️ Удалить заказ", callback_data=f"st_del_{order_id}"))
    builder.add(types.InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="adm_back_to_list"))
    builder.adjust(2, 1, 1)
    return builder.as_markup()


@dp.message(F.text == "📊 Все заказы WB")
async def admin_all_orders(message: types.Message):
    if not is_admin(message.from_user.id): return
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT order_number, status, photo_count FROM orders")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await message.answer("📋 База заказов пуста.")
        return
    text = "📋 **Текущие заказы:**\n\n"
    for order_number, status, photo_count in rows:
        text += f"📦 №`{order_number}` | Статус: *{status}* | Информация: {photo_count}\n"
    await message.answer(text, parse_mode="Markdown")


@dp.message(F.text == "🔄 Изменить статус")
async def admin_change_status_inline(message: types.Message):
    if not is_admin(message.from_user.id): return
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT order_number, status FROM orders")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await message.answer("❌ Активных заказов нет.")
        return
    builder = InlineKeyboardBuilder()
    for order_number, status in rows:
        icon = "⏳" if status == "готовится" else "✅"
        builder.add(types.InlineKeyboardButton(text=f"{icon} №{order_number}", callback_data=f"sel_ord_{order_number}"))
    builder.adjust(1)
    await message.answer("Выберите заказ для управления:", reply_markup=builder.as_markup())


@dp.callback_query(F.data == "adm_back_to_list")
async def cb_back_to_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.answer()
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT order_number, status FROM orders")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await callback.message.edit_text("❌ Активных заказов нет.")
        return
    builder = InlineKeyboardBuilder()
    for order_number, status in rows:
        icon = "⏳" if status == "готовится" else "✅"
        builder.add(types.InlineKeyboardButton(text=f"{icon} №{order_number}", callback_data=f"sel_ord_{order_number}"))
    builder.adjust(1)
    await callback.message.edit_text("Выберите заказ для управления:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("sel_ord_"))
async def admin_select_order_menu(callback: types.CallbackQuery):
    order_id = callback.data.split("_")[2] # ИСПРАВЛЕНО
    await callback.answer()
    await callback.message.edit_text(f"Управление заказом №`{order_id}`:", reply_markup=get_status_inline(order_id), parse_mode="Markdown")


@dp.callback_query(F.data.startswith("st_"))
async def admin_confirm_status(callback: types.CallbackQuery):
    data = callback.data.split("_")
    action = data[1] # ИСПРАВЛЕНО
    order_id = data[2] # ИСПРАВЛЕНО
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    if action == "del":
        cursor.execute("DELETE FROM orders WHERE order_number=?", (order_id,))
        conn.commit()
        conn.close()
        await callback.answer("Заказ удален")
        await callback.message.edit_text(f"🗑️ Заказ №`{order_id}` полностью удален из списка активных.", parse_mode="Markdown")
        return
    new_status = "готовится" if action == "prep" else "готово"
    cursor.execute("UPDATE orders SET status=? WHERE order_number=?", (new_status, order_id))
    cursor.execute("SELECT user_id FROM orders WHERE order_number=?", (order_id,))
    user_row = cursor.fetchone()
    conn.commit()
    conn.close()
    await callback.answer("Статус обновлен")
    await callback.message.edit_text(f"✅ Статус заказа №`{order_id}` изменен на *{new_status}*.", parse_mode="Markdown")
    if action == "done" and user_row and user_row[0]:
        try: await bot.send_message(chat_id=int(user_row[0]), text=f"🎉 **Отличные новости!**\nВаш заказ фотографий №`{order_id}` полностью распечатан и готов к отправке!", parse_mode="Markdown")
        except Exception: pass


@dp.message(F.text == "👥 Админы / Чат")
async def open_admin_panel(message: types.Message):
    if not is_admin(message.from_user.id): return
    await message.answer("👥 **Панель управления доступом и рассылкой**\n\nТекущий ID чата для ZIP-архивов: `{get_target_chat()}`\nИспользуйте кнопки ниже для внесения изменений:", reply_markup=get_admin_panel_inline(), parse_mode="Markdown")


# ИСПРАВЛЕНО: Кнопка ОТМЕНЫ теперь работает безупречно на любом шаге!
@dp.callback_query(F.data.startswith("adm_"))
async def handle_admin_settings_callbacks(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    action = callback.data.split("_")[1] # ИСПРАВЛЕНО
    await callback.answer()
    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Ввод отменен. Панель закрыта. Воспользуйтесь меню кнопок снизу.", reply_markup=None)
        return
    if action == "setchat":
        await state.set_state(AdminStates.waiting_for_chat_id)
        await callback.message.edit_text("Введите новый числовой ID чата/группы для ZIP-архивов:", reply_markup=get_cancel_inline())
    elif action == "addnew":
        await state.set_state(AdminStates.waiting_for_new_admin)
        await callback.message.edit_text("Введите Telegram ID пользователя, которого хотите назначить АДМИНИСТРАТОРОМ:", reply_markup=get_cancel_inline())
    elif action == "delold":
        await state.set_state(AdminStates.waiting_for_del_admin)
        await callback.message.edit_text("Введите Telegram ID пользователя, которого хотите УДАЛИТЬ из админов:", reply_markup=get_cancel_inline())


@dp.message(AdminStates.waiting_for_chat_id)
async def admin_save_chat(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    new_id = message.text.strip()
    try:
        update_target_chat(int(new_id))
        await message.answer(f"✅ Чат для отправки архивов успешно изменен на `{new_id}`!", reply_markup=get_admin_kb())
    except Exception: await message.answer("Ошибка. Введите корректный ID.")
    await state.clear()


@dp.message(AdminStates.waiting_for_new_admin)
async def admin_add_process(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    new_adm = message.text.strip()
    if new_adm.isdigit():
        add_admin_db(int(new_adm))
        await message.answer(f"✅ Пользователь `{new_adm}` успешно добавлен в список администраторов!", reply_markup=get_admin_kb(), parse_mode="Markdown")
    else: await message.answer("Ошибка. ID должен состоять только из цифр.")
    await state.clear()


@dp.message(AdminStates.waiting_for_del_admin)
async def admin_del_process(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    old_adm = message.text.strip()
    if old_adm.isdigit():
        if int(old_adm) == SUPER_ADMIN: await message.answer("❌ Вы не можете удалить главного создателя бота из админов!")
        else:
            remove_admin_db(int(old_adm))
            await message.answer(f"❌ Пользователь `{old_adm}` лишен прав администратора.", reply_markup=get_admin_kb(), parse_mode="Markdown")
    else: await message.answer("Ошибка. ID должен состоять только из цифр.")
    await state.clear()


@dp.message(F.text)
async def client_check_any_order(message: types.Message):
    if is_admin(message.from_user.id): return
    text = message.text.strip()
    if not text.isdigit(): return
    conn = sqlite3.connect("wb_shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT status, photo_count FROM orders WHERE order_number=?", (text,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]: await message.answer(f"📦 **Статус №{text}:**\n\nСостояние: *{row[0]}*\nИнформация: {row[1]}", parse_mode="Markdown")
    else: await message.answer("❌ Заказ пока не найден.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
