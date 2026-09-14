import asyncio
import re
import time
import json
from typing import Optional, List, Dict, Any
from vk_client import VkClient
import database as db

def parse_interval(time_str: str) -> int:
    """Парсит строки вида '1ч 30с', '15м', '2ч', '45с' в секунды."""
    total_seconds = 0
    patterns = {
        r"(\d+)\s*(?:ч|час|часа|часов|h)": 3600,
        r"(\d+)\s*(?:м|мин|минут|минуты|m)": 60,
        r"(\d+)\s*(?:с|сек|секунд|секунды|s)": 1
    }
    found = False
    for pat, mult in patterns.items():
        match = re.search(pat, time_str, re.IGNORECASE)
        if match:
            total_seconds += int(match.group(1)) * mult
            found = True

    if not found and time_str.isdigit():
        total_seconds = int(time_str)

    return total_seconds

async def handle_automation_command(
    vk: VkClient,
    peer_id: int,
    message_id: int,
    command: str,
    args: str,
    owner_id: int
) -> bool:
    """Обработчик команд автоматизации, повторителя, стоп-слов и циклических таймеров."""
    cmd = command.lower()

    # 1. Лимит повторов: авкол [кол-во]
    if cmd == "авкол":
        if not args.isdigit():
            cur_limit = await db.get_setting("av_count", "5")
            await vk.edit_or_send(peer_id, message_id, f"⚙️ Текущий лимит повторений авкол: **{cur_limit}**\nПример установки: `нб авкол 10`")
            return True
        val = int(args)
        econ = await db.get_user_economy(owner_id)
        max_allowed = 100 if econ["is_premium"] else 20
        if val > max_allowed:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Без премиума максимальный лимит: **{max_allowed}** (с премиумом — 100).\nОформите премиум через `нб +премиум 1`")
            return True
        await db.set_setting("av_count", str(val))
        await vk.edit_or_send(peer_id, message_id, f"✅ Лимит повторений авкол установлен на: **{val}**")
        return True

    # 2. Авто-действие/спам: ав [действие] [кол-во]
    if cmd == "ав":
        if not args.strip():
            await vk.edit_or_send(peer_id, message_id, "⚠️ Использование: `нб ав [текст/действие] [кол-во]`\nПример: `нб ав привет 5`")
            return True
        parts = args.strip().rsplit(maxsplit=1)
        action_text = args.strip()
        count = int(await db.get_setting("av_count", "5"))
        if len(parts) == 2 and parts[1].isdigit():
            action_text = parts[0]
            count = int(parts[1])

        econ = await db.get_user_economy(owner_id)
        max_allowed = 100 if econ["is_premium"] else 20
        count = min(count, max_allowed)

        await vk.delete_msg(message_id)
        for _ in range(count):
            await vk.send_msg(peer_id, action_text)
            await asyncio.sleep(0.4)
        return True

    # 3. Авлист: +авлист / -авлист / авлист
    if cmd in ("+авлист", "-авлист"):
        target_id = await vk.resolve_target(args)
        if not target_id:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите пользователя для авлиста.")
            return True
        if cmd == "+авлист":
            await db.add_to_list("auto_action", target_id)
            await vk.edit_or_send(peer_id, message_id, f"🎯 Пользователь [id{target_id}|добавлен] в список авлиста.")
        else:
            await db.remove_from_list("auto_action", target_id)
            await vk.edit_or_send(peer_id, message_id, f"🎯 Пользователь [id{target_id}|удален] из списка авлиста.")
        return True

    if cmd == "авлист":
        av_ids = await db.get_list_items("auto_action")
        if not av_ids:
            await vk.edit_or_send(peer_id, message_id, "📋 Список авлиста пуст.")
            return True
        lines = [f"• [id{uid}|Пользователь id{uid}]" for uid in av_ids]
        await vk.edit_or_send(peer_id, message_id, "🎯 **Список авлиста:**\n" + "\n".join(lines))
        return True

    # 4. Повторялка: повторялка [символ/текст]
    if cmd == "повторялка":
        if not args.strip():
            await vk.edit_or_send(peer_id, message_id, "⚠️ Использование: `нб повторялка [символ/текст]`\nПример: `нб повторялка 🚀`")
            return True
        repeat_count = int(await db.get_setting("av_count", "5"))
        repeated = (args.strip() + " ") * repeat_count
        await vk.edit_or_send(peer_id, message_id, repeated.strip())
        return True

    # 5. Удалялка стоп-слов: удалялка [текст]
    if cmd == "удалялка":
        raw_words = await db.get_setting("stop_delete_words", '["дд"]')
        words = json.loads(raw_words)
        if not args.strip():
            await vk.edit_or_send(peer_id, message_id, f"🗑️ Текущие стоп-слова для автоудаления: **{', '.join(words)}**\nПри вводе такого слова бот мгновенно стирает ваши сообщения.\nДобавить слово: `нб удалялка +[слово]`\nУдалить слово: `нб удалялка -[слово]`")
            return True
        arg = args.strip()
        if arg.startswith("+"):
            word = arg[1:].strip().lower()
            if word and word not in words:
                words.append(word)
                await db.set_setting("stop_delete_words", json.dumps(words))
                await vk.edit_or_send(peer_id, message_id, f"✅ Слово «{word}» добавлено в стоп-слова удалялки.")
        elif arg.startswith("-"):
            word = arg[1:].strip().lower()
            if word in words:
                words.remove(word)
                await db.set_setting("stop_delete_words", json.dumps(words))
                await vk.edit_or_send(peer_id, message_id, f"✅ Слово «{word}» удалено из удалялки.")
        else:
            # Замена списка на одно слово
            words = [arg.lower()]
            await db.set_setting("stop_delete_words", json.dumps(words))
            await vk.edit_or_send(peer_id, message_id, f"✅ Стоп-слово удалялки установлено: «{arg.lower()}»")
        return True

    # 6. Редач: редач [текст] (эффект печатной машинки)
    if cmd == "редач":
        if not args.strip():
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите текст для редача. Пример: `нб редач Взлом системы...`")
            return True
        target_text = args.strip()
        # Эффект печатной машинки по шагам
        step_len = max(1, len(target_text) // 6)
        current_chunk = ""
        for i in range(0, len(target_text), step_len):
            current_chunk = target_text[:i + step_len]
            try:
                await vk.api_call("messages.edit", peer_id=peer_id, message_id=message_id, message=current_chunk + " ▌")
                await asyncio.sleep(0.3)
            except Exception:
                break
        await vk.edit_or_send(peer_id, message_id, target_text)
        return True

    # 7. Циклический таймер: +цтаймер [время] [текст] / -цтаймер [id] / цтаймеры
    if cmd in ("+цтаймер", "цтаймер"):
        # Если команда просто "цтаймеры" или "+цтаймер" без аргументов
        if not args.strip() or cmd == "цтаймеры":
            timers = await db.get_active_cyclic_timers()
            if not timers:
                await vk.edit_or_send(peer_id, message_id, "⏱️ Нет активных циклических таймеров.\nСоздать: `нб +цтаймер 1ч 30с Текст`")
                return True
            lines = []
            for t in timers:
                rem = max(0, int(t['next_run'] - time.time()))
                lines.append(f"• ID #{t['id']} (Каждые {t['interval']}с, след через {rem}с): «{t['text']}»")
            await vk.edit_or_send(peer_id, message_id, "⏱️ **Активные циклические таймеры:**\n" + "\n".join(lines) + "\n\nОстановить: `нб -цтаймер [ID]`")
            return True

        # Разбор времени и текста
        # Пример: 1ч 30с Привет всем!
        time_tokens = []
        text_tokens = []
        tokens = args.strip().split()
        idx = 0
        while idx < len(tokens):
            tok = tokens[idx]
            if re.match(r"^\d+(?:ч|м|с|h|m|s|сек|мин|час)?$", tok, re.IGNORECASE):
                time_tokens.append(tok)
                idx += 1
            else:
                break
        time_part = " ".join(time_tokens)
        msg_part = " ".join(tokens[idx:])

        if not time_part or not msg_part:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Использование: `нб +цтаймер [время] [текст]`\nПример: `нб +цтаймер 1ч 30с Привет чат!` или `нб +цтаймер 10м копать`")
            return True

        interval_seconds = parse_interval(time_part)
        if interval_seconds < 5:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Минимальный интервал таймера — 5 секунд во избежание блокировок API.")
            return True

        timer_id = await db.add_cyclic_timer(peer_id, interval_seconds, msg_part)
        await vk.edit_or_send(
            peer_id,
            message_id,
            f"✅ Циклический таймер #{timer_id} успешно запущен!\n"
            f"🔹 Интервал: {interval_seconds} сек ({time_part})\n"
            f"🔹 Текст: «{msg_part}»\n"
            f"🔹 Остановить: `нб -цтаймер {timer_id}`"
        )
        return True

    if cmd == "-цтаймер":
        if not args.isdigit():
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите ID таймера для остановки. Список: `нб цтаймеры`\nПример: `нб -цтаймер 1`")
            return True
        timer_id = int(args)
        deleted = await db.remove_cyclic_timer(timer_id)
        if deleted:
            await vk.edit_or_send(peer_id, message_id, f"✅ Циклический таймер #{timer_id} успешно удалён и остановлен.")
        else:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Таймер #{timer_id} не найден.")
        return True

    return False
