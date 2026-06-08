import logging
import asyncio
import json
import os
import http.client
import ssl
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5842806238"))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

users = set()
orders = []

class OrderStates(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    waiting_question = State()

class BroadcastStates(StatesGroup):
    waiting_message = State()

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Zadati vopros")],
            [KeyboardButton(text="Ostavit zayavku")],
            [KeyboardButton(text="Kontakty")],
        ],
        resize_keyboard=True
    )

def ask_gemini(user_message):
    host = "generativelanguage.googleapis.com"
    path = f"/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    data = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": f"Ty pomoshnik kompanii. Otvechay kratko po-russki.\n\nVopros: {user_message}"}]}]
    }).encode()
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(host, timeout=20, context=ctx)
    conn.request("POST", path, data, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    result = json.loads(resp.read())
    return result["candidates"][0]["content"]["parts"][0]["text"]

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    users.add(message.from_user.id)
    await message.answer(
        f"Privet, {message.from_user.first_name}!\n\nYa pomoshnik kompanii.\n\nViberi deystvie ili napishi vopros",
        reply_markup=main_menu()
    )

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Net dostupa.")
    await message.answer(f"Admin:\nPolzovateley: {len(users)}\nZayavok: {len(orders)}\n\n/orders /broadcast")

@dp.message(Command("orders"))
async def cmd_orders(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not orders:
        return await message.answer("Zayavok net.")
    text = "Zayavki:\n\n"
    for i, o in enumerate(orders, 1):
        text += f"{i}. {o['name']} / {o['phone']}\n{o['question']}\n\n"
    await message.answer(text)

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(BroadcastStates.waiting_message)
    await message.answer("Napishi soobshenie:", reply_markup=ReplyKeyboardRemove())

@dp.message(BroadcastStates.waiting_message)
async def do_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    sent = 0
    for user_id in users:
        try:
            await bot.send_message(user_id, message.text)
            sent += 1
        except:
            pass
    await message.answer(f"Otpravleno: {sent}", reply_markup=main_menu())

@dp.message(F.text == "Ostavit zayavku")
@dp.message(Command("order"))
async def start_order(message: types.Message, state: FSMContext):
    await state.set_state(OrderStates.waiting_name)
    await message.answer("Vashe imya:", reply_markup=ReplyKeyboardRemove())

@dp.message(OrderStates.waiting_name)
async def order_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(OrderStates.waiting_phone)
    await message.answer("Vash telefon:")

@dp.message(OrderStates.waiting_phone)
async def order_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(OrderStates.waiting_question)
    await message.answer("Vash vopros:")

@dp.message(OrderStates.waiting_question)
async def order_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    order = {"name": data["name"], "phone": data["phone"], "question": message.text}
    orders.append(order)
    await message.answer("Zayavka prinyata!", reply_markup=main_menu())
    await bot.send_message(ADMIN_ID, f"Novaya zayavka!\n{order['name']}\n{order['phone']}\n{order['question']}")

@dp.message(F.text == "Kontakty")
async def contacts(message: types.Message):
    await message.answer("Telefon: +7 (999) 000-00-00\nEmail: info@company.ru")

@dp.message(F.text == "Zadati vopros")
async def ask_question(message: types.Message):
    await message.answer("Napishi vopros:", reply_markup=ReplyKeyboardRemove())

@dp.message(StateFilter(None))
async def ai_answer(message: types.Message):
    users.add(message.from_user.id)
    if message.text in ["Zadati vopros", "Ostavit zayavku", "Kontakty"]:
        return
    await message.answer("Dumayu...")
    try:
        answer = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, message.text)
    except Exception as e:
        answer = f"Oshibka: {str(e)}"
    await message.answer(answer, reply_markup=main_menu())

async def main():
    print("Bot zapushen!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
