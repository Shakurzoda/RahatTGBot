# Architecture and Structure

- The bot is wired in `main.py` with a single `Dispatcher` that uses in-memory FSM storage. All conversational logic, business rules, and admin flows are concentrated in `handlers.py`, while persistence is in `db.py` and static menu data is in `data.py`. There is no package layout or layering (e.g., services vs. handlers), so Telegram handlers perform database writes, formatting, and state transitions directly.

# Critical Issues

1. **Conflicting duplicated handlers** – `handlers.py` defines duplicate callbacks/commands (e.g., two `show_list`, `add_dish`, `checkout`, and `cmd_find` handlers) with overlapping filters. The later definitions override registration order and may lead to unexpected behavior or unhandled edits, especially because the first `add_dish` mutates quantities while the second blindly appends items. This makes ordering brittle and risks inconsistent cart totals for users. 【F:handlers.py†L159-L214】【F:handlers.py†L327-L400】
2. **Corrupted/unused state definitions** – `states.py` is truncated (no newline, missing state ordering) and unused, while a separate `OrderStates` inside `handlers.py` drives the FSM. `fsm_states.py` defines another state machine but is also unused. The dead/invalid modules make the project harder to reason about and suggest missing tests. 【F:states.py†L1-L6】【F:fsm_states.py†L1-L6】【F:handlers.py†L103-L112】
3. **Volatile FSM storage** – `MemoryStorage` is used in production, so all user sessions and carts vanish on process restart or redeploy, potentially losing active orders and leading to confused customers. 【F:main.py†L11-L27】
4. **Weak admin protection** – `is_admin_user` grants admin rights to everyone when `ADMIN_IDS` is empty, which is the default when the env var is unset. In production this can expose order management controls to any group member. 【F:handlers.py†L100-L102】【F:config.py†L18-L22】
5. **Silent failures around Supabase** – All DB calls are synchronous and unguarded; network errors will raise and kill the update flow, while some admin/user edits catch `Exception` and ignore errors, hiding data loss (e.g., courier assignment or status updates). There are no timeouts, retries, or logging around persistence. 【F:db.py†L8-L105】【F:handlers.py†L461-L522】【F:handlers.py†L558-L582】
6. **Input validation gaps** – Phone, address, and menu choices are accepted verbatim without normalization or checks, making it easy to store garbage data or trigger downstream errors. The first `add_dish` path validates item IDs while the duplicated one does not, allowing crafted callback data to raise. 【F:handlers.py†L415-L438】【F:handlers.py†L335-L347】
7. **Hard-coded menu/config** – Menu data is hard-coded in `data.py`; prices and IDs must be redeployed to change. Secrets and URLs are read at import time and raise `ValueError`, making it impossible to run with partial config or fallbacks. 【F:data.py†L1-L25】【F:config.py†L6-L22】
8. **Logging/monitoring gaps** – Only basic root logging is configured; DB operations, state transitions, and error paths are silent or `print`. There is no structured logging, alerting, or metrics, making production incidents hard to debug. 【F:main.py†L11-L27】【F:handlers.py†L461-L522】

# Code Smells & Anti-patterns

- **Tight coupling of transport and domain** – Telegram handlers assemble texts, mutate carts, and hit Supabase directly instead of calling a service layer; this prevents reuse and unit testing. 【F:handlers.py†L415-L465】【F:db.py†L20-L90】
- **Missing abstraction for menu/catalog** – Menu pagination and pricing are baked into handlers/keyboards; adding dynamic catalogs or discounts would require touching multiple modules. 【F:handlers.py†L159-L214】【F:keyboards.py†L19-L45】
- **Repeated status flow logic** – Status mappings and progress text are scattered and manually assembled; mismatches between admin keyboard transitions and user progress text are likely. 【F:handlers.py†L40-L69】【F:keyboards.py†L66-L95】
- **Broad exception swallowing** – Several blocks `except Exception: pass`, hiding delivery failures to customers or admins. 【F:handlers.py†L461-L522】【F:handlers.py†L571-L582】

# Improvement Plan

## Architecture & Separation of Concerns

- Introduce a `services/` layer (e.g., `services/orders.py`) that encapsulates cart math, validation, and Supabase access behind async functions. Handlers would only orchestrate FSM transitions and call services, making it testable.
- Split handlers by domain (`handlers/customer.py`, `handlers/admin.py`, `handlers/catalog.py`) and register routers from `main.py` to reduce cross-interference and ease ownership.
- Replace `MemoryStorage` with Redis storage (`aiogram.fsm.storage.redis.RedisStorage`) for durability and horizontal scaling. 【F:main.py†L11-L27】

## Robust Persistence & Error Handling

- Wrap Supabase client calls with timeouts, retries, and structured logging. Example wrapper:
  ```python
  import async_timeout
  import logging

  async def safe_upsert(table, payload, *, attempts=3):
      for attempt in range(1, attempts + 1):
          try:
              async with async_timeout.timeout(5):
                  return await table.upsert(payload)
          except Exception as exc:
              logging.exception("Supabase upsert failed (attempt %s)", attempt)
              if attempt == attempts:
                  raise
              await asyncio.sleep(0.5 * attempt)
  ```
  Adapt `create_order`, `update_status`, and courier updates to use such helpers and surface failures to admins. 【F:db.py†L20-L90】
- Replace bare `except Exception: pass` with targeted exceptions and user/admin notifications when delivery updates fail so orders are not silently desynchronized. 【F:handlers.py†L461-L522】【F:handlers.py†L571-L582】

## Configuration & Security

- Make `ADMIN_IDS` mandatory or default-deny when unset to prevent open admin access; validate environment at startup with clear log messages instead of crashing on import. 【F:handlers.py†L100-L102】【F:config.py†L6-L22】
- Load secrets via a dedicated `settings.py` using `pydantic`/`pydantic-settings` to support type-checked env parsing, defaults, and per-environment config. Avoid performing work at import time so tests can stub settings.

## Input Validation & Safety

- Normalize and validate user inputs (phone regex, non-empty address) and guard callback payloads with schema checks to prevent crafting invalid `dish:` data. 【F:handlers.py†L335-L347】【F:handlers.py†L415-L438】
- Store carts with product IDs and pull product data from a catalog service to avoid trusting callback data for prices.

## Reliability Features

- Persist carts/orders in DB across restarts; consider background tasks for order timeouts or SLA monitoring.
- Add structured logging (JSON) per request/user and Sentry-style error reporting. Instrument metrics (orders created, failures, DB latency) for monitoring.
- Implement graceful degradation: if Supabase is unavailable, inform users and queue requests, or fall back to an in-memory queue for admin notification.

## Testing & Observability

- Add unit tests for cart math, status transitions, and admin permissions, and integration tests with a Supabase test instance or mocks.
- Create load tests for menu browsing and order creation to catch performance bottlenecks in keyboard generation and DB access.

# Quick Wins

- Remove duplicated handlers and consolidate cart manipulation paths to a single source of truth with quantity updates.
- Fix or remove corrupted `states.py`/`fsm_states.py`; keep one FSM definition and type-annotate state data payloads.
- Add explicit logging around admin status changes and user notifications to detect delivery drift early.
