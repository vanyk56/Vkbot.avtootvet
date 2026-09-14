import json
from vk_client import VkClient
import database as db

async def handle_toggle_command(
    vk: VkClient,
    peer_id: int,
    message_id: int,
    command: str,
    args: str
) -> bool:
    """Обработка всех команд-переключателей (+ / -) и смены префикса."""
    command_lower = command.lower()
    
    # 1. Изменение префикса: префикс [буква/слово]
    if command_lower == "префикс":
        new_prefix = args.strip().lower()
        if not new_prefix:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите новый префикс. Пример: `нб префикс б`")
            return True
        await db.set_setting("prefix", new_prefix)
        await vk.edit_or_send(peer_id, message_id, f"✅ Префикс успешно изменён на: **{new_prefix}**\nТеперь команды вызываются через: `{new_prefix} инфо`")
        return True

    # 2. Ферма: +ферма / -ферма
    if command_lower in ("+ферма", "-ферма"):
        turn_on = command_lower == "+ферма"
        await db.set_bool_setting("farm", turn_on)
        await db.update_iris_farm_state(peer_id=peer_id, is_enabled=turn_on)
        state_text = "включена ✅\nБот будет собирать бонусы и копать в этой беседе!" if turn_on else "выключена ❌"
        await vk.edit_or_send(peer_id, message_id, f"🌾 Ферма (Ирис) успешно {state_text}")
        return True

    # 3. Автовыход: +автовыход / -автовыход
    if command_lower in ("+автовыход", "-автовыход"):
        turn_on = command_lower == "+автовыход"
        await db.set_bool_setting("auto_exit", turn_on)
        state_text = "включён ✅ (бот будет сразу выходить из любых новых бесед)" if turn_on else "выключен ❌"
        await vk.edit_or_send(peer_id, message_id, f"🚪 Автовыход {state_text}")
        return True

    # 4. Автопуши: +автопуши / -автопуши
    if command_lower in ("+автопуши", "-автопуши"):
        turn_on = command_lower == "+автопуши"
        await db.set_bool_setting("auto_push", turn_on)
        state_text = "включены ✅ (упоминания будут автоматически читаться)" if turn_on else "выключены ❌"
        await vk.edit_or_send(peer_id, message_id, f"🔔 Автопуши {state_text}")
        return True

    # 5. Автоотписка: +автоотписка / -автоотписка
    if command_lower in ("+автоотписка", "-автоотписка"):
        turn_on = command_lower == "+автоотписка"
        await db.set_bool_setting("auto_unfriend", turn_on)
        state_text = "включена ✅ (удаление неактивных и заброшенных страниц из друзей)" if turn_on else "выключена ❌"
        await vk.edit_or_send(peer_id, message_id, f"🧹 Автоотписка {state_text}")
        return True

    # 6. Оффлайн: +оффлайн / -оффлайн
    if command_lower in ("+оффлайн", "-оффлайн"):
        turn_on = command_lower == "+оффлайн"
        await db.set_bool_setting("offline", turn_on)
        state_text = "включен ✅ (вечный оффлайн активирован)" if turn_on else "выключен ❌"
        await vk.edit_or_send(peer_id, message_id, f"🕶️ Режим оффлайн {state_text}")
        return True

    # 7. Адвд: +адвд / -адвд
    if command_lower in ("+адвд", "-адвд"):
        turn_on = command_lower == "+адвд"
        await db.set_bool_setting("advd", turn_on)
        state_text = "включено ✅ (заявки в друзья принимаются автоматически)" if turn_on else "выключено ❌"
        await vk.edit_or_send(peer_id, message_id, f"👥 Автодобавление в друзья (Адвд) {state_text}")
        return True

    # 8. Собачки: +собачки / -собачки
    if command_lower in ("+собачки", "-собачки"):
        turn_on = command_lower == "+собачки"
        await db.set_bool_setting("clean_dogs", turn_on)
        state_text = "включена ✅ (периодическая очистка от заблокированных аккаунтов)" if turn_on else "выключена ❌"
        await vk.edit_or_send(peer_id, message_id, f"🐶 Чистка собачек {state_text}")
        return True

    # 9. Автоответчик: +автоответчик / -автоответчик / автоответчик [текст]
    if command_lower in ("+автоответчик", "-автоответчик"):
        turn_on = command_lower == "+автоответчик"
        await db.set_bool_setting("auto_reply", turn_on)
        cur_text = await db.get_setting("auto_reply_text")
        state_text = f"включен ✅\nТекущий текст: «{cur_text}»" if turn_on else "выключен ❌"
        await vk.edit_or_send(peer_id, message_id, f"🤖 Автоответчик в ЛС {state_text}")
        return True

    if command_lower == "автоответчик":
        if not args.strip():
            cur_text = await db.get_setting("auto_reply_text")
            is_on = await db.get_bool_setting("auto_reply")
            status = "Включен ✅" if is_on else "Выключен ❌"
            await vk.edit_or_send(peer_id, message_id, f"🤖 Автоответчик ({status})\nТекст: «{cur_text}»\nИзменить: `нб автоответчик [ваш текст]`")
            return True
        await db.set_setting("auto_reply_text", args.strip())
        await vk.edit_or_send(peer_id, message_id, f"✅ Текст автоответчика обновлён на:\n«{args.strip()}»")
        return True

    # 10. Уведомления: +уведы / -уведы
    if command_lower in ("+уведы", "-уведы"):
        turn_on = command_lower == "+уведы"
        await db.set_bool_setting("notifications", turn_on)
        state_text = "включены ✅" if turn_on else "выключены ❌"
        await vk.edit_or_send(peer_id, message_id, f"🔔 Уведомления от бота {state_text}")
        return True

    # 11. Дежурный: +деж / -деж
    if command_lower in ("+деж", "-деж"):
        turn_on = command_lower == "+деж"
        await db.set_bool_setting("duty", turn_on)
        state_text = "включен ✅ (доверенные лица могут выполнять команды бота)" if turn_on else "выключен ❌"
        await vk.edit_or_send(peer_id, message_id, f"🛡️ Режим «Дежурный» {state_text}")
        return True

    return False
