from supabase import create_client, Client
from datetime import datetime
import json
from typing import Optional, Dict, Any, List

from config import SUPABASE_URL, SUPABASE_KEY

# Инициализация клиента Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


class DBError(Exception):
    """Общая ошибка работы с базой данных."""
    pass


def _execute(action: str, query_callable):
    """
    Универсальная обёртка для всех запросов к БД.
    Ловит любые исключения и превращает их в DBError с понятным текстом.
    """
    try:
        res = query_callable()
        return res
    except Exception as exc:
        # Здесь можно добавить логирование, если нужно
        # logger.exception("%s failed", action)
        raise DBError(f"{action} failed") from exc


# ----- Settings -----
def set_setting(key: str, value: str) -> None:
    _execute(
        "set setting",
        lambda: supabase
        .table("settings")
        .upsert({"key": key, "value": value})
        .execute()
    )


def get_setting(key: str) -> Optional[str]:
    res = _execute(
        "get setting",
        lambda: supabase
        .table("settings")
        .select("value")
        .eq("key", key)
        .execute()
    )
    if res and res.data:
        return res.data[0].get("value")
    return None


# ----- Orders -----
def create_order(
    *,
    user_id: int,
    user_name: str,
    user_username: Optional[str],
    phone: str,
    address: str,
    items: List[Dict[str, Any]],
    total: int,
    status: str = "new",
    user_message_id: Optional[int] = None,
    group_message_id: Optional[int] = None,
) -> int:
    now = datetime.utcnow().isoformat()

    res = _execute(
        "create order",
        lambda: supabase
        .table("orders")
        .insert(
            {
                "user_id": user_id,
                "user_name": user_name,
                "user_username": user_username,
                "phone": phone,
                "address": address,
                "items_json": json.dumps(items, ensure_ascii=False),
                "total": total,
                "status": status,
                "courier": None,
                "user_message_id": user_message_id,
                "group_message_id": group_message_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        .execute()
    )

    if not res.data:
        raise DBError("create order returned no data")

    return res.data[0]["id"]


def _hydrate_order(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Восстанавливает поле items из items_json.
    """
    order = dict(row)
    items_json = order.get("items_json") or "[]"
    order["items"] = json.loads(items_json)
    return order


def get_order(order_id: int) -> Optional[Dict[str, Any]]:
    res = _execute(
        "get order",
        lambda: supabase
        .table("orders")
        .select("*")
        .eq("id", order_id)
        .execute()
    )
    if not res.data:
        return None
    return _hydrate_order(res.data[0])


def get_last_order(user_id: int) -> Optional[Dict[str, Any]]:
    res = _execute(
        "get last order",
        lambda: supabase
        .table("orders")
        .select("*")
        .eq("user_id", user_id)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return _hydrate_order(res.data[0])


def update_status(order_id: int, status: str) -> None:
    _execute(
        "update status",
        lambda: supabase
        .table("orders")
        .update(
            {
                "status": status,
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
        .eq("id", order_id)
        .execute()
    )


def set_courier(order_id: int, courier: str) -> None:
    _execute(
        "set courier",
        lambda: supabase
        .table("orders")
        .update(
            {
                "courier": courier,
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
        .eq("id", order_id)
        .execute()
    )


def set_group_message_id(order_id: int, group_message_id: int) -> None:
    _execute(
        "set group_message_id",
        lambda: supabase
        .table("orders")
        .update(
            {
                "group_message_id": group_message_id,
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
        .eq("id", order_id)
        .execute()
    )


def set_user_message_id(order_id: int, user_message_id: int) -> None:
    _execute(
        "set user_message_id",
        lambda: supabase
        .table("orders")
        .update(
            {
                "user_message_id": user_message_id,
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
        .eq("id", order_id)
        .execute()
    )


# ----- Clients -----
def save_client(user_id: int, name: str, phone: str, address: str) -> None:
    _execute(
        "save client",
        lambda: supabase
        .table("clients")
        .upsert(
            {
                "user_id": user_id,
                "name": name,
                "phone": phone,
                "address": address,
            }
        )
        .execute()
    )


def get_client(user_id: int) -> Optional[Dict[str, Any]]:
    res = _execute(
        "get client",
        lambda: supabase
        .table("clients")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]
