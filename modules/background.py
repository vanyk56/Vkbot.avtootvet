import asyncio
import time
from typing import Dict, Set
from vk_client import VkClient
from modules.farm import run_farm_cycle_step
import database as db

# Память для предотвращения спама автоответчика (user_id -> timestamp последнего ответа)
AUTO_REPLY_CACHE: Dict[int, float] = {}

async def farm_worker(vk: VkClient):
    """Фоновый воркер для проверки и сбора наград фермы Ириса."""
    while True:
        try:
            await run_farm_cycle_step(vk)
        except Exception:
            pass
        await asyncio.sleep(25.0)

async def cyclic_timers_worker(vk: VkClient):
    """Фоновый воркер для выполнения циклических таймеров (цтаймер)."""
    while True:
        try:
            now = time.time()
            timers = await db.get_active_cyclic_timers()
            for t in timers:
                if now >= t["next_run"]:
                    try:
                        await vk.send_msg(t["peer_id"], t["text"])
                    except Exception:
                        pass
                    # Обновляем время следующего запуска
                    new_next = now + t["interval"]
                    await db.update_cyclic_timer_next_run(t["id"], new_next)
                    await asyncio.sleep(0.5)
        except Exception:
            pass
        await asyncio.sleep(3.0)

async def auto_accept_friends_worker(vk: VkClient):
    """Фоновый воркер для автоматического принятия заявок в друзья (Адвд)."""
    while True:
        try:
            is_on = await db.get_bool_setting("advd")
            if is_on:
                res = await vk.api_call("friends.getRequests", count=20, need_mutual=0)
                items = res.get("items", []) if isinstance(res, dict) else []
                for user_id in items:
                    try:
                        await vk.api_call("friends.add", user_id=user_id)
                        await asyncio.sleep(1.0)
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(180.0)  # Проверка каждые 3 минуты

async def clean_dogs_worker(vk: VkClient):
    """Фоновый воркер для чистки списка друзей от заблокированных аккаунтов (собачек)."""
    while True:
        try:
            is_on = await db.get_bool_setting("clean_dogs")
            if is_on:
                friends = await vk.api_call("friends.get", fields="deactivated")
                items = friends.get("items", []) if isinstance(friends, dict) else []
                for f in items:
                    if f.get("deactivated"):
                        try:
                            await vk.api_call("friends.delete", user_id=f["id"])
                            await asyncio.sleep(1.5)
                        except Exception:
                            pass
        except Exception:
            pass
        await asyncio.sleep(1800.0)  # Проверка каждые 30 минут

async def auto_unfriend_worker(vk: VkClient):
    """Фоновый воркер для удаления неактивных пользователей (не заходивших более 90 дней)."""
    while True:
        try:
            is_on = await db.get_bool_setting("auto_unfriend")
            if is_on:
                friends = await vk.api_call("friends.get", fields="last_seen,deactivated")
                items = friends.get("items", []) if isinstance(friends, dict) else []
                now = time.time()
                three_months = 90 * 86400

                for f in items:
                    if f.get("deactivated"):
                        await vk.api_call("friends.delete", user_id=f["id"])
                        await asyncio.sleep(1.5)
                        continue

                    last_seen = f.get("last_seen", {}).get("time", 0)
                    if last_seen and (now - last_seen) > three_months:
                        try:
                            await vk.api_call("friends.delete", user_id=f["id"])
                            await asyncio.sleep(1.5)
                        except Exception:
                            pass
        except Exception:
            pass
        await asyncio.sleep(3600.0 * 2)  # Проверка раз в 2 часа

# --- Обработчики входящих событий LongPoll ---

async def handle_auto_reply_event(vk: VkClient, peer_id: int, from_id: int, owner_id: int):
    """Ответ автоответчика в личные сообщения."""
    # Только ЛС от других пользователей
    if peer_id <= 0 or peer_id >= 2000000000 or from_id == owner_id:
        return

    is_on = await db.get_bool_setting("auto_reply")
    if not is_on:
        return

    now = time.time()
    # Отвечаем одному человеку не чаще чем раз в 15 минут
    if from_id in AUTO_REPLY_CACHE and (now - AUTO_REPLY_CACHE[from_id]) < 900:
        return

    reply_text = await db.get_setting("auto_reply_text", "Привет! Меня нет на месте, отвечу позже.")
    try:
        await vk.send_msg(peer_id, reply_text)
        AUTO_REPLY_CACHE[from_id] = now
    except Exception:
        pass

async def handle_auto_push_event(vk: VkClient, peer_id: int, message_id: int, text: str, from_id: int, owner_id: int):
    """Автоматическое прочтение упоминаний."""
    is_on = await db.get_bool_setting("auto_push")
    if not is_on:
        return

    # Проверяем фильтр пушей
    push_filter = await db.get_setting("push_filter", "all")
    if push_filter == "no_bots" and from_id < 0:
        return
    if push_filter == "no_all" and ("@all" in text or "@online" in text):
        return

    # Проверяем, упомянут ли пользователь
    user_tag = f"[id{owner_id}|"
    if "@all" in text or "@online" in text or user_tag in text or f"id{owner_id}" in text:
        try:
            await vk.api_call("messages.markAsRead", peer_id=peer_id, start_message_id=message_id)
        except Exception:
            pass

async def handle_auto_exit_event(vk: VkClient, peer_id: int, from_id: int, owner_id: int, extra: dict):
    """Автоматический выход из бесед при добавлении."""
    if peer_id <= 2000000000:
        return

    is_on = await db.get_bool_setting("auto_exit")
    if not is_on:
        return

    # Проверка белого списка бесед
    if await db.is_in_list("whitelist_chat", peer_id):
        return

    # Проверяем, если действие - добавление бота в беседу
    source_act = extra.get("source_act")
    source_mid = extra.get("source_mid")

    if source_act == "chat_invite_user" and str(source_mid) == str(owner_id):
        chat_id = peer_id - 2000000000
        try:
            await vk.api_call("messages.removeChatUser", chat_id=chat_id, member_id=owner_id)
        except Exception:
            pass
