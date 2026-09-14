import time
import random
from typing import Optional, Dict, Any, List
from vk_client import VkClient
from modules.moderation import extract_target_user
from modules.farm import format_duration, COOLDOWNS
import database as db

ZODIAC_PREDICTIONS = [
    "Сегодня звёзды сулят удачу во всех начинаниях и приятный бонус в игре!",
    "Благоприятный день для общения, наведения порядка в беседах и отдыха.",
    "Ваша продуктивность сегодня на максимуме, используйте это время с пользой!",
    "Возможны неожиданные приятные сюрпризы от друзей и близких.",
    "Отличный момент, чтобы накопить фортанты и прокачать свои возможности!",
    "День гармонии и спокойствия. Избегайте лишних споров в чатах."
]

async def handle_info_command(
    vk: VkClient,
    peer_id: int,
    message_id: int,
    command: str,
    args: str,
    owner_id: int,
    msg_timestamp: float = 0.0,
    raw_event: Optional[list] = None
) -> bool:
    """Обработчик информационных команд (инфо, профиль, помощь, пинг, беседа, онлайн, ава, гороскоп, вк ми)."""
    cmd = command.lower()

    # 1. Инфо / Профиль / Я
    if cmd in ("инфо", "профиль", "я"):
        prefix = await db.get_setting("prefix", "нб")
        farm_state = await db.get_iris_farm_state()
        auto_exit = await db.get_bool_setting("auto_exit")
        auto_push = await db.get_bool_setting("auto_push")
        auto_unfriend = await db.get_bool_setting("auto_unfriend")
        offline = await db.get_bool_setting("offline")
        advd = await db.get_bool_setting("advd")
        clean_dogs = await db.get_bool_setting("clean_dogs")
        auto_reply = await db.get_bool_setting("auto_reply")
        auto_reply_text = await db.get_setting("auto_reply_text", "Привет! Меня нет на месте, отвечу позже.")
        duty = await db.get_bool_setting("duty")
        notifs = await db.get_bool_setting("notifications")

        econ = await db.get_user_economy(owner_id)
        premium_str = "Активен ⭐" if econ["is_premium"] else "Не активен ❌"

        # Таймер фермы
        if farm_state["is_enabled"]:
            now = time.time()
            rem = (farm_state.get("last_farm", 0) + COOLDOWNS["farm"]) - now
            farm_str = f"Включена ✅ (до команды {format_duration(rem)})"
        else:
            farm_str = "Выключена ❌"

        status_text = (
            f"📊 **Статус селф-бота «{prefix}»**\n\n"
            f"**Переключатели:**\n"
            f"🌾 Ферма (Ирис): {farm_str}\n"
            f"🚪 Автовыход: {'Включен ✅' if auto_exit else 'Выключен ❌'}\n"
            f"🔔 Автопуши: {'Включены ✅' if auto_push else 'Выключены ❌'}\n"
            f"🧹 Автоотписка: {'Включена ✅' if auto_unfriend else 'Выключена ❌'}\n"
            f"🕶️ Оффлайн: {'Включен ✅' if offline else 'Выключен ❌'}\n"
            f"👥 Адвд (Друзья): {'Включен ✅' if advd else 'Выключен ❌'}\n"
            f"🐶 Чистка собачек: {'Включена ✅' if clean_dogs else 'Выключена ❌'}\n"
            f"🛡️ Дежурный: {'Включен ✅' if duty else 'Выключен ❌'}\n"
            f"🔔 Уведомления: {'Включены ✅' if notifs else 'Выключены ❌'}\n\n"
            f"**Настройки:**\n"
            f"🔹 Текущий префикс: **{prefix}**\n"
            f"🔹 Автоответчик: {'Включен ✅' if auto_reply else 'Выключен ❌'}\n"
            f"🔹 Текст автоответчика: «{auto_reply_text}»\n"
            f"🔹 Баланс: **{econ['fortants']} фортантов**\n"
            f"🔹 Премиум-статус: **{premium_str}**"
        )
        await vk.edit_or_send(peer_id, message_id, status_text)
        return True

    # 2. Пинг / Форматтер пинг
    if cmd in ("пинг", "форматтер пинг"):
        now = time.time()
        delay_ms = int((now - msg_timestamp) * 1000) if msg_timestamp > 0 else 25
        delay_ms = max(5, min(delay_ms, 999))
        await vk.edit_or_send(
            peer_id,
            message_id,
            f"🏓 **ПОНГ!**\n"
            f"⚡ Задержка LongPoll: `{delay_ms} ms`\n"
            f"🟢 Статус: Селф-бот работает штатно"
        )
        return True

    # 3. Беседа
    if cmd == "беседа":
        if peer_id <= 2000000000:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Команда предназначена для бесед!")
            return True
        try:
            members = await vk.api_call("messages.getConversationMembers", peer_id=peer_id)
            count = members.get("count", 0)
            profiles = members.get("profiles", [])
            items = members.get("items", [])

            dogs = sum(1 for p in profiles if p.get("deactivated"))
            admins = [it["member_id"] for it in items if it.get("is_admin")]
            bot_admin = owner_id in admins

            chat_title = "Беседа"
            owner_admin_id = items[0].get("member_id", 0) if items else 0

            info_msg = (
                f"💬 **Информация о беседе:**\n"
                f"🔹 ID чата: `{peer_id - 2000000000}` (Peer: `{peer_id}`)\n"
                f"👥 Всего участников: **{count}**\n"
                f"🐶 Заблокированных («собачек»): **{dogs}**\n"
                f"👑 Администраторов: **{len(admins)}**\n"
                f"🛡️ Статус бота в беседе: {'Администратор 👑' if bot_admin else 'Участник 👤'}"
            )
            await vk.edit_or_send(peer_id, message_id, info_msg)
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Не удалось получить информацию о беседе: {e}")
        return True

    # 4. Онлайн в беседе
    if cmd == "онлайн":
        if peer_id <= 2000000000:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Команда предназначена для бесед!")
            return True
        try:
            members = await vk.api_call("messages.getConversationMembers", peer_id=peer_id)
            profiles = members.get("profiles", [])
            online_users = [p for p in profiles if p.get("online") == 1]
            if not online_users:
                await vk.edit_or_send(peer_id, message_id, "👥 В данный момент никто не в сети.")
                return True
            lines = [f"• [id{u['id']}|{u['first_name']} {u['last_name']}]" for u in online_users[:30]]
            await vk.edit_or_send(
                peer_id,
                message_id,
                f"🟢 **Сейчас онлайн в беседе ({len(online_users)}):**\n" + "\n".join(lines)
            )
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Ошибка получения онлайна: {e}")
        return True

    # 5. Аватарка: ава [ссылка / ответ]
    if cmd == "ава":
        target_id = await extract_target_user(vk, peer_id, message_id, args, raw_event) or owner_id
        try:
            users = await vk.api_call("users.get", user_ids=target_id, fields="photo_max_orig")
            if users:
                photo_url = users[0].get("photo_max_orig")
                name = f"{users[0]['first_name']} {users[0]['last_name']}"
                await vk.edit_or_send(peer_id, message_id, f"🖼️ Аватарка пользователя [id{target_id}|{name}]:\n{photo_url}")
            else:
                await vk.edit_or_send(peer_id, message_id, "⚠️ Пользователь не найден.")
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Ошибка: {e}")
        return True

    # 6. Гороскоп
    if cmd == "гороскоп":
        prediction = random.choice(ZODIAC_PREDICTIONS)
        await vk.edit_or_send(peer_id, message_id, f"🔮 **Астрологический прогноз на сегодня:**\n{prediction}")
        return True

    # 7. Брак помощь
    if cmd in ("брак помощь", "браки"):
        text = (
            "💍 **Модуль «Виртуальные браки»**\n\n"
            "• `преф брак [ссылка / ответ]` — сделать предложение пользователю стать парой.\n"
            "• Если вам уже сделали предложение, повторный ввод команды зарегистрирует брак!\n"
            "• `преф развод` — расторгнуть текущий брак.\n"
            "• `преф профиль` — показывает вашу вторую половинку."
        )
        await vk.edit_or_send(peer_id, message_id, text)
        return True

    # 8. ВК ми (короткая ссылка)
    if cmd == "вк ми":
        if peer_id > 2000000000:
            link = f"https://vk.me/join/{peer_id}"
            await vk.edit_or_send(peer_id, message_id, f"🔗 Ссылка на диалог: {link}")
        else:
            link = f"https://vk.me/id{owner_id}"
            await vk.edit_or_send(peer_id, message_id, f"🔗 Ссылка на личные сообщения: {link}")
        return True

    # 9. Помощь / Кмд
    if cmd in ("помощь", "кмд"):
        prefix = await db.get_setting("prefix", "нб")
        help_text = (
            f"📖 **Команды Селф-бота (Префикс: `{prefix}`)**\n\n"
            f"🔘 **Переключатели On/Off:**\n"
            f"• `{prefix} +ферма` / `-ферма` — сбор бонусов Ириса\n"
            f"• `{prefix} ферма инфо` — таймеры Ириса\n"
            f"• `{prefix} +автовыход` / `-автовыход` — автовыход из чужих бесед\n"
            f"• `{prefix} +автопуши` / `-автопуши` — авточтение упоминаний\n"
            f"• `{prefix} пуши [боты/алл/все]` — фильтр упоминаний\n"
            f"• `{prefix} +автоотписка` / `-автоотписка` — очистка неактивных друзей\n"
            f"• `{prefix} +оффлайн` / `-оффлайн` — режим вечного оффлайна\n"
            f"• `{prefix} +адвд` / `-адвд` — автоприем заявок в друзья\n"
            f"• `{prefix} +собачки` / `-собачки` — чистка от заблокированных аккаунтов\n"
            f"• `{prefix} +автоответчик` / `-автоответчик` / `автоответчик [текст]`\n"
            f"• `{prefix} +деж` / `-деж` — режим «Дежурный»\n"
            f"• `{prefix} префикс [буква]` — смена префикса\n\n"
            f"🛡️ **Модерация и Списки:**\n"
            f"• `{prefix} вернуть` / `{prefix} кик` [цель] — вернуть / кикнуть\n"
            f"• `{prefix} +админ` / `-админ` [цель] — управление админкой\n"
            f"• `{prefix} +игн` / `-игн` [цель], `{prefix} игнлист` — игнор\n"
            f"• `{prefix} +чс` / `-чс` [цель], `{prefix} чсы` — Черный Список ВК\n"
            f"• `{prefix} +дов` / `-дов` [цель], `{prefix} довы` — доверенные\n"
            f"• `{prefix} +др` / `-др` [цель] — добавить / удалить друга\n\n"
            f"⚡ **Автоматизация и Таймеры:**\n"
            f"• `{prefix} авкол [число]` — лимит повторений\n"
            f"• `{prefix} ав [текст] [число]` — циклическая отправка\n"
            f"• `{prefix} повторялка [символ]` — дублирование символов\n"
            f"• `{prefix} удалялка [слово]` — стоп-слова (например `дд`)\n"
            f"• `{prefix} редач [текст]` — анимация редактирования\n"
            f"• `{prefix} +цтаймер [время] [текст]` — циклический таймер\n"
            f"• `{prefix} -цтаймер [id]`, `{prefix} цтаймеры` — список таймеров\n\n"
            f"📂 **Шаблоны (Текст и ГС):**\n"
            f"• `{prefix} +шаб` / `-шаб` / `шабы` / `шаб [имя]` — текст\n"
            f"• `{prefix} +гс` / `-гс` / `гсы` / `гс [имя]` — голосовые (ГС)\n\n"
            f"📊 **Инструменты и Массовые действия:**\n"
            f"• `{prefix} инфо` / `{prefix} профиль` / `{prefix} пинг` / `{prefix} беседа`\n"
            f"• `{prefix} онлайн` / `{prefix} ава` / `{prefix} гороскоп` / `{prefix} вк ми`\n"
            f"• `{prefix} прочитать [все/чаты/группы/беседы]`\n"
            f"• `{prefix} очистить [все/чаты/группы/беседы]`\n"
            f"• `{prefix} влс [текст]` — рассылка по ЛС\n"
            f"• `{prefix} мегапуш` — упомянуть всех участников\n\n"
            f"💎 **Экономика и Интерактив:**\n"
            f"• `{prefix} баланс` / `передать [цель] [кол-во]`\n"
            f"• `{prefix} +премиум [кол-во месяцев]` (50 фортантов)\n"
            f"• `{prefix} +лайк` / `-лайк` / `лайки [цель]`\n"
            f"• `{prefix} брак [цель]` / `{prefix} развод` / `{prefix} стикеры`"
        )
        await vk.edit_or_send(peer_id, message_id, help_text)
        return True

    return False
