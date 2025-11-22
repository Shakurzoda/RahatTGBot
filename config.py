from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Не найден BOT_TOKEN в .env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Нужно указать SUPABASE_URL и SUPABASE_KEY в .env")

_admin_group_env = os.getenv("ADMIN_GROUP_ID", "").strip()
ADMIN_GROUP_ID = int(_admin_group_env) if _admin_group_env.lstrip("-").isdigit() else None

_admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = {
    int(x) for x in _admin_ids_str.split(",")
    if x.strip().lstrip("+").isdigit()
}
