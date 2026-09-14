import asyncio
import sys
import os
import json
import time
from typing import Optional

from config import VK_TOKEN, DEFAULT_PREFIX, OWNER_ID
import config
from vk_client import VkClient, VkApiError
import database as db

# Импорт модулей команд
from modules.toggles import handle_toggle_command
from modules.farm import get_farm_info_text
from modules.moderation import handle_moderation_command
from modules.automation import handle_automation_command
from modules.templates import handle_templates_command
from modules.info import handle_info_command
from modules.mass import handle_mass_command
from modules.interactive import handle_interactive_command
from modules.economy import handle_economy_command
from modules.background import (
    farm_worker,
    cyclic_timers_worker,
    auto_accept_friends_worker,
    clean_dogs_worker,
    auto_unfriend_worker,
    handle_auto_reply_event,
    handle_auto_push_event,
    handle_auto_exit_event
)

# История последних сообщений владельца для работы удалялки: peer_id -> list of message_ids
OWNER_MESSAGE_HISTORY: dict = {}

async def route_command(
    vk: VkClient,
    peer_id: int,
    message_id: int,
    cmd_name: str,
    args: str,
    owner_id: int,
    msg_timestamp: float,
    raw_event: list
) -> bool:
    """Центральный диспетчер команд селф-бота."""
    cmd_lower = cmd_name.lower()

    # 1. Специфическая команда «ферма инфо»
    if cmd_lower == "ферма" and args.lower().startswith("инфо"):
        info_text = await get_farm_info_text()
        await vk.edit_or_send(peer_id, message_id, info_text)
        return True

    # 2. Модуль переключателей (On/Off) и смены префикса
    if await handle_toggle_command(vk, peer_id, message_id, cmd_lower, args):
        return True

    # 3. Модуль модерации и списков
    if await handle_moderation_command(vk, peer_id, message_id, cmd_lower, args, raw_event):
        return True

    # 4. Модуль автоматизации (ав, авкол, повторялка, удалялка, редач, цтаймер)
    if await handle_automation_command(vk, peer_id, message_id, cmd_lower, args, owner_id):
        return True

    # 5. Модуль текстовых и голосовых шаблонов
    if await handle_templates_command(vk, peer_id, message_id, cmd_lower, args):
        return True

    # 6. Модуль информации, профиля, онлайна, пинга и помощи
    if await handle_info_command(vk, peer_id, message_id, cmd_lower, args, owner_id, msg_timestamp, raw_event):
        return True

    # 7. Модуль массовых действий (прочитать, очистить, влс, мегапуш, пуши)
    if await handle_mass_command(vk, peer_id, message_id, cmd_lower, args, owner_id):
        return True

    # 8. Модуль интерактива (лайки, браки, стикеры)
    if await handle_interactive_command(vk, peer_id, message_id, cmd_lower, args, owner_id, raw_event):
        return True

    # 9. Модуль экономики и премиума
    if await handle_economy_command(vk, peer_id, message_id, cmd_lower, args, owner_id, raw_event):
        return True

    return False

async def main():
    print("=" * 60)
    print("🚀 Запуск VK Селф-бота (Userbot)...")
    print("=" * 60)

    # 1. Проверка токена
    if not VK_TOKEN or "your_token_here" in VK_TOKEN:
        print("\n❌ ОШИБКА: Токен ВКонтакте не указан в файле .env!")
        print("1. Откройте файл .env в папке бота.")
        print("2. Вставьте ваш VK User Access Token в поле VK_TOKEN=")
        print("3. Перезапустите бота.\n")
        return

    # 2. Инициализация базы данных
    await db.init_db()
    print("📁 База данных SQLite успешно инициализирована.")

    # 3. Создание клиента VK
    vk = VkClient(VK_TOKEN)

    # 4. Определение владельца аккаунта с автоповтором при Flood Control
    owner_id = OWNER_ID or 1060180749
    connected = False

    while not connected:
        try:
            user_info = await vk.api_call("users.get")
            if user_info and len(user_info) > 0:
                owner_id = user_info[0]["id"]
                user_name = f"{user_info[0]['first_name']} {user_info[0]['last_name']}"
                print(f"👤 Авторизован как: {user_name} (ID: {owner_id})")
            else:
                print(f"👤 Владелец ID: {owner_id}")
            connected = True
        except Exception as e:
            if "Flood control" in str(e) or "9" in str(e):
                print("⏳ ВКонтакте временно включил защиту Flood Control (защита от частых запросов).")
                print("   Бот не закрывается и повторит попытку через 30 секунд...")
                await asyncio.sleep(30)
            else:
                print(f"⚠️ Ошибка подключения к VK API: {e}. Повтор через 20 секунд...")
                await asyncio.sleep(20)

    current_prefix = await db.get_setting("prefix", DEFAULT_PREFIX)
    print(f"🔧 Текущий префикс команд: {current_prefix}")

    # 5. Запуск фоновых задач
    background_tasks = [
        asyncio.create_task(farm_worker(vk)),
        asyncio.create_task(cyclic_timers_worker(vk)),
        asyncio.create_task(auto_accept_friends_worker(vk)),
        asyncio.create_task(clean_dogs_worker(vk)),
        asyncio.create_task(auto_unfriend_worker(vk))
    ]
    print("⚡ Фоновые модули (Ферма, Цтаймер, Адвд, Собачки, Отписка) запущены.")
    print("👂 Подключение к User LongPoll... Бот готов к работе!\n")

    # 6. Основной цикл LongPoll с авто-восстановлением
    try:
        while True:
            try:
                async for event in vk.longpoll_stream():
                    # Событие 4: Новое сообщение
                    # Формат события: [4, message_id, flags, peer_id, timestamp, text, extra, attachments, random_id]
                    if event[0] != 4:
                        continue

                    message_id = event[1]
                    flags = event[2]
                    peer_id = event[3]
                    timestamp = float(event[4])
                    text = str(event[5]) if len(event) > 5 else ""
                    extra = event[6] if len(event) > 6 and isinstance(event[6], dict) else {}

                    is_outbox = bool(flags & 2)

                    # Определяем отправителя
                    if is_outbox:
                        from_id = owner_id
                        # Сохраняем ID сообщения владельца в историю чата для удалялки
                        if peer_id not in OWNER_MESSAGE_HISTORY:
                            OWNER_MESSAGE_HISTORY[peer_id] = []
                        OWNER_MESSAGE_HISTORY[peer_id].append(message_id)
                        if len(OWNER_MESSAGE_HISTORY[peer_id]) > 30:
                            OWNER_MESSAGE_HISTORY[peer_id].pop(0)
                    else:
                        from_id = int(extra.get("from", peer_id))

                    # Проверка списка игнорируемых
                    if await db.is_in_list("ignore", from_id):
                        try:
                            await vk.delete_msg(message_id)
                        except Exception:
                            pass
                        continue

                    # Обработка автовыхода, автопушей и автоответчика
                    if not is_outbox:
                        await handle_auto_reply_event(vk, peer_id, from_id, owner_id)
                        await handle_auto_push_event(vk, peer_id, message_id, text, from_id, owner_id)
                        await handle_auto_exit_event(vk, peer_id, from_id, owner_id, extra)

                    # Проверка стоп-слова удалялки (для исходящих сообщений владельца)
                    if is_outbox and text.strip():
                        raw_words = await db.get_setting("stop_delete_words", '["дд"]')
                        stop_words = json.loads(raw_words)
                        if text.strip().lower() in [w.lower() for w in stop_words]:
                            # Удаляем текущее сообщение-триггер и последние 2 сообщения владельца
                            to_delete = [message_id]
                            recent = OWNER_MESSAGE_HISTORY.get(peer_id, [])
                            if len(recent) > 1:
                                to_delete.extend(recent[-3:])
                            await vk.delete_msg(list(set(to_delete)))
                            continue

                    # Проверка прав на выполнение команд бота
                    # Команды может вызывать владелец, либо доверенные (довы), если включен режим «дежурный»
                    can_execute = False
                    if is_outbox or from_id == owner_id:
                        can_execute = True
                    else:
                        is_duty = await db.get_bool_setting("duty")
                        if is_duty and await db.is_in_list("trusted", from_id):
                            can_execute = True

                    if not can_execute:
                        continue

                    # Проверка совпадения префикса
                    prefix = await db.get_setting("prefix", DEFAULT_PREFIX)
                    text_stripped = text.strip()

                    if not text_stripped.lower().startswith(prefix.lower()):
                        continue

                    # Отрезаем префикс и получаем команду с аргументами
                    body = text_stripped[len(prefix):].strip()
                    if not body:
                        continue

                    parts = body.split(maxsplit=1)
                    cmd_name = parts[0]
                    cmd_args = parts[1] if len(parts) > 1 else ""

                    # Запуск обработки команды
                    try:
                        await route_command(
                            vk=vk,
                            peer_id=peer_id,
                            message_id=message_id,
                            cmd_name=cmd_name,
                            args=cmd_args,
                            owner_id=owner_id,
                            msg_timestamp=timestamp,
                            raw_event=event
                        )
                    except Exception as e:
                        print(f"⚠️ Ошибка выполнения команды «{cmd_name}»: {e}")
            except Exception as e:
                if "Flood control" in str(e) or "9" in str(e):
                    print("⏳ Временный Flood Control при подключении к LongPoll. Ожидание 30 сек...")
                    await asyncio.sleep(30)
                else:
                    print(f"⚠️ Сбой LongPoll соединения: {e}. Переподключение через 10 сек...")
                    await asyncio.sleep(10)

    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n🛑 Завершение работы бота...")
    finally:
        for t in background_tasks:
            t.cancel()
        await vk.close()
        print("👋 Бот полностью остановлен.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
