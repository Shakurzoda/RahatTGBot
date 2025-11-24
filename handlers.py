import asyncio
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramForbiddenError  # <--- добавили

from config import ADMIN_GROUP_ID, ADMIN_IDS
from data import CATEGORY_TITLES, MENU
from db import (
    DBError,
    create_order,
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


def order_status_legend() -> str:
    """
    Текст с этапами заказа, чтобы клиент понимал, что означает каждый статус.
    """
    return (
        "Этапы заказа:\n"
        "• 👨‍🍳 Готовим — ⏳\n"
        "• ✅ Готов — ⏳\n"
        "• 📦 Передаём курьеру — ⏳\n"
        "• 🚚 В пути — ⏳\n"
        "• 🏁 Доставлен — ⏳"
    )


def _user_order_text(
    name: str,
    phone: str,
    address: str,
    cart: list,
    status: str,
    courier: str | None,
    comment_text: str | None = None,
    comment_topic: str | None = None,
) -> str:
    items_text = "\n".join(
        f"• {i['name']} ×{i.get('qty', 1)} — {i['price'] * i.get('qty', 1)}₽"
        for i in cart
    )
    total = cart_total(cart)
    courier_line = f"\n<b>Курьер:</b> {courier}" if courier else ""

    comment_line = ""
    if comment_text:
        topic_label = "заказу"
        if comment_topic == "food":
            topic_label = "еде"
        elif comment_topic == "delivery":
            topic_label = "доставке"
        comment_line = f"\n<b>Комментарий к {topic_label}:</b> {comment_text}"

    return (
        f"✅ <b>Заказ оформлен!</b>\n\n"
        f"<b>Имя:</b> {name}\n"
        f"<b>Телефон:</b> {phone}\n"
        f"<b>Адрес:</b> {address}{courier_line}{comment_line}\n\n"
        f"<b>Ваши блюда:</b>\n{items_text}\n\n"
        f"<b>Итого:</b> {total}₽\n\n"
        f"<b>Статус:</b> {STATUS_TITLES_RU.get(status, status)} {STATUS_ICONS.get(status, '')}\n\n"
        f"{progress_text(status)}"
    )


def _admin_order_text(order) -> str:
    items_text = "\n".join(
        f"• {i['name']} ×{i.get('qty', 1)} — {i['price'] * i.get('qty', 1)}₽"
        for i in order["items"]
    )
    user_link = f"<a href='tg://user?id={order['user_id']}'>{order['user_name'] or 'user'}</a>"
    courier_line = f"\n<b>Курьер:</b> {order['courier']}" if order.get("courier") else ""

    comment = order.get("comment")
    comment_topic = order.get("comment_topic")
    comment_line = ""
    if comment:
        topic_label = "заказу"
        if comment_topic == "food":
            topic_label = "еде"
        elif comment_topic == "delivery":
            topic_label = "доставке"
        comment_line = f"\n<b>Комментарий клиента к {topic_label}:</b> {comment}"

    return (
        f"{STATUS_ICONS.get(order['status'], '')} <b>Заказ #{order['id']}</b>\n"
        f"{items_text}\n\n"
        f"<b>Сумма:</b> {order['total']}₽\n"
        f"<b>Клиент:</b> {user_link} @{order.get('user_username') or '-'}\n"
        f"<b>Телефон:</b> {order.get('phone')}\n"
        f"<b>Адрес:</b> {order.get('address')}{courier_line}{comment_line}\n"
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
    waiting_for_comment_choice = State()
    waiting_for_comment_text = State()


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
        reply_markup=start_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 Доступные команды:\n"
        "/menu – открыть меню\n"
        "/cart – показать корзину\n"
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
    await message.answer(
        f"🧺 <b>Корзина</b>\n\n{format_cart(cart)}", reply_markup=cart_kb(cart)
    )


# ----------------- Каталог и корзина -----------------
@router.callback_query(F.data == "make_order")
async def make_order(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OrderStates.choosing_category)
    await state.update_data(cart=[])
    await callback.message.edit_text(
        "Выберите категорию:", reply_markup=categories_kb()
    )
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
            f"• {i['name']} ×{i.get('qty', 1)} — {i['price'] * i.get('qty', 1)}₽"
            for i in cart
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

    await callback.message.edit_text(
        header, reply_markup=list_dishes_kb(category_key, page=0)
    )
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
        f"• {i['name']} ×{i.get('qty', 1)} — {i['price'] * i.get('qty', 1)}₽"
        for i in cart
    )

    header = (
        f"Категория: <b>{CATEGORY_TITLES.get(category_key, category_key)}</b>\n"
        f"В корзине: {qty_sum} поз. • {total}₽\n"
        f"<b>Вы выбрали:</b>\n{cart_lines}\n\n"
        f"Выберите блюдо:"
    )

    page = int(page_str) if page_str.lstrip("-").isdigit() else 0
    await callback.message.edit_text(
        header, reply_markup=list_dishes_kb(category_key, page=page)
    )
    await callback.answer(f"{dish['name']} добавлено ✅")


@router.callback_query(F.data == "show_cart", OrderStates.choosing_category)
async def show_cart(callback: CallbackQuery, state: FSMContext):
    cart = (await state.get_data()).get("cart", [])
    await callback.message.edit_text(
        f"🧺 <b>Корзина</b>\n\n{format_cart(cart)}", reply_markup=cart_kb(cart)
    )
    await callback.answer()


@router.callback_query(F.data == "clear_cart", OrderStates.choosing_category)
async def clear_cart(callback: CallbackQuery, state: FSMContext):
    await state.update_data(cart=[])
    await callback.message.edit_text(
        "🧺 Корзина очищена.\n\nВыберите категорию:", reply_markup=categories_kb()
    )
    await callback.answer("Корзина очищена")


@router.callback_query(F.data == "back_to_categories", OrderStates.choosing_category)
async def back_to_categories(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Выберите категорию:", reply_markup=categories_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(OrderStates.choosing_category)
    await callback.message.edit_text(
        "Нажмите кнопку ниже, чтобы начать заказ:", reply_markup=start_kb()
    )
    await callback.answer()


# ----------------- Оформление заказа -----------------
@router.callback_query(F.data == "checkout", OrderStates.choosing_category)
async def checkout(callback: CallbackQuery, state: FSMContext):
    """
    Упрощённый чек-аут:
    - не подгружаем клиента из БД,
    - всегда заново спрашиваем имя/телефон/адрес.
    """
    cart = (await state.get_data()).get("cart", [])
    if not cart:
        await callback.answer("Корзина пуста ❌", show_alert=True)
        return

    await callback.message.edit_text("Введите ваше имя:")
    await state.set_state(OrderStates.waiting_for_name)
    await callback.answer()


@router.message(OrderStates.waiting_for_name)
async def enter_name(message: Message, state: FSMContext):
    if not (message.text or "").strip():
        await message.answer("Имя не может быть пустым. Введите снова:")
        return
    await state.update_data(name=message.text.strip())
    await message.answer(
        "Введите номер телефона.\n\n"
        "Примеры:\n"
        "+992 900 00 00 00\n"
        "+7 900 000-00-00\n"
        "900000000"
    )
    await state.set_state(OrderStates.waiting_for_phone)


@router.message(OrderStates.waiting_for_phone)
async def enter_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    if not phone:
        await message.answer(
            "Пожалуйста, введите номер телефона.\n\n"
            "Примеры:\n"
            "+992 900 00 00 00\n"
            "+7 900 000-00-00\n"
            "900000000"
        )
        return

    # НЕ проверяем формат, просто сохраняем как есть
    await state.update_data(phone=phone)

    await message.answer("Введите адрес доставки:")
    await state.set_state(OrderStates.waiting_for_address)


@router.message(OrderStates.waiting_for_address)
async def enter_address(message: Message, state: FSMContext):
    address = (message.text or "").strip()
    if not address:
        await message.answer("Адрес не может быть пустым. Введите снова:")
        return

    await state.update_data(address=address)

    # После адреса спрашиваем про комментарий
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🍽 Комментарий к еде", callback_data="comment:food"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚚 Комментарий к доставке",
                    callback_data="comment:delivery",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Без комментария",
                    callback_data="comment:skip",
                )
            ],
        ]
    )

    await message.answer(
        "Хотите оставить комментарий к заказу?",
        reply_markup=kb,
    )
    await state.set_state(OrderStates.waiting_for_comment_choice)


@router.callback_query(F.data.startswith("comment:"), OrderStates.waiting_for_comment_choice)
async def comment_choice(callback: CallbackQuery, state: FSMContext):
    try:
        _, topic = _safe_split(callback.data, 2)
    except Exception:
        await callback.answer("Некорректные данные", show_alert=True)
        return

    if topic == "skip":
        # Без комментария — оформляем заказ сразу
        await callback.answer("Оформляем заказ без комментария")
        await finalize_order(callback.message, state)
        return

    # Сохраняем тему комментария и просим текст
    await state.update_data(comment_topic=topic)
    if topic == "food":
        prompt = "Напишите комментарий по еде (вкус, температура, подача и т.п.):"
    else:
        prompt = "Напишите комментарий по доставке (скорость, вежливость и т.п.):"

    await callback.message.answer(prompt)
    await state.set_state(OrderStates.waiting_for_comment_text)
    await callback.answer()


@router.message(OrderStates.waiting_for_comment_text)
async def comment_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Комментарий не может быть пустым. Напишите хотя бы пару слов 🙂")
        return

    await state.update_data(comment_text=text)
    await finalize_order(message, state)


async def finalize_order(message: Message, state: FSMContext):
    """
    Общий финальный шаг:
    - берём имя, телефон, адрес, корзину, комментарий (если есть),
    - создаём заказ,
    - отправляем сообщения клиенту и в админ-группу.
    """
    data = await state.get_data()
    cart = data.get("cart", [])
    name = data.get("name", "")
    phone = data.get("phone", "")
    address = data.get("address", "")

    comment_topic = data.get("comment_topic")
    comment_text = data.get("comment_text")

    if not cart:
        await message.answer("Корзина пуста ❌")
        await state.clear()
        return

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
        # технично мы всё ещё сохраняем клиента в БД,
        # но не используем эту "память" в диалогах
        save_client(message.from_user.id, name, phone, address)
    except DBError:
        logger.exception("Не удалось создать заказ")
        await message.answer(
            "Не удалось оформить заказ. Попробуйте ещё раз позже ❌"
        )
        await state.clear()
        return

    # Сообщение для клиента
    user_msg = await message.answer(
        _user_order_text(
            name,
            phone,
            address,
            cart,
            status="new",
            courier=None,
            comment_text=comment_text,
            comment_topic=comment_topic,
        )
    )
    set_user_message_id(order_id, user_msg.message_id)

    # Подсказка по этапам заказа
    try:
        await message.answer(order_status_legend())
    except Exception:
        logger.warning("Не удалось отправить легенду статусов для заказа %s", order_id)

    # Сообщение в админскую группу
    if ADMIN_GROUP_ID:
        try:
            admin_payload = {
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
            if comment_text:
                admin_payload["comment"] = comment_text
                admin_payload["comment_topic"] = comment_topic

            admin_msg = await message.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=_admin_order_text(admin_payload),
                reply_markup=admin_order_kb(
                    order_id, "new", has_courier=False
                ),
            )
            set_group_message_id(order_id, admin_msg.message_id)
        except Exception:
            logger.exception(
                "Не удалось отправить сообщение в группу %s", ADMIN_GROUP_ID
            )

    await state.clear()


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
        reply_markup=admin_order_kb(
            order_id, order["status"], has_courier=bool(order.get("courier"))
        ),
    )


# ----------------- Админская часть -----------------
@router.callback_query(
    F.data.startswith("order:"), F.message.chat.type.in_({"group", "supergroup"})
)
async def admin_actions(callback: CallbackQuery, state: FSMContext):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = callback.data or ""
    parts = data.split(":")

    # ожидаемые варианты:
    # order:set:<order_id>:<status>
    # order:setcourier:<order_id>
    # order:refresh:<order_id>
    if len(parts) < 3 or parts[0] != "order":
        await callback.answer("Некорректные данные кнопки", show_alert=True)
        return

    action = parts[1]

    # ------ изменение статуса ------
    if action == "set":
        if len(parts) < 4:
            await callback.answer("Некорректные данные заказа", show_alert=True)
            return

        try:
            order_id = int(parts[2])
            new_status = parts[3]
        except Exception:
            await callback.answer("Некорректные данные заказа", show_alert=True)
            return

        try:
            order = get_order(order_id)
        except DBError:
            logger.exception("Не удалось загрузить заказ %s", order_id)
            await callback.answer("Ошибка загрузки заказа", show_alert=True)
            return

        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        # обновляем статус в БД
        try:
            update_status(order_id, new_status)
            order = get_order(order_id)
        except DBError:
            logger.exception("Не удалось обновить статус заказа %s", order_id)
            await callback.answer("Ошибка обновления статуса", show_alert=True)
            return

        # обновляем сообщение в админ-группе
        try:
            await callback.message.edit_text(
                _admin_order_text(order),
                reply_markup=admin_order_kb(
                    order_id,
                    order["status"],
                    has_courier=bool(order.get("courier")),
                ),
            )
        except Exception:
            logger.exception(
                "Не удалось обновить сообщение в админ-группе для заказа %s", order_id
            )

        # --------- ОТПРАВКА СООБЩЕНИЯ КЛИЕНТУ ---------
        user_markup = (
            post_order_kb(order_id)
            if order["status"] in ("delivered", "canceled")
            else None
        )

        user_text = _user_order_text(
            order["user_name"],
            order["phone"],
            order["address"],
            order["items"],
            status=order["status"],
            courier=order.get("courier"),
        )

        try:
            msg = await callback.bot.send_message(
                chat_id=order["user_id"],
                text=user_text,
                reply_markup=user_markup,
            )
            # по желанию обновляем последний user_message_id
            try:
                set_user_message_id(order_id, msg.message_id)
            except Exception:
                pass

        except TelegramForbiddenError as e:
            if "bots can't send messages to bots" in str(e):
                logger.info(
                    "Клиент %s является ботом, Telegram не разрешает отправлять ему сообщения",
                    order["user_id"],
                )
            else:
                logger.warning(
                    "Не удалось отправить сообщение клиенту для заказа %s: %s",
                    order_id,
                    e,
                )
        except Exception as e:
            logger.warning(
                "Не удалось отправить сообщение клиенту для заказа %s: %s",
                order_id,
                e,
            )

        await callback.answer("Статус обновлён")
        return

    # ------ назначение курьера ------
    if action == "setcourier":
        try:
            order_id = int(parts[2])
        except Exception:
            await callback.answer("Некорректные данные заказа", show_alert=True)
            return

        await state.update_data(order_id_for_courier=order_id)
        await state.set_state(AdminStates.waiting_courier_name)
        await callback.answer()
        await callback.message.reply(
            "Введите имя/позывной курьера одним сообщением:"
        )
        return

    # ------ принудительное обновление карточки ------
    if action == "refresh":
        try:
            order_id = int(parts[2])
        except Exception:
            await callback.answer("Некорректные данные заказа", show_alert=True)
            return

        try:
            order = get_order(order_id)
        except DBError:
            logger.exception("Не удалось загрузить заказ %s при refresh", order_id)
            await callback.answer("Ошибка загрузки заказа", show_alert=True)
            return

        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        try:
            await callback.message.edit_text(
                _admin_order_text(order),
                reply_markup=admin_order_kb(
                    order_id,
                    order["status"],
                    has_courier=bool(order.get("courier")),
                ),
            )
        except Exception:
            logger.exception(
                "Не удалось обновить карточку заказа %s при refresh", order_id
            )
            await callback.answer("Ошибка обновления сообщения", show_alert=True)
            return

        await callback.answer("Обновлено")
        return

    # если попало что-то непонятное
    await callback.answer("Некорректные данные кнопки", show_alert=True)


@router.message(
    AdminStates.waiting_courier_name, F.chat.type.in_({"group", "supergroup"})
)
async def set_courier_name(message: Message, state: FSMContext):
    if not is_admin_user(message.from_user.id):
        await message.reply("Недостаточно прав")
        return

    data = await state.get_data()
    order_id = data.get("order_id_for_courier")
    if not order_id:
        await message.reply("Не найден контекст заказа.")
        return

    courier = (message.text or "").strip()
    if not courier:
        await message.reply("Имя курьера не может быть пустым. Повторите:")
        return

    try:
        set_courier(order_id, courier)
        order = get_order(order_id)
    except DBError:
        logger.exception("Не удалось назначить курьера для заказа %s", order_id)
        await message.reply("Ошибка сохранения курьера. Попробуйте ещё раз")
        return

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=order["group_message_id"],
            text=_admin_order_text(order),
            reply_markup=admin_order_kb(
                order_id, order["status"], has_courier=True
            ),
        )
    except Exception:
        pass

    try:
        await message.bot.edit_message_text(
            chat_id=order["user_id"],
            message_id=order["user_message_id"],
            text=_user_order_text(
                order["user_name"],
                order["phone"],
                order["address"],
                order["items"],
                status=order["status"],
                courier=order.get("courier"),
            ),
        )
        await message.bot.send_message(
            order["user_id"], f"Назначен курьер: {courier} 🚚"
        )
    except Exception:
        pass

    await state.clear()
    await message.reply(f"Курьер назначен: {courier}")
