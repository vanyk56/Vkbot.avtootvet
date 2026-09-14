from typing import Optional, Dict, Any, List
from vk_client import VkClient
from modules.moderation import extract_target_user
import database as db

# Временное хранилище предложений брака: target_id -> from_id
PENDING_MARRIAGES: Dict[int, int] = {}

async def handle_interactive_command(
    vk: VkClient,
    peer_id: int,
    message_id: int,
    command: str,
    args: str,
    owner_id: int,
    raw_event: Optional[list] = None
) -> bool:
    """Обработчик интерактивных команд: лайки, браки, развод, стикеры."""
    cmd = command.lower()

    # --- Лайки: +лайк, -лайк, лайки ---
    if cmd in ("+лайк", "-лайк", "лайки"):
        target_id = await extract_target_user(vk, peer_id, message_id, args, raw_event) or owner_id
        try:
            # Получаем последнюю запись на стене пользователя или аватар
            wall = await vk.api_call("wall.get", owner_id=target_id, count=1)
            posts = wall.get("items", []) if isinstance(wall, dict) else []

            item_type = "post"
            item_id = 0
            if posts:
                item_id = posts[0]["id"]
            else:
                # Если на стене пусто, ищем фото профиля
                photos = await vk.api_call("photos.get", owner_id=target_id, album_id="profile", rev=1, count=1)
                items = photos.get("items", []) if isinstance(photos, dict) else []
                if items:
                    item_type = "photo"
                    item_id = items[0]["id"]

            if not item_id:
                await vk.edit_or_send(peer_id, message_id, "⚠️ У пользователя нет доступных постов или фото для лайка.")
                return True

            if cmd == "+лайк":
                await vk.api_call("likes.add", type=item_type, owner_id=target_id, item_id=item_id)
                await vk.edit_or_send(peer_id, message_id, f"❤️ Лайк успешно поставлен на первый {item_type} пользователя [id{target_id}|id{target_id}]!")
            elif cmd == "-лайк":
                await vk.api_call("likes.delete", type=item_type, owner_id=target_id, item_id=item_id)
                await vk.edit_or_send(peer_id, message_id, f"💔 Лайк успешно убран с объекта пользователя [id{target_id}|id{target_id}].")
            elif cmd == "лайки":
                is_liked = await vk.api_call("likes.isLiked", type=item_type, owner_id=target_id, item_id=item_id)
                liked_status = "Стоит ❤️" if is_liked.get("liked") else "Не стоит 🤍"
                likes_info = await vk.api_call("likes.getList", type=item_type, owner_id=target_id, item_id=item_id)
                total_likes = likes_info.get("count", 0)
                await vk.edit_or_send(
                    peer_id,
                    message_id,
                    f"📊 **Статистика лайков объекта:**\n"
                    f"🔹 Всего отметкок «Нравится»: **{total_likes}**\n"
                    f"🔹 Ваш лайк: **{liked_status}**"
                )
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Ошибка при работе с лайками: {e}")
        return True

    # --- Браки: брак, развод ---
    if cmd == "развод":
        partner_id = await db.divorce_marriage(owner_id)
        if partner_id:
            await vk.edit_or_send(peer_id, message_id, f"💔 Ваш виртуальный брак с [id{partner_id}|партнером] успешно расторгнут.")
        else:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Вы не состоите в браке.")
        return True

    if cmd == "брак":
        target_id = await extract_target_user(vk, peer_id, message_id, args, raw_event)
        if not target_id:
            econ = await db.get_user_economy(owner_id)
            if econ["partner_id"]:
                try:
                    users = await vk.api_call("users.get", user_ids=econ["partner_id"])
                    name = f"{users[0]['first_name']} {users[0]['last_name']}"
                    await vk.edit_or_send(peer_id, message_id, f"💍 Ваша вторая половинка: [id{econ['partner_id']}|{name}] ❤️")
                except Exception:
                    await vk.edit_or_send(peer_id, message_id, f"💍 Ваша вторая половинка: [id{econ['partner_id']}|партнер] ❤️")
            else:
                await vk.edit_or_send(peer_id, message_id, "💍 Вы пока не состоите в браке. Сделать предложение: `нб брак [ссылка / ответ]`")
            return True

        if target_id == owner_id:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Нельзя заключить брак с самим собой!")
            return True

        # Проверяем, есть ли встречное предложение
        if PENDING_MARRIAGES.get(owner_id) == target_id:
            # Заключаем брак!
            del PENDING_MARRIAGES[owner_id]
            await db.set_marriage(owner_id, target_id)
            await vk.edit_or_send(peer_id, message_id, f"🎉 **Совет да любовь!** [id{owner_id}|Вы] и [id{target_id}|партнер] теперь официально состоите в виртуальном браке! 💍❤️")
            return True
        else:
            # Отправляем предложение
            PENDING_MARRIAGES[target_id] = owner_id
            await vk.edit_or_send(peer_id, message_id, f"💍 [id{target_id}|Вам] сделано предложение руки и сердца от [id{owner_id}|владельца бота]!\nДля согласия введите: `нб брак` в ответ.")
            return True

    # --- Стикеры: стикеры ---
    if cmd == "стикеры":
        try:
            res = await vk.api_call("store.getProducts", type="stickers", filters="purchased")
            items = res.get("items", []) if isinstance(res, dict) else []
            count = len(items)
            if not items:
                await vk.edit_or_send(peer_id, message_id, "📦 На аккаунте нет активированных наборов стикеров или доступ закрыт.")
                return True
            pack_names = [f"• {p.get('title', 'Набор')}" for p in items[:25]]
            await vk.edit_or_send(
                peer_id,
                message_id,
                f"🎨 **Ваши стикерпаки ({count} шт.):**\n" + "\n".join(pack_names)
            )
        except Exception as e:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Не удалось получить список стикеров: {e}")
        return True

    return False
