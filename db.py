from datetime import datetime
import json
from typing import Optional, Dict, Any, Callable

from supabase import Client, create_client

from config import SUPABASE_KEY, SUPABASE_URL
from logger import get_logger

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
logger = get_logger(__name__)


class DBError(RuntimeError):
    """Raised when Supabase operations fail."""


def _execute(action: str, query_callable: Callable[[], Any]):
    """Execute a Supabase query with consistent error logging."""

    try:
        res = query_callable()
        # Supabase python client does not raise for HTTP errors, it exposes "error".
        if getattr(res, "error", None):
            raise DBError(f"{action} failed: {res.error}")
        return res
    except Exception as exc:  # pragma: no cover - defensive for network layer
        logger.error("%s failed: %s", action, exc)
        raise DBError(f"{action} failed") from exc

# ----- Settings -----
def set_setting(key: str, value: str):
    _execute("upsert setting", lambda: supabase.table("settings").upsert({"key": key, "value": value}).execute())

def get_setting(key: str) -> Optional[str]:
    res = _execute("get setting", lambda: supabase.table("settings").select("value").eq("key", key).execute())
    if res.data:
        return res.data[0]["value"]
    return None

# ----- Orders -----
def create_order(
    *,
    user_id: int,
    user_name: str,
    user_username: Optional[str],
    phone: str,
    address: str,
    items: list[Dict[str, Any]],
    total: int,
    status: str = "new",
    user_message_id: Optional[int] = None,
    group_message_id: Optional[int] = None,
) -> int:
    now = datetime.utcnow().isoformat()
    res = _execute(
        "create order",
        lambda: supabase.table("orders").insert({
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
            "updated_at": now
        }).execute(),
    )
    return res.data[0]["id"]

def get_order(order_id: int) -> Optional[Dict[str, Any]]:
    res = _execute("get order", lambda: supabase.table("orders").select("*").eq("id", order_id).execute())
    if not res.data:
        return None
    order = res.data[0]
    order["items"] = json.loads(order["items_json"])
    return order

def get_last_order(user_id: int) -> Optional[Dict[str, Any]]:
    res = _execute(
        "get last order",
        lambda: supabase
        .table("orders")
        .select("*")
        .eq("user_id", user_id)
        .order("id", desc=True)
        .limit(1)
        .execute(),
    )
    if not res.data:
        return None
    order = res.data[0]
    order["items"] = json.loads(order["items_json"])
    return order

def update_status(order_id: int, status: str):
    _execute(
        "update status",
        lambda: supabase
        .table("orders")
        .update({
            "status": status,
            "updated_at": datetime.utcnow().isoformat()
        })
        .eq("id", order_id)
        .execute(),
    )

def set_courier(order_id: int, courier: str):
    _execute(
        "set courier",
        lambda: supabase
        .table("orders")
        .update({
            "courier": courier,
            "updated_at": datetime.utcnow().isoformat()
        })
        .eq("id", order_id)
        .execute(),
    )

def set_group_message_id(order_id: int, group_message_id: int):
    _execute(
        "set group message id",
        lambda: supabase
        .table("orders")
        .update({
            "group_message_id": group_message_id,
            "updated_at": datetime.utcnow().isoformat()
        })
        .eq("id", order_id)
        .execute(),
    )

def set_user_message_id(order_id: int, user_message_id: int):
    _execute(
        "set user message id",
        lambda: supabase
        .table("orders")
        .update({
            "user_message_id": user_message_id,
            "updated_at": datetime.utcnow().isoformat()
        })
        .eq("id", order_id)
        .execute(),
    )

# ----- Clients -----
def save_client(user_id: int, name: str, phone: str, address: str):
    _execute(
        "save client",
        lambda: supabase
        .table("clients")
        .upsert({
            "user_id": user_id,
            "name": name,
            "phone": phone,
            "address": address
        })
        .execute(),
    )

def get_client(user_id: int) -> Optional[Dict[str, Any]]:
    res = _execute("get client", lambda: supabase.table("clients").select("*").eq("user_id", user_id).execute())
    if not res.data:
        return None
    return res.data[0]



