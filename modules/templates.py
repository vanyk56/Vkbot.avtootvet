from typing import Optional, Dict, Any, List
from vk_client import VkClient
import database as db

async def handle_templates_command(
    vk: VkClient,
    peer_id: int,
    message_id: int,
    command: str,
    args: str
) -> bool:
    """Обработчик текстовых и голосовых шаблонов (+шаб, -шаб, шабы, шаб, +гс, -гс, гсы, гс)."""
    cmd = command.lower()

    # --- Текстовые шаблоны ---

    # 1. Список шаблонов: шабы
    if cmd == "шабы":
        names = await db.get_all_templates("text")
        if not names:
            await vk.edit_or_send(peer_id, message_id, "📝 Список текстовых шаблонов пуст.\nДобавить: ответьте на текст `нб +шаб [имя]`")
            return True
        lines = [f"• `{name}`" for name in names]
        await vk.edit_or_send(peer_id, message_id, "📝 **Сохранённые текстовые шаблоны:**\n" + "\n".join(lines) + "\n\nОтправить: `нб шаб [имя]`")
        return True

    # 2. Добавить шаблон: +шаб [название]
    if cmd == "+шаб":
        name = args.strip().lower()
        if not name:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите название шаблона в ответ на сообщение с текстом.\nПример: `нб +шаб приветствие`")
            return True

        # Извлекаем текст из ответа или пересланных сообщений
        text_content = ""
        try:
            res = await vk.api_call("messages.getById", message_ids=message_id)
            items = res.get("items", [])
            if items:
                msg = items[0]
                if msg.get("reply_message") and msg["reply_message"].get("text"):
                    text_content = msg["reply_message"]["text"]
                elif msg.get("fwd_messages") and msg["fwd_messages"][0].get("text"):
                    text_content = msg["fwd_messages"][0]["text"]
        except Exception:
            pass

        if not text_content:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Ответьте на сообщение с текстом, чтобы сохранить его в шаблон!")
            return True

        await db.save_template(name, "text", text_content)
        await vk.edit_or_send(peer_id, message_id, f"✅ Текстовый шаблон `{name}` успешно сохранён!\nВызов: `нб шаб {name}`")
        return True

    # 3. Удалить шаблон: -шаб [название]
    if cmd == "-шаб":
        name = args.strip().lower()
        if not name:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите название шаблона для удаления: `нб -шаб [название]`")
            return True
        deleted = await db.delete_template(name, "text")
        if deleted:
            await vk.edit_or_send(peer_id, message_id, f"✅ Текстовый шаблон `{name}` удалён.")
        else:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Шаблон `{name}` не найден.")
        return True

    # 4. Отправить шаблон: шаб [название]
    if cmd == "шаб":
        name = args.strip().lower()
        if not name:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите имя шаблона: `нб шаб [имя]`. Список: `нб шабы`")
            return True
        tmpl = await db.get_template(name, "text")
        if not tmpl:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Шаблон `{name}` не найден. Доступные шаблоны: `нб шабы`")
            return True
        # Редактируем сообщение прямо в текст сохранённого шаблона
        await vk.edit_or_send(peer_id, message_id, tmpl["content"])
        return True

    # --- Голосовые шаблоны (ГС) ---

    # 5. Список ГС: гсы
    if cmd == "гсы":
        names = await db.get_all_templates("voice")
        if not names:
            await vk.edit_or_send(peer_id, message_id, "🎙️ Список голосовых шаблонов пуст.\nДобавить: ответьте на ГС `нб +гс [имя]`")
            return True
        lines = [f"• `{name}`" for name in names]
        await vk.edit_or_send(peer_id, message_id, "🎙️ **Сохранённые ГС шаблоны:**\n" + "\n".join(lines) + "\n\nОтправить: `нб гс [имя]`")
        return True

    # 6. Добавить ГС: +гс [название]
    if cmd == "+гс":
        name = args.strip().lower()
        if not name:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите название шаблона в ответ на голосовое сообщение: `нб +гс [имя]`")
            return True

        attachment_str = ""
        try:
            res = await vk.api_call("messages.getById", message_ids=message_id)
            items = res.get("items", [])
            if items:
                msg = items[0]
                target_msg = msg.get("reply_message") or (msg.get("fwd_messages")[0] if msg.get("fwd_messages") else None)
                if target_msg and "attachments" in target_msg:
                    for att in target_msg["attachments"]:
                        att_type = att.get("type")
                        if att_type in ("audio_message", "doc"):
                            doc_obj = att.get("audio_message") or att.get("doc")
                            owner_id = doc_obj.get("owner_id")
                            doc_id = doc_obj.get("id")
                            access_key = doc_obj.get("access_key", "")
                            key_part = f"_{access_key}" if access_key else ""
                            attachment_str = f"doc{owner_id}_{doc_id}{key_part}"
                            break
        except Exception:
            pass

        if not attachment_str:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Ответьте на голосовое сообщение (ГС), чтобы сохранить его в шаблон!")
            return True

        await db.save_template(name, "voice", attachment_str)
        await vk.edit_or_send(peer_id, message_id, f"✅ Голосовой шаблон `{name}` успешно сохранён!\nВызов: `нб гс {name}`")
        return True

    # 7. Удалить ГС: -гс [название]
    if cmd == "-гс":
        name = args.strip().lower()
        if not name:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите название ГС для удаления: `нб -гс [название]`")
            return True
        deleted = await db.delete_template(name, "voice")
        if deleted:
            await vk.edit_or_send(peer_id, message_id, f"✅ Голосовой шаблон `{name}` удалён.")
        else:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Голосовой шаблон `{name}` не найден.")
        return True

    # 8. Отправить ГС: гс [название]
    if cmd == "гс":
        name = args.strip().lower()
        if not name:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите имя ГС: `нб гс [имя]`. Список: `нб гсы`")
            return True
        tmpl = await db.get_template(name, "voice")
        if not tmpl:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Голосовой шаблон `{name}` не найден.")
            return True
        # Удаляем команду и отправляем как настоящее голосовое сообщение
        await vk.delete_msg(message_id)
        await vk.send_msg(peer_id, "", attachment=tmpl["content"])
        return True

    return False
