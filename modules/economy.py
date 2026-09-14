import time
from datetime import datetime
from typing import Optional
from vk_client import VkClient
from modules.moderation import extract_target_user
import database as db

async def handle_economy_command(
    vk: VkClient,
    peer_id: int,
    message_id: int,
    command: str,
    args: str,
    owner_id: int,
    raw_event: Optional[list] = None
) -> bool:
    """Обработчик экономики (баланс, передать, +премиум)."""
    cmd = command.lower()

    # 1. Баланс: баланс
    if cmd == "баланс":
        econ = await db.get_user_economy(owner_id)
        prem_status = "Активен ⭐" if econ["is_premium"] else "Не активен ❌"
        prem_date = ""
        if econ["is_premium"]:
            dt = datetime.fromtimestamp(econ["premium_until"]).strftime("%d.%m.%Y %H:%M")
            prem_date = f"\n🔹 Действует до: {dt}"

        msg = (
            f"💰 **Ваш кошелёк:**\n"
            f"🔹 Баланс: **{econ['fortants']}** фортантов\n"
            f"🔹 Премиум: {prem_status}{prem_date}\n\n"
            f"💡 Активировать премиум: `нб +премиум 1` (50 фортантов/мес)"
        )
        await vk.edit_or_send(peer_id, message_id, msg)
        return True

    # 2. Передать фортанты: передать [ссылка / ответ] [кол-во]
    if cmd == "передать":
        tokens = args.strip().split()
        if not tokens:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Использование: `нб передать [ссылка / ответ] [кол-во]`\nПример: `нб передать @durov 25`")
            return True

        amount = 0
        target_str = ""
        for t in tokens:
            if t.isdigit():
                amount = int(t)
            else:
                target_str = t

        target_id = await extract_target_user(vk, peer_id, message_id, target_str, raw_event)
        if not target_id or target_id == owner_id:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите корректного получателя фортантов (ссылку или ответ).")
            return True

        if amount <= 0:
            await vk.edit_or_send(peer_id, message_id, "⚠️ Укажите положительную сумму фортантов для перевода.")
            return True

        sender_econ = await db.get_user_economy(owner_id)
        if sender_econ["fortants"] < amount:
            await vk.edit_or_send(peer_id, message_id, f"⚠️ Недостаточно фортантов! Ваш баланс: {sender_econ['fortants']}, требуется: {amount}.")
            return True

        target_econ = await db.get_user_economy(target_id)
        await db.set_user_balance(owner_id, sender_econ["fortants"] - amount)
        await db.set_user_balance(target_id, target_econ["fortants"] + amount)

        await vk.edit_or_send(
            peer_id,
            message_id,
            f"💸 Успешный перевод!\n"
            f"🔹 Отправлено: **{amount}** фортантов пользователю [id{target_id}|получателю]\n"
            f"🔹 Ваш остаток: **{sender_econ['fortants'] - amount}** фортантов"
        )
        return True

    # 3. Активация Премиума: +премиум [кол-во месяцев]
    if cmd == "+премиум":
        months = 1
        if args.strip().isdigit():
            months = max(1, int(args.strip()))

        price = months * 50
        econ = await db.get_user_economy(owner_id)
        if econ["fortants"] < price:
            await vk.edit_or_send(
                peer_id,
                message_id,
                f"⚠️ Недостаточно средств для покупки премиума на {months} мес.!\n"
                f"Стоимость: **{price}** фортантов (50 за мес.), ваш баланс: **{econ['fortants']}**."
            )
            return True

        # Списание и начисление премиума
        await db.set_user_balance(owner_id, econ["fortants"] - price)
        new_expiry = await db.add_user_premium_months(owner_id, months)
        exp_date_str = datetime.fromtimestamp(new_expiry).strftime("%d.%m.%Y %H:%M")

        msg = (
            f"⭐ **Поздравляем с активацией Премиума!**\n"
            f"🔹 Продлено на: **{months}** мес.\n"
            f"🔹 Активен до: **{exp_date_str}**\n"
            f"🔹 Списано: **{price}** фортантов\n\n"
            f"🚀 Вам доступны расширенные лимиты `авкол` до 100 и команда `мегапуш`!"
        )
        await vk.edit_or_send(peer_id, message_id, msg)
        return True

    return False
