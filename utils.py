from __future__ import annotations

from typing import Iterable, List, Mapping


def cart_total(cart: Iterable[Mapping[str, int]]) -> int:
    return sum(item["price"] * item.get("qty", 1) for item in cart)


def format_cart(cart: List[Mapping[str, int | str]]) -> str:
    if not cart:
        return "Корзина пуста."
    lines = [
        f"• {i['name']} ×{i.get('qty',1)} — {i['price']*i.get('qty',1)}₽" for i in cart
    ]
    total = cart_total(cart)
    lines.append(f"\nИтого: <b>{total}₽</b>")
    return "\n".join(lines)


STATUS_FLOW = ["new", "preparing", "ready", "handoff", "onway", "delivered", "canceled"]


def progress_text(current: str) -> str:
    steps = [
        ("preparing", "🧑‍🍳 Готовим"),
        ("ready", "✅ Готов"),
        ("handoff", "📦 Передаём курьеру"),
        ("onway", "🚚 В пути"),
        ("delivered", "🏁 Доставлен"),
    ]
    cur_idx = STATUS_FLOW.index(current) if current in STATUS_FLOW else 0
    lines = []
    for status, title in steps:
        idx = STATUS_FLOW.index(status)
        mark = "✅" if idx <= cur_idx and current != "canceled" else ("⏳" if current != "canceled" else "—")
        lines.append(f"• {title} — {mark}")
    return "\n".join(lines)


def _safe_split(data: str, expected: int) -> list[str]:
    parts = data.split(":")
    if len(parts) < expected:
        raise ValueError("Not enough parts in callback data")
    return parts
