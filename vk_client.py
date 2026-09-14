import asyncio
import aiohttp
import re
import time
from typing import Optional, Dict, Any, List, Union
import config
from config import VK_API_VERSION

class VkApiError(Exception):
    def __init__(self, error_code: int, error_msg: str, request_params: Optional[dict] = None):
        super().__init__(f"VK API Error [{error_code}]: {error_msg}")
        self.error_code = error_code
        self.error_msg = error_msg
        self.request_params = request_params

class VkClient:
    def __init__(self, token: str):
        self.token = token
        self.session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        self._last_request_time = 0.0
        self._min_interval = 0.34  # ~3 запроса в секунду для соблюдения лимитов VK API

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            headers = {
                "User-Agent": "KateMobileAndroid/110.1 lite-535 (Android 14; SDK 34; arm64-v8a; Xiaomi 2201117TY; ru)"
            }
            connector = None
            if config.PROXY_URL:
                try:
                    from aiohttp_socks import ProxyConnector
                    connector = ProxyConnector.from_url(config.PROXY_URL)
                except Exception as e:
                    print(f"⚠️ Ошибка инициализации прокси: {e}")

            self.session = aiohttp.ClientSession(
                headers=headers,
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=40)
            )
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def api_call(self, method: str, **params) -> Dict[str, Any]:
        """Вызов метода VK API с автоматической задержкой и обработкой ошибок."""
        session = await self.get_session()
        params["v"] = VK_API_VERSION
        params["access_token"] = self.token

        async with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_time = time.time()

        for attempt in range(3):
            try:
                async with session.post(f"https://api.vk.com/method/{method}", data=params) as resp:
                    data = await resp.json()
                    if "error" in data:
                        err = data["error"]
                        code = err.get("error_code", 0)
                        msg = err.get("error_msg", "Unknown error")
                        # Ошибка 6: Too many requests per second -> ждём и повторяем
                        if code == 6 and attempt < 2:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        raise VkApiError(code, msg, err.get("request_params"))
                    return data.get("response")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < 2:
                    await asyncio.sleep(1.0)
                    continue
                raise e

        raise VkApiError(-1, "Failed after 3 attempts")

    async def resolve_target(self, target_str: str) -> Optional[int]:
        """Определение ID пользователя по строке (число, id123, vk.com/..., [id123|name], screen_name)."""
        if not target_str:
            return None
        target_str = target_str.strip()

        # 1. Формат упоминания: [id12345|Имя] или [club12345|Группа]
        mention_match = re.match(r"\[(id|club|public)(\d+)\|.*?\]", target_str)
        if mention_match:
            prefix, obj_id = mention_match.group(1), int(mention_match.group(2))
            return -obj_id if prefix in ("club", "public") else obj_id

        # 2. Формат ссылки: vk.com/..., vk.ru/..., m.vk.com/...
        url_match = re.search(r"(?:vk\.com|vk\.ru)/(?:id(\d+)|([a-zA-Z0-9_\.]+))", target_str)
        if url_match:
            if url_match.group(1):
                return int(url_match.group(1))
            screen_name = url_match.group(2)
            return await self._resolve_screen_name(screen_name)

        # 3. Числовой id или id123
        if target_str.startswith("id") and target_str[2:].isdigit():
            return int(target_str[2:])
        if target_str.lstrip("-").isdigit():
            return int(target_str)

        # 4. Произвольный screen_name (например durov)
        return await self._resolve_screen_name(target_str)

    async def _resolve_screen_name(self, screen_name: str) -> Optional[int]:
        try:
            res = await self.api_call("utils.resolveScreenName", screen_name=screen_name)
            if res and isinstance(res, dict):
                obj_type = res.get("type")
                obj_id = res.get("object_id")
                if obj_type == "user":
                    return obj_id
                elif obj_type in ("group", "page"):
                    return -obj_id
        except Exception:
            pass
        return None

    async def edit_or_send(
        self,
        peer_id: int,
        message_id: Optional[int],
        text: str,
        attachment: Optional[str] = None
    ) -> int:
        """Редактирует указанное сообщение, если возможно, иначе отправляет новое."""
        if message_id:
            try:
                params = {
                    "peer_id": peer_id,
                    "message_id": message_id,
                    "message": text,
                    "keep_forward_messages": 1
                }
                if attachment:
                    params["attachment"] = attachment
                res = await self.api_call("messages.edit", **params)
                if res:
                    return message_id
            except Exception:
                pass

        # Если отредактировать не удалось, отправляем новое сообщение
        send_params = {
            "peer_id": peer_id,
            "message": text,
            "random_id": int(time.time() * 1000) % 2147483647
        }
        if attachment:
            send_params["attachment"] = attachment
        return await self.api_call("messages.send", **send_params)

    async def send_msg(self, peer_id: int, text: str, attachment: Optional[str] = None, reply_to: Optional[int] = None) -> int:
        """Отправка нового сообщения."""
        params = {
            "peer_id": peer_id,
            "message": text,
            "random_id": int(time.time() * 10000) % 2147483647
        }
        if attachment:
            params["attachment"] = attachment
        if reply_to:
            params["reply_to"] = reply_to
        return await self.api_call("messages.send", **params)

    async def delete_msg(self, message_ids: Union[int, List[int]], delete_for_all: int = 1):
        """Удаление сообщений."""
        ids_str = str(message_ids) if isinstance(message_ids, int) else ",".join(map(str, message_ids))
        try:
            await self.api_call("messages.delete", message_ids=ids_str, delete_for_all=delete_for_all)
        except Exception:
            pass

    async def longpoll_stream(self):
        """Асинхронный генератор событий User LongPoll."""
        server_info = await self.api_call("messages.getLongPollServer", need_pts=0, lp_version=10)
        server = server_info["server"]
        key = server_info["key"]
        ts = server_info["ts"]

        session = await self.get_session()

        while True:
            url = f"https://{server}?act=a_check&key={key}&ts={ts}&wait=25&mode=2&version=10"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=40)) as resp:
                    data = await resp.json()
                    if "failed" in data:
                        code = data["failed"]
                        if code == 1:
                            ts = data["ts"]
                        elif code in (2, 3):
                            # Ключ устарел или информация сервера изменилась
                            server_info = await self.api_call("messages.getLongPollServer", need_pts=0, lp_version=10)
                            server = server_info["server"]
                            key = server_info["key"]
                            ts = server_info["ts"]
                        continue

                    ts = data.get("ts", ts)
                    updates = data.get("updates", [])
                    for update in updates:
                        yield update
            except asyncio.CancelledError:
                break
            except Exception as e:
                await asyncio.sleep(2.0)
                # Переполучаем данные сервера при сбое соединения
                try:
                    server_info = await self.api_call("messages.getLongPollServer", need_pts=0, lp_version=10)
                    server = server_info["server"]
                    key = server_info["key"]
                    ts = server_info["ts"]
                except Exception:
                    await asyncio.sleep(3.0)
