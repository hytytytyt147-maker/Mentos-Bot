import io
import time
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram import BaseMiddleware
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.utils.keyboard import InlineKeyboardBuilder
from barcode import generate
from barcode.writer import ImageWriter

TOKEN = "8947024615:AAHf9RX5nl70knZ3aKy_4WRuhn5f83vHkIs"
ADMIN_ID = 1924047464

bot = Bot(token=TOKEN)
dp = Dispatcher()


def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS orders ("
        "order_number TEXT PRIMARY KEY, "
        "status TEXT DEFAULT 'готовится', "
        "photo_count INTEGER DEFAULT 0, "
        "user_id INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS settings ("
        "key TEXT PRIMARY KEY, value TEXT)"
    )
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) "
        "VALUES ('archive_chat_id', ?)",
        (str(ADMIN_ID),),
    )
    conn.commit()
    conn.close()


init_db()


def get_setting(key):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else str(ADMIN_ID)


def update_setting(key, value):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) "
        "VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()
class AntiSpamMiddleware(BaseMiddleware):

    def __init__(self, limit: int = 2):
        self.limit = limit
        self.storage = {}
        super().__init__()

    async def __call__(self, handler, event: types.Message, data: dict):
        if not event.from_user:
            return await handler(event, data)
        user_id = event.from_user.id
        now = time.time()
        if user_id in self.storage:
            last_time = self.storage[user_id]
            if now - last_time < self.limit:
                if user_id != ADMIN_ID:
                    return await event.answer(
                        "⚠️ Пожалуйста, не спамьте!"
                    )
                return
        self.storage[user_id] = now
        return await handler(event, data)


dp.message.middleware(AntiSpamMiddleware(limit=1))


class OrderStates(StatesGroup):
    waiting_for_order_number = State()
    uploading_photos = State()


class AdminStates(StatesGroup):
    waiting_for_archive_chat = State()
    waiting_for_status_order = State()


def get_admin_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="⚡ Начать сборку"))
    builder.add(types.KeyboardButton(text="📋 Все заказы"))
    builder.add(types.KeyboardButton(text="⚙️ Admin Панель"))
    builder.adjust(1, 2)
    return builder.as_markup(resize_keyboard=True)


def get_admin_panel_inline():
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(
            text="📁 Изменить чат архивов",
            callback_data="admin_change_chat",
        )
    )
    builder.add(
        types.InlineKeyboardButton(
            text="🔄 Изменить статус заказа",
            callback_data="admin_change_status",
        )
    )
    builder.add(
        types.InlineKeyboardButton(
            text="🗑️ Очистить базу заказов",
            callback_data="admin_clear_orders",
        )
    )
    builder.adjust(1)
    return builder.as_markup()


def get_assembly_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="Подтвердить отправку"))
    builder.add(types.KeyboardButton(text="Отменить заказ"))
    builder.adjust(1, 1)
    return builder.as_markup(
        resize_keyboard=True,
        input_field_placeholder="Загрузите фото...",
    )


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            f"Привет, Администратор {message.from_user.first_name}!\n"
            "Вы вошли в систему инвентаризации WB.",
            reply_markup=get_admin_main_keyboard(),
        )
    else:
        await message.answer(
            f"Привет, {message.from_user.first_name}!\n"
            "Это система проверки готовности заказов.\n"
            "Чтобы узнать статус, просто отправьте номер заказа.",
            reply_markup=types.ReplyKeyboardRemove(),
        )


@dp.message(F.text == "📋 Все заказы")
async def show_all_orders_text(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT order_number, status, photo_count FROM orders"
    )
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await message.answer("📭 Список заказов пуст.")
        return
    report = "📊 **Список текущих заказов:**\n\n"
    for row in rows:
        report += (
            f"📦 Заказ №`{row[0]}` | "
            f"Статус: *{row[1]}* | "
            f"Фото: {row[2]} шт.\n"
        )
    await message.answer(report, parse_mode="Markdown")
@dp.message(F.text == "⚙️ Admin Панель")
async def open_admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    current_chat = get_setting("archive_chat_id")
    await message.answer(
        f"⚙️ **Панель настроек**\n\n"
        f"ID отправки архивов: `{current_chat}`",
        reply_markup=get_admin_panel_inline(),
        parse_mode="Markdown",
    )


@dp.callback_query(F.data == "admin_change_chat")
async def admin_change_chat_step1(
    callback: types.CallbackQuery, state: FSMContext
):
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_archive_chat)
    await callback.message.answer("Введите новый ID чата:")


@dp.message(AdminStates.waiting_for_archive_chat)
async def admin_change_chat_step2(
    message: types.Message, state: FSMContext
):
    if message.from_user.id != ADMIN_ID:
        return
    new_chat = message.text.strip()
    update_setting("archive_chat_id", new_chat)
    await state.clear()
    await message.answer(
        f"✅ Чат изменен на: `{new_chat}`",
        parse_mode="Markdown",
        reply_markup=get_admin_main_keyboard(),
    )


@dp.callback_query(F.data == "admin_clear_orders")
async def admin_clear_orders(callback: types.CallbackQuery):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orders")
    conn.commit()
    conn.close()
    await callback.answer("🗑️ Все заказы удалены", show_alert=True)


@dp.callback_query(F.data == "admin_change_status")
async def admin_status_step1(
    callback: types.CallbackQuery, state: FSMContext
):
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_status_order)
    await callback.message.answer("Введите номер заказа:")


@dp.message(AdminStates.waiting_for_status_order)
async def admin_status_step2(
    message: types.Message, state: FSMContext
):
    if message.from_user.id != ADMIN_ID:
        return
    order_id = message.text.strip()
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT order_number FROM orders WHERE order_number = ?",
        (order_id,),
    )
    if not cursor.fetchone():
        await message.answer("❌ Заказ с таким номером не найден.")
        conn.close()
        await state.clear()
        return
    conn.close()
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(
            text="⏳ Готовится",
            callback_data=f"set_stat_prep_{order_id}",
        )
    )
    builder.add(
        types.InlineKeyboardButton(
            text="✅ Готово",
            callback_data=f"set_stat_done_{order_id}",
        )
    )
    builder.adjust(2)
    await state.clear()
    await message.answer(
        f"Выберите статус для №{order_id}:",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("set_stat_"))
async def admin_status_confirm(callback: types.CallbackQuery):
    data = callback.data.split("_")
    status_type = data[2]
    order_id = data[3]
    new_status = (
        "готовится" if status_type == "prep" else "готово"
    )
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE orders SET status = ? WHERE order_number = ?",
        (new_status, order_id),
    )
    conn.commit()
    conn.close()
    await callback.answer(f"Статус изменен на '{new_status}'")
    await callback.message.edit_text(
        f"✅ Статус заказа №`{order_id}` изменен на *{new_status}*.",
        parse_mode="Markdown",
    )


@dp.message(F.text == "⚡ Начать сборку")
async def start_assembly(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(OrderStates.waiting_for_order_number)
    await message.answer(
        "Шаг 1: Введите номер заказа:",
        reply_markup=types.ReplyKeyboardRemove(),
    )


@dp.message(OrderStates.waiting_for_order_number)
async def process_order_number(
    message: types.Message, state: FSMContext
):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.text:
        await message.answer("⚠️ Введите корректный номер заказа:")
        return
    order_number = message.text.strip()
    if not order_number.isdigit():
        await message.answer(
            "❌ Ошибка! Номер должен состоять ТОЛЬКО из цифр:"
        )
        return
    if len(order_number) < 5 or len(order_number) > 25:
        await message.answer("⚠️ Неверный формат! Введите заново:")
        return
    try:
        fp = io.BytesIO()
        generate(
            "code128",
            order_number,
            writer=ImageWriter(),
            output=fp,
            text=order_number,
        )
        fp.seek(0)
        photo = types.BufferedInputFile(
            fp.read(), filename="barcode.png"
        )
        await message.answer_photo(
            photo=photo, caption=f"Штрихкод для заказа №{order_number}."
        )
    except Exception as e:
        await message.answer(f"Ошибка штрихкода: {e}")
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO orders "
        "(order_number, status, photo_count, user_id) "
        "VALUES (?, 'готовится', 0, ?)",
        (order_number, message.from_user.id),
    )
    conn.commit()
    conn.close()
    await state.update_data(order_number=order_number, photos=[])
    await state.set_state(OrderStates.uploading_photos)
    await message.answer(
        f"Заказ №{order_number} открыт. Отправляйте фото товара.",
        reply_markup=get_assembly_keyboard(),
    )


@dp.message(OrderStates.uploading_photos, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    user_data = await state.get_data()
    photos_list = user_data.get("photos", [])
    photos_list.append(message.photo[-1].file_id)
    await state.update_data(photos=photos_list)
    order_number = user_data.get("order_number")
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE orders SET photo_count = ? WHERE order_number = ?",
        (len(photos_list), order_number),
    )
    conn.commit()
    conn.close()
    await message.answer(f"Фото добавлено (всего: {len(photos_list)})")


@dp.message(
    OrderStates.uploading_photos, F.text == "Подтвердить отправку"
)
async def confirm_assembly(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    user_data = await state.get_data()
    order_number = user_data.get("order_number")
    photos_list = user_data.get("photos", [])
    if not photos_list:
        await message.answer("Загрузите хотя бы одно фото товара.")
        return
    archive_target = get_setting("archive_chat_id")
    try:
        await bot.send_message(
            chat_id=archive_target,
            text=f"📦 Архив заказа №{order_number}. "
            f"Фото: {len(photos_list)}",
        )
    except Exception:
        pass
    await message.answer(
        f"✅ Сборка заказа №{order_number} завершена!",
        reply_markup=get_admin_main_keyboard(),
    )
    await state.clear()


@dp.message(OrderStates.uploading_photos, F.text == "Отменить заказ")
async def cancel_assembly(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    user_data = await state.get_data()
    order_number = user_data.get("order_number")
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM orders WHERE order_number = ?",
        (order_number,),
    )
    conn.commit()
    conn.close()
    await message.answer(
        "Сборка отменена. Заказ удален.",
        reply_markup=get_admin_main_keyboard(),
    )
    await state.clear()


@dp.message(F.text)
async def client_check_order(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        return
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите цифровой номер заказа:")
        return
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status, photo_count FROM orders WHERE order_number = ?",
        (text,),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        await message.answer(
            f"📦 **Информация о заказе №{text}:**\n\n"
            f"Статус: *{row[0]}*\n"
            f"Загружено фотографий: {row[1]} шт.",
            parse_mode="Markdown",
        )
    else:
        await message.answer(
            "❌ Заказ с таким номером пока не найден в системе."
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(dp.start_polling(bot))
