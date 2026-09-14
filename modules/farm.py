import asyncio
import time
from typing import Dict, Any
from vk_client import VkClient
import database as db

# Интервалы перезарядки команд Ириса (в секундах)
COOLDOWNS = {
    "farm": 4 * 3600,     # Ферма: раз в 4 часа
    "work": 4 * 3600,     # Работа: раз в 4 часа
    "mine": 4 * 3600,     # Шахта: раз в 4 часа
    "bonus": 24 * 3600,   # Бонус: раз в сутки
    "dig": 2 * 3600       # Копать: раз в 2 часа
}

COMMAND_NAMES = {
    "farm": "Ферма",
    "work": "Работа",
    "mine": "Шахта",
    "bonus": "Бонус",
    "dig": "Копать"
}

def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "Готово к сбору! ⚡"
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    parts = []
    if h > 0:
        parts.append(f"{h}ч")
    if m > 0:
        parts.append(f"{m}м")
    parts.append(f"{sec}с")
    return " ".join(parts)

async def get_farm_info_text() -> str:
    """Формирует отчет о статусе фермы и таймерах обратного отсчета."""
    state = await db.get_iris_farm_state()
    is_on = state["is_enabled"]
    now = time.time()

    status_icon = "Включена ✅" if is_on else "Выключена ❌"
    peer_info = f"Беседа #{state['peer_id'] - 2000000000}" if state['peer_id'] > 2000000000 else f"Диалог {state['peer_id']}"

    lines = [
        "🌾 **Статус модуля «Ферма (Ирис)»**",
        f"🔹 Состояние: {status_icon}",
        f"🔹 Цель отправки: {peer_info if state['peer_id'] != 0 else 'Не установлена (напишите `нб +ферма` в нужной беседе)'}",
        "",
        "⏳ **Таймеры до следующей отправки команд:**"
    ]

    for key, name in COMMAND_NAMES.items():
        last_time = state.get(f"last_{key}", 0)
        cd = COOLDOWNS[key]
        rem = (last_time + cd) - now
        lines.append(f"• «{name}»: {format_duration(rem)}")

    return "\n".join(lines)

async def run_farm_cycle_step(vk: VkClient):
    """Один шаг проверки и отправки команд фермы в фоновом режиме."""
    state = await db.get_iris_farm_state()
    if not state["is_enabled"] or state["peer_id"] == 0:
        return

    now = time.time()
    peer_id = state["peer_id"]

    for key, cmd_text in COMMAND_NAMES.items():
        last_time = state.get(f"last_{key}", 0)
        cd = COOLDOWNS[key]
        if (now - last_time) >= cd:
            try:
                await vk.send_msg(peer_id, cmd_text)
                await db.update_iris_farm_state(**{f"last_{key}": now})
                await asyncio.sleep(3.0)  # Задержка между отправками команд
            except Exception:
                pass
