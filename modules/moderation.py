from typing import Optional, List, Dict, Any
from vk_client import VkClient, VkApiError
import database as db

async def extract_target_user(
    vk: VkClient,
    peer_id: int,
    message_id: int,
    args: str,
    raw_event: Optional[list] = None
) -> Optional[int]:
    """Извлекает ID целевого пользователя: из ответа на сообщение (reply) или из аргументов."""
    # 1. Сначала пробуем взять из текста аргументов (ссылка, [id123|Имя], id123)
    if args and args.strip():
        first_token = args.strip().split()[0]
        user_id = await vk.resolve_target(first_token)
        if user_id:
            return user_id

    # 2. Если аргументов нет или не распознались, запрашиваем информацию о текущем сообщении (проверка на reply_message или fwd_messages)
    try:
        res = await vk.api_call("messages.getById", message_ids=message_id)
        items = res.get("items", [])
        if items:
            msg = items[0]
            if "reply_message" in msg and msg["reply_message"]:
                return msg["reply_message"]["from_id"]
            if "fwd_messages" in msg and msg["fwd_messages"]:
                return msg["fwd_messages"][0]["from_id"]
    except Exception:
        pass

    return None

async def handle_moderation_command(
    vk: VkClient,
    peer_id: int,
    message_id: int,
    command: str,
    args: str,
    raw_event: Optional[list] = None
) -> bool:
    """Обработчик команд модерации и управления пользователями."""
    cmd = command.lower()

    # --- Списки без обязательной цели ---
    if cmd == "игнлист":
        ignored_ids = await db.get_list_items("ignore")
        if not ignored_ids:
            await vk.edit_or_send(peer_id, message_id, "📋 Список игнорируемых пользователей пуст.")
            return True
        try:
            users = await vk.api_call("users.get", user_ids=",".join(map(str, ignored_ids)))
            names = [f"• [id{u['id']}|{u['first_name']} {u['last_name']}]" for u in users]
            await vk.edit_or_send(peer_id, message_id, "📋 **Список игнорируемых:**\n" + "\n".join(names))
        except Exception:
            ids_str = "\n".join([f"• id{uid}" for uid in ignored_ids])
            await vk.edit_or_send(peer_id, message_id, f"📋 **Список игнорируемых:**\n{ids_str}")
        return True

    if cmd == "довы":
        trusted_ids = await db.get_list_items("trusted")
        if not trusted_ids:
            await vk.edit_or_send(peer_id, message_id, "🛡️ Список доверенных пользователей пуст.")
            return True
        try:
            users = await vk.api_call("users.get", user_ids=",".join(map(str, trusted_ids)))
            names = [f"• [id{u['id']}|{u['first_name']} {u['last_name']}]" for u in users]
            await vk.edit_or_send(peer_id, message_id, "🛡️ **Список доверенных (довы):**\n" + "\n".join(names))
        except Exception:
            ids_str = "\n".join([f"• id{uid}" for uid in trusted_ids])
            await vk.edit_or_send(peer_id, message_id, f"🛡️ **Список доверенных (довы):**\n{ids_str}")
        return True

    if cmd in ("чсы", "чслист"):
        try:
            banned = await vk.api_call("account.getBanned", count=50)
            items = banned.get("items", []) if isinstance(banned, dict) else []
            profiles = banned.get("profiles", []) if isinstance(banned, dict) else []
            if not items and not profiles:
                await vk.edit_or_send(peer_id, message_id, "🚫 Черный список пуст.")
                return True
            if profiles:
                names = [f"• [id{p['id']}|{p['first_name']} {p['last_name']}]" for p in profiles]
            else:
                names = [f"• id{item}" for item in items]
            await vk.edit_or_send(peer_id, message_id, "🚫 **Пользователи в Черном Списке:**\n" + "\n".join(names[:30]))
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Ошибка получения ЧС: {e}")
        return True

    # --- Команды с указанием цели (ссылка или реплай) ---
    target_id = await extract_target_user(vk, peer_id, message_id, args, raw_event)

    # Вернуть в беседу
    if cmd == "вернуть":
        if peer_id <= 2000000000:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Команда работает только в беседах!")
            return True
        if not target_id:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите пользователя (ссылку или ответьте на его сообщение).")
            return True
        chat_id = peer_id - 2000000000
        try:
            await vk.api_call("messages.addChatUser", chat_id=chat_id, user_id=target_id)
            await vk.edit_or_send(peer_id, message_id, f"✅ Пользователь [id{target_id}|вернyт] в беседу.")
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Не удалось вернуть пользователя: {e}")
        return True

    # Кикнуть из беседы
    if cmd == "кик":
        if peer_id <= 2000000000:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Команда работает только в беседах!")
            return True
        if not target_id:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите пользователя (ссылку или ответьте на его сообщение).")
            return True
        chat_id = peer_id - 2000000000
        try:
            await vk.api_call("messages.removeChatUser", chat_id=chat_id, member_id=target_id)
            await vk.edit_or_send(peer_id, message_id, f"👢 Пользователь [id{target_id}|исключен] из беседы.")
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Не удалось исключить пользователя: {e}")
        return True

    # Админка: +админ / -админ
    if cmd in ("+админ", "-админ"):
        if peer_id <= 2000000000:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Команда работает только в беседах!")
            return True
        if not target_id:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите пользователя для назначения/снятия прав админа.")
            return True
        role = "admin" if cmd == "+админ" else "member"
        role_name = "администратором 👑" if cmd == "+админ" else "обычным участником"
        try:
            await vk.api_call("messages.setMemberRole", peer_id=peer_id, member_id=target_id, role=role)
            await vk.edit_or_send(peer_id, message_id, f"✅ Пользователь [id{target_id}|назначен] {role_name}.")
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Ошибка изменения роли: {e}")
        return True

    # Игнор: +игн / -игн
    if cmd in ("+игн", "-игн"):
        if not target_id:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите пользователя для добавления/удаления из игнора.")
            return True
        if cmd == "+игн":
            await db.add_to_list("ignore", target_id)
            await vk.edit_or_send(peer_id, message_id, f"🔇 Пользователь [id{target_id}|добавлен] в локальный игнор-лист.")
        else:
            await db.remove_from_list("ignore", target_id)
            await vk.edit_or_send(peer_id, message_id, f"🔊 Пользователь [id{target_id}|удален] из игнор-листа.")
        return True

    # ЧС VK: +чс / -чс
    if cmd in ("+чс", "-чс"):
        if not target_id:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите пользователя для ЧС.")
            return True
        try:
            if cmd == "+чс":
                await vk.api_call("account.ban", owner_id=target_id)
                await vk.edit_or_send(peer_id, message_id, f"🚫 Пользователь [id{target_id}|заблокирован] (добавлен в ЧС ВКонтакте).")
            else:
                await vk.api_call("account.unban", owner_id=target_id)
                await vk.edit_or_send(peer_id, message_id, f"🔓 Пользователь [id{target_id}|разблокирован] (удален из ЧС ВКонтакте).")
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Ошибка ЧС: {e}")
        return True

    # Доверенные: +дов / -дов
    if cmd in ("+дов", "-дов"):
        if not target_id:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите пользователя для добавления в доверенные.")
            return True
        if cmd == "+дов":
            await db.add_to_list("trusted", target_id)
            await vk.edit_or_send(peer_id, message_id, f"🛡️ Пользователь [id{target_id}|добавлен] в список Доверенных (может вызывать команды в режиме дежурного).")
        else:
            await db.remove_from_list("trusted", target_id)
            await vk.edit_or_send(peer_id, message_id, f"🛡️ Пользователь [id{target_id}|удален] из списка Доверенных.")
        return True

    # Друзья: +др / -др
    if cmd in ("+др", "-др"):
        if not target_id:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите пользователя для добавления/удаления из друзей.")
            return True
        try:
            if cmd == "+др":
                await vk.api_call("friends.add", user_id=target_id)
                await vk.edit_or_send(peer_id, message_id, f"🤝 Заявка в друзья пользователю [id{target_id}|отправлена/принята].")
            else:
                await vk.api_call("friends.delete", user_id=target_id)
                await vk.edit_or_send(peer_id, message_id, f"👋 Пользователь [id{target_id}|удален] из друзей.")
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Ошибка управления друзьями: {e}")
        return True

    return False
