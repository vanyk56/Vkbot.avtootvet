import asyncio
from typing import Optional, List, Dict, Any
from vk_client import VkClient
import database as db

async def handle_mass_command(
    vk: VkClient,
    peer_id: int,
    message_id: int,
    command: str,
    args: str,
    owner_id: int
) -> bool:
    """Обработчик массовых действий: прочитать, очистить, влс, мегапуш, пуши."""
    cmd = command.lower()

    # 1. Прочитать диалоги: прочитать [все / чаты / группы / беседы]
    if cmd == "прочитать":
        category = args.strip().lower() or "все"
        await vk.edit_or_send(peer_id, message_id, f"⏳ Отмечаю диалоги ({category}) как прочитанные...")
        try:
            convs = await vk.api_call("messages.getConversations", count=100, filter="unread")
            items = convs.get("items", []) if isinstance(convs, dict) else []
            count_read = 0

            for it in items:
                p_id = it["conversation"]["peer"]["id"]
                p_type = it["conversation"]["peer"]["type"]

                if category in ("все", "всё"):
                    pass
                elif category in ("чаты", "лс", "люди") and p_type != "user":
                    continue
                elif category in ("группы", "паблики") and p_type != "group":
                    continue
                elif category in ("беседы", "конфы") and p_type != "chat":
                    continue

                try:
                    await vk.api_call("messages.markAsRead", peer_id=p_id)
                    count_read += 1
                    await asyncio.sleep(0.1)
                except Exception:
                    pass

            await vk.edit_or_send(peer_id, message_id, f"✅ Успешно прочитано диалогов: **{count_read}**")
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Ошибка при чтении диалогов: {e}")
        return True

    # 2. Очистить диалоги: очистить [все / чаты / группы / беседы]
    if cmd == "очистить":
        category = args.strip().lower()
        if not category:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите категорию: `нб очистить [все / чаты / группы / беседы]`")
            return True

        await vk.edit_or_send(peer_id, message_id, f"⏳ Начинаю очистку ({category})...")
        try:
            convs = await vk.api_call("messages.getConversations", count=50)
            items = convs.get("items", []) if isinstance(convs, dict) else []
            deleted_count = 0

            for it in items:
                p_id = it["conversation"]["peer"]["id"]
                p_type = it["conversation"]["peer"]["type"]

                if category in ("все", "всё"):
                    pass
                elif category in ("чаты", "лс") and p_type != "user":
                    continue
                elif category in ("группы",) and p_type != "group":
                    continue
                elif category in ("беседы",) and p_type != "chat":
                    continue

                try:
                    await vk.api_call("messages.deleteConversation", peer_id=p_id)
                    deleted_count += 1
                    await asyncio.sleep(0.35)
                except Exception:
                    pass

            await vk.edit_or_send(peer_id, message_id, f"✅ Успешно очищено диалогов: **{deleted_count}**")
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Ошибка очистки: {e}")
        return True

    # 3. Рассылка по ЛС: влс [текст]
    if cmd == "влс":
        if not args.strip():
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите текст для рассылки: `нб влс [текст]`")
            return True
        broadcast_text = args.strip()
        await vk.edit_or_send(peer_id, message_id, "⏳ Начинаю рассылку по личным диалогам...")

        try:
            convs = await vk.api_call("messages.getConversations", count=40)
            items = convs.get("items", []) if isinstance(convs, dict) else []
            sent_count = 0

            for it in items:
                p_id = it["conversation"]["peer"]["id"]
                p_type = it["conversation"]["peer"]["type"]
                if p_type == "user" and p_id > 0 and p_id != owner_id:
                    try:
                        await vk.send_msg(p_id, broadcast_text)
                        sent_count += 1
                        await asyncio.sleep(0.8)  # Задержка для предотвращения капчи
                    except Exception:
                        pass

            await vk.edit_or_send(peer_id, message_id, f"✅ Сообщение успешно отправлено в **{sent_count}** ЛС!")
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Ошибка рассылки: {e}")
        return True

    # 4. Мегапуш: мегапуш
    if cmd == "мегапуш":
        if peer_id <= 2000000000:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Команда мегапуш работает только в беседах!")
            return True

        econ = await db.get_user_economy(owner_id)
        if not econ["is_premium"]:
            await vk.edit_or_send(peer_id, message_id, "⭐ Команда «мегапуш» доступна только с Премиум-подпиской!\nАктивация: `нб +премиум 1` (50 фортантов)")
            return True

        try:
            members = await vk.api_call("messages.getConversationMembers", peer_id=peer_id)
            profiles = members.get("profiles", [])
            # Исключаем собачек и себя
            valid_ids = [p["id"] for p in profiles if not p.get("deactivated") and p["id"] != owner_id]

            if not valid_ids:
                await vk.edit_or_send(peer_id, message_id, "⚠️ Нет доступных участников для упоминания.")
                return True

            await vk.delete_msg(message_id)

            # Разбиваем на группы по 25 упоминаний (лимит ВК для надежного пуша)
            chunk_size = 25
            for i in range(0, len(valid_ids), chunk_size):
                chunk = valid_ids[i:i + chunk_size]
                # Невидимый символ для бесшумного тега
                mentions = " ".join([f"[id{uid}|ᅠ]" for uid in chunk])
                push_text = f"📢 **Общий сбор беседы!**\n{mentions}"
                await vk.send_msg(peer_id, push_text)
                await asyncio.sleep(0.5)

        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Ошибка мегапуша: {e}")
        return True

    # 5. Фильтрация пушей: пуши [боты / алл / все]
    if cmd == "пуши":
        mode = args.strip().lower().replace("-", "")
        if mode in ("боты", "no_bots"):
            await db.set_setting("push_filter", "no_bots")
            await vk.edit_or_send(peer_id, message_id, "🔔 Фильтр пушей: игнорировать пуши от ботов (Ирис и др.).")
        elif mode in ("алл", "all", "no_all"):
            await db.set_setting("push_filter", "no_all")
            await vk.edit_or_send(peer_id, message_id, "🔔 Фильтр пушей: не реагировать на @all и @online.")
        elif mode in ("все", "всё", "all_pushes"):
            await db.set_setting("push_filter", "all")
            await vk.edit_or_send(peer_id, message_id, "🔔 Фильтр пушей: собирать и читать абсолютно все упоминания.")
        else:
            cur = await db.get_setting("push_filter", "all")
            await vk.edit_or_send(peer_id, message_id, f"🔔 Текущий режим пушей: **{cur}**\nВарианты настройки: `нб пуши боты`, `нб пуши алл`, `нб пуши все`")
        return True

    return False
