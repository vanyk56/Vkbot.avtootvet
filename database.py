import aiosqlite
import json
import time
from typing import Optional, List, Dict, Any
from config import DB_PATH, DEFAULT_PREFIX

async def init_db():
    """Инициализация базы данных и создание необходимых таблиц."""
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Настройки и переключатели (Key-Value)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # 2. Шаблоны (текстовые и голосовые)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                type TEXT, -- 'text' или 'voice'
                content TEXT
            )
        """)

        # 3. Списки пользователей и бесед (игнор, довы, авлист, белый список бесед)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_type TEXT, -- 'ignore', 'trusted', 'auto_action', 'whitelist_chat'
                target_id INTEGER,
                added_at REAL,
                UNIQUE(list_type, target_id)
            )
        """)

        # 4. Циклические таймеры (цтаймер)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cyclic_timers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                peer_id INTEGER,
                interval_seconds INTEGER,
                text TEXT,
                next_run REAL,
                is_active INTEGER DEFAULT 1
            )
        """)

        # 5. Состояние фермы Ириса
        await db.execute("""
            CREATE TABLE IF NOT EXISTS iris_farm (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                peer_id INTEGER DEFAULT 0,
                is_enabled INTEGER DEFAULT 0,
                last_farm REAL DEFAULT 0,
                last_work REAL DEFAULT 0,
                last_mine REAL DEFAULT 0,
                last_bonus REAL DEFAULT 0,
                last_dig REAL DEFAULT 0
            )
        """)

        # 6. Локальная экономика, браки и премиум
        await db.execute("""
            CREATE TABLE IF NOT EXISTS economy (
                user_id INTEGER PRIMARY KEY,
                fortants INTEGER DEFAULT 100,
                premium_until REAL DEFAULT 0,
                partner_id INTEGER DEFAULT 0
            )
        """)

        await db.commit()

        # Заполнение дефолтных настроек, если их ещё нет
        default_settings = {
            "prefix": DEFAULT_PREFIX,
            "farm": "0",
            "auto_exit": "0",
            "auto_push": "1",
            "push_filter": "all",  # 'all', 'no_bots', 'no_all'
            "auto_unfriend": "0",
            "offline": "1",
            "advd": "1",
            "clean_dogs": "0",
            "auto_reply": "0",
            "auto_reply_text": "Привет! Меня нет на месте, отвечу позже.",
            "notifications": "1",
            "duty": "0",
            "av_count": "5",
            "stop_delete_words": json.dumps(["дд"])
        }

        for k, v in default_settings.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        # Инициализация строки фермы
        await db.execute("INSERT OR IGNORE INTO iris_farm (id, peer_id, is_enabled) VALUES (1, 0, 0)")
        await db.commit()

# --- Вспомогательные функции для настроек ---

async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
        await db.commit()

async def get_bool_setting(key: str, default: bool = False) -> bool:
    val = await get_setting(key, "1" if default else "0")
    return val == "1"

async def set_bool_setting(key: str, value: bool):
    await set_setting(key, "1" if value else "0")

# --- Списки (Игнор, Довы, Авлист, Whitelist) ---

async def add_to_list(list_type: str, target_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_lists (list_type, target_id, added_at) VALUES (?, ?, ?)",
            (list_type, target_id, time.time())
        )
        await db.commit()

async def remove_from_list(list_type: str, target_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM user_lists WHERE list_type = ? AND target_id = ?", (list_type, target_id))
        await db.commit()

async def is_in_list(list_type: str, target_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM user_lists WHERE list_type = ? AND target_id = ?", (list_type, target_id)) as cursor:
            row = await cursor.fetchone()
            return row is not None

async def get_list_items(list_type: str) -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT target_id FROM user_lists WHERE list_type = ?", (list_type,)) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

# --- Шаблоны (Текст и ГС) ---

async def save_template(name: str, template_type: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO templates (name, type, content) VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET type = excluded.type, content = excluded.content",
            (name.lower(), template_type, content)
        )
        await db.commit()

async def delete_template(name: str, template_type: Optional[str] = None) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        if template_type:
            cursor = await db.execute("DELETE FROM templates WHERE name = ? AND type = ?", (name.lower(), template_type))
        else:
            cursor = await db.execute("DELETE FROM templates WHERE name = ?", (name.lower(),))
        await db.commit()
        return cursor.rowcount > 0

async def get_template(name: str, template_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        if template_type:
            query = "SELECT name, type, content FROM templates WHERE name = ? AND type = ?"
            params = (name.lower(), template_type)
        else:
            query = "SELECT name, type, content FROM templates WHERE name = ?"
            params = (name.lower(),)
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"name": row[0], "type": row[1], "content": row[2]}
            return None

async def get_all_templates(template_type: str) -> List[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT name FROM templates WHERE type = ? ORDER BY name ASC", (template_type,)) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

# --- Циклические таймеры (цтаймер) ---

async def add_cyclic_timer(peer_id: int, interval_seconds: int, text: str) -> int:
    next_run = time.time() + interval_seconds
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO cyclic_timers (peer_id, interval_seconds, text, next_run, is_active) VALUES (?, ?, ?, ?, 1)",
            (peer_id, interval_seconds, text, next_run)
        )
        await db.commit()
        return cursor.lastrowid

async def remove_cyclic_timer(timer_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM cyclic_timers WHERE id = ?", (timer_id,))
        await db.commit()
        return cursor.rowcount > 0

async def get_active_cyclic_timers() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, peer_id, interval_seconds, text, next_run FROM cyclic_timers WHERE is_active = 1") as cursor:
            rows = await cursor.fetchall()
            return [
                {"id": r[0], "peer_id": r[1], "interval": r[2], "text": r[3], "next_run": r[4]}
                for r in rows
            ]

async def update_cyclic_timer_next_run(timer_id: int, next_run: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE cyclic_timers SET next_run = ? WHERE id = ?", (next_run, timer_id))
        await db.commit()

# --- Ферма Ириса ---

async def get_iris_farm_state() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT peer_id, is_enabled, last_farm, last_work, last_mine, last_bonus, last_dig FROM iris_farm WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "peer_id": row[0],
                    "is_enabled": bool(row[1]),
                    "last_farm": row[2],
                    "last_work": row[3],
                    "last_mine": row[4],
                    "last_bonus": row[5],
                    "last_dig": row[6],
                }
            return {"peer_id": 0, "is_enabled": False, "last_farm": 0, "last_work": 0, "last_mine": 0, "last_bonus": 0, "last_dig": 0}

async def update_iris_farm_state(peer_id: Optional[int] = None, is_enabled: Optional[bool] = None, **kwargs):
    state = await get_iris_farm_state()
    if peer_id is not None:
        state["peer_id"] = peer_id
    if is_enabled is not None:
        state["is_enabled"] = is_enabled
    for k, v in kwargs.items():
        if k in state:
            state[k] = v

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE iris_farm SET
                peer_id = ?,
                is_enabled = ?,
                last_farm = ?,
                last_work = ?,
                last_mine = ?,
                last_bonus = ?,
                last_dig = ?
            WHERE id = 1
        """, (
            state["peer_id"],
            1 if state["is_enabled"] else 0,
            state["last_farm"],
            state["last_work"],
            state["last_mine"],
            state["last_bonus"],
            state["last_dig"]
        ))
        await db.commit()

# --- Экономика, браки и премиум ---

async def get_user_economy(user_id: int) -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT fortants, premium_until, partner_id FROM economy WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "user_id": user_id,
                    "fortants": row[0],
                    "premium_until": row[1],
                    "is_premium": row[1] > time.time(),
                    "partner_id": row[2]
                }
            return {
                "user_id": user_id,
                "fortants": 100,
                "premium_until": 0,
                "is_premium": False,
                "partner_id": 0
            }

async def set_user_balance(user_id: int, fortants: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO economy (user_id, fortants) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET fortants = excluded.fortants
        """, (user_id, fortants))
        await db.commit()

async def add_user_premium_months(user_id: int, months: int):
    econ = await get_user_economy(user_id)
    current_expiry = econ["premium_until"]
    now = time.time()
    base_time = max(current_expiry, now)
    new_expiry = base_time + (months * 30 * 86400)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO economy (user_id, premium_until) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET premium_until = excluded.premium_until
        """, (user_id, new_expiry))
        await db.commit()
    return new_expiry

async def set_marriage(user1_id: int, user2_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO economy (user_id, partner_id) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET partner_id = excluded.partner_id
        """, (user1_id, user2_id))
        await db.execute("""
            INSERT INTO economy (user_id, partner_id) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET partner_id = excluded.partner_id
        """, (user2_id, user1_id))
        await db.commit()

async def divorce_marriage(user_id: int) -> Optional[int]:
    econ = await get_user_economy(user_id)
    partner_id = econ["partner_id"]
    if partner_id:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE economy SET partner_id = 0 WHERE user_id = ?", (user_id,))
            await db.execute("UPDATE economy SET partner_id = 0 WHERE user_id = ?", (partner_id,))
            await db.commit()
    return partner_id if partner_id != 0 else None
