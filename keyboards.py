from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from data import CATEGORY_TITLES, MENU

# -------- Клиент: старт и категории --------
def start_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Сделать заказ", callback_data="make_order")
    return kb.as_markup()

def categories_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, title in CATEGORY_TITLES.items():
        kb.button(text=title, callback_data=f"cat:{key}")
    kb.button(text="⬅️ Назад", callback_data="back_to_start")
    kb.adjust(1)
    return kb.as_markup()

# -------- Список блюд (1 колонка, 5 на страницу) --------
def list_dishes_kb(category_key: str, page: int, page_size: int = 5) -> InlineKeyboardMarkup:
    dishes_all = MENU.get(category_key, [])
    total_pages = max(1, (len(dishes_all) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))

    start = page * page_size
    dishes = dishes_all[start:start + page_size]

    kb = InlineKeyboardBuilder()
    for d in dishes:
        kb.button(
            text=f"{d['name']} — {d['price']}₽",
            callback_data=f"dish:{category_key}:{d['id']}:{page}"  # нажал — сразу +1 в корзину
        )
    kb.adjust(1)

    kb.row(
        InlineKeyboardButton(text="◀️", callback_data=f"page:{category_key}:{page-1}"),
        InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"),
        InlineKeyboardButton(text="▶️", callback_data=f"page:{category_key}:{page+1}")
    )
    kb.row(
        InlineKeyboardButton(text="🛒 Открыть корзину", callback_data="show_cart"),
        InlineKeyboardButton(text="⬅️ К категориям", callback_data="back_to_categories")
    )
    return kb.as_markup()

# -------- Корзина: только действия (без +/-) --------
def cart_kb(_cart=None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Оформить", callback_data="checkout"),
        InlineKeyboardButton(text="🗑 Очистить", callback_data="clear_cart"),
    )
    kb.row(InlineKeyboardButton(text="⬅️ К категориям", callback_data="back_to_categories"))
    return kb.as_markup()

# --- После доставки/отмены ---
def post_order_kb(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Новый заказ", callback_data="new_order")
    kb.button(text=f"🔁 Повторить заказ", callback_data=f"reorder:{order_id}")
    kb.adjust(1)
    return kb.as_markup()

# -------- Админ-группа --------
_STATUS_TITLES_RU = {
    "new": "Новый",
    "preparing": "Готовят",
    "ready": "Готов",
    "handoff": "Передаём курьеру",
    "onway": "Курьер в пути",
    "delivered": "Доставлен",
    "canceled": "Отменён",
}
_NEXT_BY_STATUS = {
    "new": ["preparing", "canceled"],
    "preparing": ["ready", "canceled"],
    "ready": ["handoff", "canceled"],
    "handoff": ["onway", "canceled"],
    "onway": ["delivered", "canceled"],
    "delivered": [],
    "canceled": [],
}

def admin_order_kb(order_id: int, status: str, has_courier: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in _NEXT_BY_STATUS.get(status, []):
        kb.button(text=_STATUS_TITLES_RU[s], callback_data=f"order:set:{order_id}:{s}")
    if status in ("ready", "handoff", "onway") and not has_courier:
        kb.button(text="🚚 Назначить курьера", callback_data=f"order:setcourier:{order_id}")
    if status not in ("delivered", "canceled"):
        kb.button(text="❌ Отменить", callback_data=f"order:set:{order_id}:canceled")
    kb.button(text="🔁 Обновить", callback_data=f"order:refresh:{order_id}")
    kb.adjust(2)
    return kb.as_markup()
