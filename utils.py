from typing import List, Dict, Any


def _safe_split(data: str, parts: int, sep: str = ":") -> List[str]:
    """
    Безопасно разбивает строку вида "prefix:arg1:arg2"
    и проверяет, что частей ровно `parts`.
    Иначе кидает ValueError.
    """
    if not isinstance(data, str):
        raise ValueError("data must be string")

    chunks = data.split(sep)
    if len(chunks) != parts:
        raise ValueError(f"Expected {parts} parts, got {len(chunks)} in '{data}'")
    return chunks


def cart_total(cart: List[Dict[str, Any]]) -> int:
    """
    Считает общую сумму корзины:
    сумма (price * qty) по всем позициям.
    """
    total = 0
    for item in cart or []:
        price = int(item.get("price", 0) or 0)
        qty = int(item.get("qty", 1) or 1)
        total += price * qty
    return total


def format_cart(cart: List[Dict[str, Any]]) -> str:
    """
    Красивое текстовое представление корзины для пользователя.
    """
    if not cart:
        return "Корзина пуста."

    lines = []
    total = 0
    for item in cart:
        name = item.get("name", "—")
        price = int(item.get("price", 0) or 0)
        qty = int(item.get("qty", 1) or 1)
        line_sum = price * qty
        total += line_sum
        lines.append(f"• {name} ×{qty} — {line_sum}₽")

    lines.append(f"\n<b>Итого:</b> {total}₽")
    return "\n".join(lines)


def progress_text(status: str) -> str:
    """
    Текстовый индикатор прогресса заказа по статусу.
    Просто делает понятное сообщение, без магии.
    """
    status = (status or "").lower()

    if status == "new":
        return "🆕 Ваш заказ принят и скоро будет передан на кухню."
    if status == "preparing":
        return "🧑‍🍳 Ваш заказ сейчас готовится."
    if status == "ready":
        return "✅ Заказ готов и скоро будет передан курьеру."
    if status == "handoff":
        return "📦 Передаём заказ курьеру."
    if status == "onway":
        return "🚚 Курьер уже в пути к вам."
    if status == "delivered":
        return "🏁 Заказ доставлен. Приятного аппетита! 😋"
    if status == "canceled":
        return "❌ Заказ отменён. Если это ошибка — напишите нам."

    # На всякий случай для неизвестных статусов
    return "Статус заказа обновлён."
