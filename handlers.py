import asyncio
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_GROUP_ID, ADMIN_IDS
from data import CATEGORY_TITLES, MENU
from db import (
    DBError,
    create_order,
    get_client,
    get_last_order,
    get_order,
    save_client,
    set_courier,
    set_group_message_id,
    set_user_message_id,
    update_status,
)
from keyboards import (
    admin_order_kb,
    cart_kb,
    categories_kb,
    list_dishes_kb,
    post_order_kb,
    start_kb,
)
from logger import get_logger
from utils import _safe_split, cart_total, format_cart, progress_text
from telegram_utils import safe_edit_message_text

# ----------------- Router -----------------
router = Router()
logger = get_logger(__name__)

# ----------------- Утилиты -----------------
STATUS_ICONS = {
    "new": "🆕", "preparing": "🧑‍🍳", "ready": "✅",
    "handoff": "📦", "onway": "🚚", "delivered": "🏁", "canceled": "❌",
}
STATUS_TITLES_RU = {
    "new": "Заказ принят",
    "preparing": "Ваш заказ готовят",
    "ready": "Ваш заказ готов",
    "handoff": "Передаём курьеру",
    "onway": "Курьер везёт ваш заказ",
    "delivered": "Заказ доставлен",
    "canceled": "Заказ отменён",
}

def _user_order_text(name: str, phone: str, address: str, cart: list, status: str, courier: str | None) -> str:
    items_text = "\n".join(f"• {i['name']} ×{i.get('qty',1)} — {i['price']*i.get('qty',1)}₽" for i in cart)
    total = cart_total(cart)
    courier_line = f"\n<b>Курьер:</b> {courier}" if courier else ""
    return (
        f"✅ <b>Заказ оформлен!</b>\n\n"
        f"<b>Имя:</b> {name}\n"
        f"<b>Телефон:</b> {phone}\n"
        f"<b>Адрес:</b> {address}{courier_line}\n\n"
        f"<b>Ваши блюда:</b>\n{items_text}\n\n"
        f"<b>Итого:</b> {total}₽\n\n"
        f"<b>Статус:</b> {STATUS_TITLES_RU.get(status, status)} {STATUS_ICONS.get(status, '')}\n\n"
        f"{progress_text(status)}"
    )

def _admin_order_text(order) -> str:
    items_text = "\n".join(f"• {i['name']} ×{i.get('qty',1)} — {i['price']*i.get('qty',1)}₽" for i in order['items'])
    user_link = f"<a href='tg://user?id={order['user_id']}'>{order['user_name'] or 'user'}</a>"
    courier_line = f"\n<b>Курьер:</b> {order['courier']}" if order.get("courier") else ""
    return (
        f"{STATUS_ICONS.get(order['status'],'')} <b>Заказ #{order['id']}</b>\n"
        f"{items_text}\n\n"
        f"<b>Сумма:</b> {order['total']}₽\n"
        f"<b>Клиент:</b> {user_link} @{order.get('user_username') or '-'}\n"
        f"<b>Телефон:</b> {order.get('phone')}\n"
        f"<b>Адрес:</b> {order.get('address')}{courier_line}\n"
        f"<b>Статус:</b> {STATUS_TITLES_RU.get(order['status'], order['status'])}"
    )

def is_admin_user(user_id: int) -> bool:
    return True if not ADMIN_IDS else (user_id in ADMIN_IDS)

# ----------------- FSM -----------------
class OrderStates(StatesGroup):
    choosing_category = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_address = State()

class AdminStates(StatesGroup):
    waiting_courier_name = State()

# ----------------- Клиентские команды -----------------
@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(OrderStates.choosing_category)
    await state.update_data(cart=[])
    await message.answer(
        "Привет! Добро пожаловать в наш бот.\nНажмите кнопку ниже, чтобы начать заказ:",
        reply_markup=start_kb()
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 Доступные команды:\n"
        "/menu – открыть меню\n"
        "/cart – показать корзину\n"
        "/status – статус последнего заказа\n"
        "/help – помощь"
    )

@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.set_state(OrderStates.choosing_category)
    await state.update_data(cart=[])
    await message.answer("Выберите категорию:", reply_markup=categories_kb())

@router.message(Command("cart"))
async def cmd_cart(message: Message, state: FSMContext):
    cart = (await state.get_data()).get("cart", [])
    await message.answer(f"🧺 <b>Корзина</b>\n\n{format_cart(cart)}", reply_markup=cart_kb(cart))

@router.message(Command("status"))
async def cmd_status(message: Message):
    order = get_last_order(message.from_user.id)
    if not order:
        await message.answer("У вас ещё нет заказов ❌")
        return
    text = _user_order_text(
        order["user_name"], order["phone"], order["address"],
        order["items"], status=order["status"], courier=order.get("courier")
    )
    await message.answer(text)


# ----------------- Каталог и корзина -----------------
@router.callback_query(F.data == "make_order")
async def make_order(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OrderStates.choosing_category)
    await state.update_data(cart=[])
    await callback.message.edit_text("Выберите категорию:", reply_markup=categories_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("cat:"), OrderStates.choosing_category)
async def show_list(callback: CallbackQuery, state: FSMContext):
    try:
        _, category_key = _safe_split(callback.data, 2)
    except ValueError:
        await callback.answer("Некорректные данные", show_alert=True)
        return

    data = await state.get_data()
    cart = data.get("cart", [])

    qty_sum = sum(i.get("qty", 1) for i in cart)
    total = cart_total(cart)
    cart_lines = (
        "\n".join(
            f"• {i['name']} ×{i.get('qty',1)} — {i['price']*i.get('qty',1)}₽" for i in cart
        )
        if cart
        else "Корзина пуста."
    )
    header = (
        f"Категория: <b>{CATEGORY_TITLES.get(category_key, category_key)}</b>\n"
        f"В корзине: {qty_sum} поз. • {total}₽\n"
        f"<b>Вы выбрали:</b>\n{cart_lines}\n\n"
        f"Выберите блюдо:"
    )

    await callback.message.edit_text(header, reply_markup=list_dishes_kb(category_key, page=0))
    await callback.answer()


@router.callback_query(F.data.startswith("dish:"), OrderStates.choosing_category)
async def add_dish(callback: CallbackQuery, state: FSMContext):
    try:
        _, category_key, dish_id_str, page_str = _safe_split(callback.data, 4)
        dish_id = int(dish_id_str)
    except Exception:
        await callback.answer("Некорректные данные блюда", show_alert=True)
        return

    dish = next((d for d in MENU.get(category_key, []) if d["id"] == dish_id), None)
    if not dish:
        await callback.answer("Блюдо не найдено", show_alert=True)
        return

    data = await state.get_data()
    cart = data.get("cart", [])
    for item in cart:
        if item["name"] == dish["name"]:
            item["qty"] += 1
            break
    else:
        cart.append({"name": dish["name"], "price": dish["price"], "qty": 1})

    await state.update_data(cart=cart)

    qty_sum = sum(i.get("qty", 1) for i in cart)
    total = cart_total(cart)
    cart_lines = "\n".join(
        f"• {i['name']} ×{i.get('qty',1)} — {i['price']*i.get('qty',1)}₽" for i in cart
    )

    header = (
        f"Категория: <b>{CATEGORY_TITLES.get(category_key, category_key)}</b>\n"
        f"В корзине: {qty_sum} поз. • {total}₽\n"
        f"<b>Вы выбрали:</b>\n{cart_lines}\n\n"
        f"Выберите блюдо:"
    )

    page = int(page_str) if page_str.lstrip("-").isdigit() else 0
    await callback.message.edit_text(header, reply_markup=list_dishes_kb(category_key, page=page))
    await callback.answer(f"{dish['name']} добавлено ✅")


@router.callback_query(F.data == "show_cart", OrderStates.choosing_category)
async def show_cart(callback: CallbackQuery, state: FSMContext):
    cart = (await state.get_data()).get("cart", [])
    await callback.message.edit_text(f"🧺 <b>Корзина</b>\n\n{format_cart(cart)}", reply_markup=cart_kb(cart))
    await callback.answer()


@router.callback_query(F.data == "clear_cart", OrderStates.choosing_category)
async def clear_cart(callback: CallbackQuery, state: FSMContext):
    await state.update_data(cart=[])
    await callback.message.edit_text("🧺 Корзина очищена.\n\nВыберите категорию:", reply_markup=categories_kb())
    await callback.answer("Корзина очищена")


@router.callback_query(F.data == "back_to_categories", OrderStates.choosing_category)
async def back_to_categories(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Выберите категорию:", reply_markup=categories_kb())
    await callback.answer()


@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(OrderStates.choosing_category)
    await callback.message.edit_text("Нажмите кнопку ниже, чтобы начать заказ:", reply_markup=start_kb())
    await callback.answer()


# ----------------- Оформление заказа -----------------
@router.callback_query(F.data == "checkout", OrderStates.choosing_category)
async def checkout(callback: CallbackQuery, state: FSMContext):
    cart = (await state.get_data()).get("cart", [])
    if not cart:
        await callback.answer("Корзина пуста ❌", show_alert=True)
        return

    try:
        client = get_client(callback.from_user.id)
    except DBError:
        client = None
        logger.exception("Не удалось загрузить данные клиента")

    if client:
        await state.update_data(
            name=client["name"],
            phone=client["phone"],
            address=client["address"],
        )
        await callback.message.edit_text(
            f"Мы нашли ваши данные:\n"
            f"👤 Имя: {client['name']}\n"
            f"📞 Телефон: {client['phone']}\n"
            f"📍 Адрес: {client['address']}\n\n"
            f"Подтверждаете или хотите ввести заново?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_client")],
                    [InlineKeyboardButton(text="✏ Ввести заново", callback_data="edit_client")],
                ]
            ),
        )
        return

    await callback.message.edit_text("Введите ваше имя:")
    await state.set_state(OrderStates.waiting_for_name)
    await callback.answer()


@router.callback_query(F.data == "confirm_client", OrderStates.choosing_category)
async def confirm_client(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.update_data(address=data.get("address"))
    await enter_address(callback.message, state)


@router.callback_query(F.data == "edit_client", OrderStates.choosing_category)
async def edit_client(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите ваше имя:")
    await state.set_state(OrderStates.waiting_for_name)
    await callback.answer()


@router.message(OrderStates.waiting_for_name)
async def enter_name(message: Message, state: FSMContext):
    if not (message.text or "").strip():
        await message.answer("Имя не может быть пустым. Введите снова:")
        return
    await state.update_data(name=message.text.strip())
    await message.answer("Введите номер телефона (только цифры и +):")
    await state.set_state(OrderStates.waiting_for_phone)


@router.message(OrderStates.waiting_for_phone)
async def enter_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    if not phone or any(ch for ch in phone if not (ch.isdigit() or ch == "+")):
        await message.answer("Телефон должен содержать только цифры и +. Введите снова:")
        return
    await state.update_data(phone=phone)
    await message.answer("Введите адрес доставки:")
    await state.set_state(OrderStates.waiting_for_address)


@router.message(OrderStates.waiting_for_address)
async def enter_address(message: Message, state: FSMContext):
    data = await state.get_data()
    cart = data.get("cart", [])
    name = data.get("name", "")
    phone = data.get("phone", "")
    address = (message.text or "").strip()

    try:
        order_id = create_order(
            user_id=message.from_user.id,
            user_name=message.from_user.full_name,
            user_username=message.from_user.username,
            phone=phone,
            address=address,
            items=cart,
            total=cart_total(cart),
            status="new",
        )
        save_client(message.from_user.id, name, phone, address)
    except DBError:
        logger.exception("Не удалось создать заказ")
        await message.answer("Не удалось оформить заказ. Попробуйте ещё раз позже ❌")
        return

    user_msg = await message.answer(
        _user_order_text(name, phone, address, cart, status="new", courier=None)
    )
    set_user_message_id(order_id, user_msg.message_id)

    if ADMIN_GROUP_ID:
        try:
            admin_msg = await message.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=_admin_order_text(
                    {
                        "id": order_id,
                        "items": cart,
                        "total": cart_total(cart),
                        "user_id": message.from_user.id,
                        "user_username": message.from_user.username,
                        "user_name": message.from_user.full_name,
                        "phone": phone,
                        "address": address,
                        "courier": None,
                        "status": "new",
                    }
                ),
                reply_markup=admin_order_kb(order_id, "new", has_courier=False),
            )
            set_group_message_id(order_id, admin_msg.message_id)
        except Exception:
            logger.exception("Не удалось отправить сообщение в группу %s", ADMIN_GROUP_ID)

    await state.clear()


# ----------------- Повтор заказа -----------------
@router.callback_query(F.data == "new_order")
async def new_order(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(OrderStates.choosing_category)
    await state.update_data(cart=[])
    await callback.message.answer("Выберите категорию:", reply_markup=categories_kb())
    await callback.answer("Новый заказ")


@router.callback_query(F.data.startswith("reorder:"))
async def reorder(callback: CallbackQuery, state: FSMContext):
    try:
        _, order_id_str = _safe_split(callback.data, 2)
        order_id = int(order_id_str)
    except Exception:
        await callback.answer("Некорректный заказ", show_alert=True)
        return

    try:
        order = get_order(order_id)
    except DBError:
        logger.exception("Не удалось загрузить заказ %s", order_id)
        order = None
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    if order["user_id"] != callback.from_user.id:
        await callback.answer("Это не ваш заказ", show_alert=True)
        return

    await state.set_state(OrderStates.choosing_category)
    await state.update_data(cart=order["items"])
    await callback.message.answer(
        f"🔁 Корзина восстановлена из заказа #{order_id}\n\n{format_cart(order['items'])}",
        reply_markup=cart_kb(order["items"]),
    )
    await callback.answer("Корзина восстановлена")


# ----------------- Поиск заказа по номеру -----------------
@router.message(Command("find"))
async def cmd_find(message: Message):
    if not is_admin_user(message.from_user.id):
        await message.answer("Недостаточно прав ❌")
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /find <номер заказа>")
        return

    order_id = int(parts[1])
    try:
        order = get_order(order_id)
    except DBError:
        logger.exception("Не удалось получить заказ %s", order_id)
        order = None
    if not order:
        await message.answer("Заказ не найден ❌")
        return

    await message.answer(
        _admin_order_text(order),
        reply_markup=admin_order_kb(order_id, order["status"], has_courier=bool(order.get("courier"))),
    )


# ----------------- Админская часть -----------------
@router.callback_query(F.data.startswith("order:"), F.message.chat.type.in_({"group", "supergroup"}))
async def admin_actions(callback: CallbackQuery, state: FSMContext):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    try:
        _, action, *rest = _safe_split(callback.data, 3)
    except ValueError:
        await callback.answer("Некорректные данные", show_alert=True)
        return

    if action == "set":
        try:
            order_id = int(rest[0]); new_status = rest[1]
        except Exception:
            await callback.answer("Некорректные данные заказа", show_alert=True)
            return

        try:
            order = get_order(order_id)
        except DBError:
            logger.exception("Не удалось загрузить заказ %s", order_id)
            order = None
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        try:
            update_status(order_id, new_status)
            order = get_order(order_id)
        except DBError:
            logger.exception("Не удалось обновить статус заказа %s", order_id)
            await callback.answer("Ошибка обновления статуса", show_alert=True)
            return

        exc_text = await safe_edit_message_text(
            callback.message.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=_admin_order_text(order),
            reply_markup=admin_order_kb(order_id, order["status"], has_courier=bool(order.get("courier"))),
            order_id=order_id,
            context="admin",
        )
        if exc_text:
            if "message is not modified" in exc_text:
                logger.info("Сообщение администратора не изменилось для заказа %s", order_id)
            elif "message to edit not found" in exc_text:
                logger.warning("Админское сообщение не найдено, отправляем новое для заказа %s", order_id)
                await callback.message.answer(
                    _admin_order_text(order),
                    reply_markup=admin_order_kb(order_id, order["status"], has_courier=bool(order.get("courier"))),
                )

        user_markup = post_order_kb(order_id) if order["status"] in ("delivered", "canceled") else None
        user_text = _user_order_text(
            order["user_name"],
            order["phone"],
            order["address"],
            order["items"],
            status=order["status"],
            courier=order.get("courier"),
        )

        user_message_id = order.get("user_message_id")
        if user_message_id:
            try:
                await callback.bot.edit_message_text(
                    chat_id=order["user_id"],
                    message_id=user_message_id,
                    text=user_text,
                    reply_markup=user_markup,
                )
            except TelegramBadRequest as e:
                logger.warning(
                    "Не удалось обновить сообщение клиента для заказа %s: %s",
                    order_id,
                    e,
                )
                return
        else:
            logger.warning("Для заказа %s нет user_message_id. Отправляем новое сообщение.", order_id)
            try:
                new_msg = await callback.bot.send_message(
                    chat_id=order["user_id"],
                    text=user_text,
                    reply_markup=user_markup,
                )
                set_user_message_id(order_id, new_msg.message_id)
            except Exception:
                logger.exception("Не удалось отправить новое сообщение клиенту для заказа %s", order_id)

        try:
            if order["status"] == "delivered":
                await callback.bot.send_message(
                    chat_id=order["user_id"],
                    text="🙏 Спасибо за заказ! Мы очень ценим ваше доверие ❤️",
                    reply_markup=post_order_kb(order_id),
                )
            elif order["status"] == "canceled":
                await callback.bot.send_message(
                    chat_id=order["user_id"],
                    text="❌ Ваш заказ был отменён. Но вы всегда можете оформить новый заказ 🛒",
                    reply_markup=post_order_kb(order_id),
                )
            else:
                await callback.bot.send_message(
                    chat_id=order["user_id"],
                    text=f"{STATUS_TITLES_RU.get(order['status'], order['status'])} {STATUS_ICONS.get(order['status'],'')}",
                )
        except Exception:
            logger.exception("Не удалось отправить уведомление клиенту для заказа %s", order_id)

        await callback.answer("Статус обновлён")
        return

    if action == "setcourier":
        try:
            order_id = int(rest[0])
        except Exception:
            await callback.answer("Некорректные данные заказа", show_alert=True)
            return
        await state.update_data(order_id_for_courier=order_id)
        await state.set_state(AdminStates.waiting_courier_name)
        await callback.answer()
        await callback.message.reply("Введите имя/позывной курьера одним сообщением:")

    if action == "refresh":
        try:
            order_id = int(rest[0])
            order = get_order(order_id)
        except Exception:
            await callback.answer("Ошибка при обновлении", show_alert=True)
            return
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        exc_text = await safe_edit_message_text(
            callback.message.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=_admin_order_text(order),
            reply_markup=admin_order_kb(order_id, order["status"], has_courier=bool(order.get("courier"))),
            order_id=order_id,
            context="admin",
        )
        if exc_text:
            if "message is not modified" in exc_text:
                logger.info("Сообщение администратора без изменений для заказа %s", order_id)
            elif "message to edit not found" in exc_text:
                logger.warning("Админское сообщение не найдено при refresh, отправляем новое для заказа %s", order_id)
                await callback.message.answer(
                    _admin_order_text(order),
                    reply_markup=admin_order_kb(order_id, order["status"], has_courier=bool(order.get("courier"))),
                )
        await callback.answer("Обновлено")

@router.message(AdminStates.waiting_courier_name, F.chat.type.in_({"group", "supergroup"}))
async def set_courier_name(message: Message, state: FSMContext):
    if not is_admin_user(message.from_user.id):
        await message.reply("Недостаточно прав"); return

    data = await state.get_data()
    order_id = data.get("order_id_for_courier")
    if not order_id:
        await message.reply("Не найден контекст заказа."); return

    courier = (message.text or "").strip()
    if not courier:
        await message.reply("Имя курьера не может быть пустым. Повторите:"); return

    try:
        set_courier(order_id, courier)
        order = get_order(order_id)
    except DBError:
        logger.exception("Не удалось назначить курьера для заказа %s", order_id)
        await message.reply("Ошибка сохранения курьера. Попробуйте ещё раз")
        return

    await safe_edit_message_text(
        message.bot,
        chat_id=message.chat.id,
        message_id=order["group_message_id"],
        text=_admin_order_text(order),
        reply_markup=admin_order_kb(order_id, order["status"], has_courier=True),
        order_id=order_id,
        context="admin",
    )

    await safe_edit_message_text(
        message.bot,
        chat_id=order["user_id"],
        message_id=order["user_message_id"],
        text=_user_order_text(
            order["user_name"], order["phone"], order["address"],
            order["items"], status=order["status"], courier=order.get("courier")
        ),
        order_id=order_id,
        context="client",
    )
    await message.bot.send_message(order["user_id"], f"Назначен курьер: {courier} 🚚")

    await state.clear()
    await message.reply(f"Курьер назначен: {courier}")
