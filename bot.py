import asyncio
import os
import shutil
import zipfile
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import barcode
from barcode.writer import ImageWriter

TOKEN = "8947024615:AAHf9RX5nl70knZ3aKy_4WRuhn5f83vHkIs"
PROXY_URL = "http://127.0.0.1:10809"
ADMIN_ID = 1924047464  

session = AiohttpSession(proxy=PROXY_URL)
bot = Bot(token=TOKEN, session=session)
dp = Dispatcher()

# Состояния бота для контроля шагов пользователя
class OrderStates(StatesGroup):
    waiting_for_order_number = State()  # Ожидание ввода номера заказа
    uploading_photos = State()          # Ожидание загрузки фотографий

# Клавиатура до ввода заказа
def get_start_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="📥 Начать загрузку"))
    return builder.as_markup(resize_keyboard=True)

# Клавиатура во время загрузки фото
def get_upload_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="✅ Подтвердить отправку"))
    builder.add(types.KeyboardButton(text="❌ Отменить заказ"))
    builder.adjust(1, 1)
    return builder.as_markup(resize_keyboard=True, input_field_placeholder="Загрузите фото...")

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Приветствую, {message.from_user.first_name}!\n\n"
        "Это тестовая система приема фотографий для заказов Wildberries.\n"
        "Нажмите кнопку ниже, чтобы привязать ваш заказ.",
        reply_markup=get_start_keyboard()
    )

@dp.message(F.text == "📥 Начать загрузку")
async def start_order_process(message: types.Message, state: FSMContext):
    await state.set_state(OrderStates.waiting_for_order_number)
    await message.answer(
        "Пожалуйста, введите **номер вашего заказа** Wildberries.\n"
        "(Для теста введите любое число, например: 1234567890)",
        reply_markup=types.ReplyKeyboardRemove() # Убираем кнопку, чтобы человек мог писать текст
    )

# Ловим номер заказа
@dp.message(OrderStates.waiting_for_order_number)
async def process_order_number(message: types.Message, state: FSMContext):
    order_number = message.text.strip()
    
    # Тестовая проверка: номер должен состоять только из цифр
    if not order_number.isdigit():
        await message.answer("⚠️ Неверный формат. Номер заказа должен состоять только из цифр. Попробуйте еще раз:")
        return

    # Сохраняем номер заказа в память бота
    await state.update_data(order_number=order_number)
    await state.set_state(OrderStates.uploading_photos)
    
    await message.answer(
        f"✅ Заказ №`{order_number}` успешно авторизован!\n\n"
        "Теперь вы можете отправить фотографии (альбомом, поодиночке или файлами).\n"
        "Как закончите — обязательно нажмите кнопку **«✅ Подтвердить отправку»**.",
        reply_markup=get_upload_keyboard(),
        parse_mode="Markdown"
    )

# Сброс и отмена
@dp.message(OrderStates.uploading_photos, F.text == "❌ Отменить заказ")
async def cancel_order(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_dir = f"downloads/{user_id}"
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir)
    await state.clear()
    await message.answer("❌ Загрузка отменена. Данные стерты.", reply_markup=get_start_keyboard())

# Кнопка завершения
@dp.message(OrderStates.uploading_photos, F.text == "✅ Подтвердить отправку")
async def cmd_confirm_send(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or "id_user"
    
    # Извлекаем сохраненный номер заказа из памяти
    user_data = await state.get_data()
    order_number = user_data.get("order_number", "unknown")
    
    user_dir = f"downloads/{user_id}"
    # Теперь архив называется именем заказа!
    zip_path = f"downloads/заказ_{order_number}.zip"
    
    if not os.path.exists(user_dir) or not os.listdir(user_dir):
        await message.answer("⚠️ Вы еще не загрузили ни одного фото. Отправьте изображения в чат.")
        return

    processing_msg = await message.answer("⏳ Формируем архив и генерируем стикер штрих-кода...")

    try:
        # ГЕНЕРАЦИЯ ШТРИХ-КОДА ПО НОМЕРУ ЗАКАЗА
        # Используем популярный стандарт Code128 (подходит для большинства сканеров и WB)
        # ГЕНЕРАЦИЯ ШТРИХ-КОДА ПО НОМЕРУ ЗАКАЗА
        code_class = barcode.get_barcode_class('code128')
        generated_code = code_class(order_number, writer=ImageWriter())

        barcode_img_path = f"{user_dir}/штрихкод_{order_number}"
        # Библиотека сама допишет .png в конец, файл сохранится прямо в папку с фото клиента
        generated_code.save(barcode_img_path)

        # Создаем ZIP-архив (куда попадут все фото + сгенерированный штрих-код)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(user_dir):
                for file in files:
                    zipf.write(os.path.join(root, file), file)

        # Отправляем готовый брендированный архив админу
        document = types.FSInputFile(zip_path)
        await bot.send_document(
            chat_id=ADMIN_ID, 
            document=document, 
            caption=f"📦 **ПОСТУПИЛ НОВЫЙ ЗАКАЗ WB**\n\n🔢 Номер заказа: `{order_number}`\n👤 Клиент: @{username}\n🆔 Telegram ID: {user_id}",
            parse_mode="Markdown"
        )
        await processing_msg.delete()
        await message.answer("🎉 Все ваши фотографии успешно упакованы и отправлены в производственный цех!", reply_markup=get_start_keyboard())
        await state.clear() # Полностью очищаем состояние пользователя для нового заказа
        
    except Exception as e:
        await processing_msg.delete()
        await message.answer(f"⚠️ Ошибка на сервере сборки: {e}. Попробуйте нажать кнопку еще раз.")

    # Чистим временные файлы
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir)
    if os.path.exists(zip_path):
        os.remove(zip_path)

# Сохранение фото (срабатывает только внутри активного процесса заказа)
@dp.message(OrderStates.uploading_photos, F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    user_dir = f"downloads/{user_id}"
    os.makedirs(user_dir, exist_ok=True)
    
    for index, photo_size in enumerate(message.photo):
        file_id = photo_size.file_id
        file_name = f"msg_{message.message_id}_size_{index}.jpg"
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, f"{user_dir}/{file_name}")

# Сохранение файлов (фото без сжатия)
@dp.message(OrderStates.uploading_photos, F.document)
async def handle_document(message: types.Message):
    if message.document.mime_type and message.document.mime_type.startswith("image/"):
        user_id = message.from_user.id
        user_dir = f"downloads/{user_id}"
        os.makedirs(user_dir, exist_ok=True)
        
        file_id = message.document.file_id
        file_name = message.document.file_name or f"file_{message.message_id}.jpg"
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, f"{user_dir}/{file_name}")

async def main():
    os.makedirs("downloads", exist_ok=True)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
