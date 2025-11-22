import pytest

from utils import _safe_split, cart_total, format_cart, progress_text


def test_cart_total_counts_quantities():
    cart = [{"price": 100, "qty": 2}, {"price": 50, "qty": 1}]
    assert cart_total(cart) == 250


def test_format_cart_empty_and_total():
    assert format_cart([]) == "Корзина пуста."

    cart = [{"name": "Плов", "price": 200, "qty": 2}]
    text = format_cart(cart)
    assert "Плов" in text and "400₽" in text and "Итого" in text


@pytest.mark.parametrize(
    "status,expected_line",
    [
        ("preparing", "🧑‍🍳 Готовим"),
        ("delivered", "🏁 Доставлен"),
    ],
)
def test_progress_text_contains_steps(status, expected_line):
    text = progress_text(status)
    assert expected_line in text


def test_safe_split_validates_length():
    with pytest.raises(ValueError):
        _safe_split("too:short", 3)

