import asyncio
import json
import os
from datetime import datetime, timedelta
from time import time


import aiohttp
import brotli
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from bot.config import settings

from bot.utils import logger
from bot.exceptions import InvalidSession
from .headers import headers

from random import randint

from ..config.youtube_tasks import YOUTUBE_TASKS
from ..utils.file_manager import get_random_cat_image
from ..utils.tg_manager.TGSession import TGSession


class Tapper:
    def __init__(self, tg_session: TGSession):
        self.tg_session = tg_session
        self.session_name = tg_session.session_name
        self.start_param = ''
        self.name = ''

    async def login(self, http_client: aiohttp.ClientSession, retry=0):
        try:
            response = await http_client.get("https://api.catshouse.club/user",
                                             timeout=aiohttp.ClientTimeout(60))

            if response.status == 404:
                response = await http_client.post("https://api.catshouse.club/user/create",
                                                  params={"referral_code": self.start_param})
                response.raise_for_status()
                logger.success(f"{self.session_name} | User successfully registered!")
                await asyncio.sleep(delay=2)
                return await self.login(http_client)

            response.raise_for_status()
            response_bytes = await response.read()
            response_text = brotli.decompress(response_bytes)
            response_json = json.loads(response_text.decode('utf-8'))
            return response_json

        except Exception as error:
            if retry < 5:
                logger.warning(f"{self.session_name} | Can't logging | Retry attempt: {retry}")
                await asyncio.sleep(delay=randint(5, 10))
                return await self.login(http_client, retry=retry+1)

            logger.error(f"{self.session_name} | Unknown error when logging: {error}")
            await asyncio.sleep(delay=randint(3, 7))

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(url='https://ipinfo.io/ip', timeout=aiohttp.ClientTimeout(20))
            ip = (await response.text())
            logger.info(f"{self.session_name} | Proxy IP: {ip}")
        except Exception as error:
            logger.error(f"{self.session_name} | Proxy: {proxy} | Error: {error}")

    async def get_all_tasks(self, http_client: aiohttp.ClientSession, groups: list[str], retry=0):
        try:
            tasks = []
            for group in groups:
                response = await http_client.get(f"https://api.catshouse.club/tasks/user?group={group}")
                response.raise_for_status()
                response_bytes = await response.read()
                response_text = brotli.decompress(response_bytes)
                tasks_json = json.loads(response_text.decode('utf-8'))
                tasks += tasks_json.get('tasks')
                await asyncio.sleep(delay=randint(1, 3))
            return tasks
        except Exception as error:
            if retry < 5:
                logger.warning(f"{self.session_name} | Can't getting tasks | Retry attempt: {retry}")
                await asyncio.sleep(delay=randint(5, 10))
                return await self.get_all_tasks(http_client, groups, retry=retry+1)

            logger.error(f"{self.session_name} | Unknown error when getting tasks: {error}")
            await asyncio.sleep(delay=3)

    async def processing_tasks(self, http_client: aiohttp.ClientSession):
        try:
            tasks = await self.get_all_tasks(http_client, ['cats', 'bitget', 'kukoin', 'okx'])
            if tasks:
                for task in tasks:
                    if not task['completed'] and not task['isPending'] and task['type'] not in settings.DISABLED_TASKS:
                        if task['type'] == 'NICKNAME_CHANGE':
                            if '🐈‍⬛' in self.name:
                                result = await self.verify_task(http_client, task['id'], endpoint='check')
                                if result:
                                    logger.info(f"{self.session_name} | Removing 🐈 from nickname")
                                    name = self.name.split('🐈‍⬛')[0]
                                    await self.tg_session.change_tg_nickname(name=name)
                            else:
                                logger.info(f"{self.session_name} | Performing <lc>{task['title']}</lc> task")
                                cat_name = f'{self.name}🐈‍⬛'
                                await self.tg_session.change_tg_nickname(name=cat_name)
                                continue
                        elif task['type'] == 'SUBSCRIBE_TO_CHANNEL':
                            if not settings.JOIN_TG_CHANNELS:
                                continue
                            url = task['params']['channelUrl']
                            logger.info(f"{self.session_name} | Performing TG subscription to <lc>{url}</lc>")
                            await self.tg_session.join_tg_channel(url)
                            result = await self.verify_task(http_client, task['id'], endpoint='check')

                        elif task['type'] == 'YOUTUBE_WATCH':
                            logger.info(f'{self.session_name} | Performing Youtube <y>{task["title"]}</y>')
                            answer = YOUTUBE_TASKS.get(task["title"], None)
                            if answer:
                                endpoint = f'complete?answer={answer}'
                                await asyncio.sleep(delay=randint(30, 60))
                                result = await self.verify_task(http_client, task['id'], endpoint=endpoint)
                            else:
                                logger.warning(f'{self.session_name} | Answer for task <y>{task["title"]}</y> not found')
                                continue
                        else:
                            logger.info(f"{self.session_name} | Performing <lc>{task['title']}</lc> task")
                            result = await self.verify_task(http_client, task['id'], endpoint='complete')

                        if result:
                            logger.success(f"{self.session_name} | Task <lc>{task['title']}</lc> completed! |"
                                           f" Reward: <e>+{task['rewardPoints']}</e> CATS")
                        else:
                            logger.info(f"{self.session_name} | Task <lc>{task['title']}</lc> not completed")

                        await asyncio.sleep(delay=randint(5, 10))

                    elif task['isPending']:
                        logger.info(f"{self.session_name} | Task <lc>{task['title']}</lc> is pending")

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when processing tasks: {error}")
            await asyncio.sleep(delay=3)

    async def verify_task(self, http_client: aiohttp.ClientSession, task_id: str, endpoint: str, retry=0):
        try:
            response = await http_client.post(f'https://api.catshouse.club/tasks'
                                              f'/{task_id}/{endpoint}', json={}, timeout=aiohttp.ClientTimeout(60))
            response.raise_for_status()
            response_json = await response.json()
            status = response_json.get('success', False) or response_json.get('completed', False)
            return status

        except Exception as e:
            if retry < 5:
                logger.warning(f"{self.session_name} | Can't verify task | Retry attempt: {retry}")
                await asyncio.sleep(delay=randint(5, 10))
                return await self.verify_task(http_client, task_id, endpoint, retry=retry+1)

            logger.error(f"{self.session_name} | Unknown error while verifying task {task_id} | Error: {e}")
            await asyncio.sleep(delay=3)

    async def get_avatar_info(self, http_client: aiohttp.ClientSession, retry=0):
        try:
            response = await http_client.get('https://api.catshouse.club/user/avatar')
            response.raise_for_status()
            response_bytes = await response.read()
            response_text = brotli.decompress(response_bytes)
            response_json = json.loads(response_text.decode('utf-8'))
            return response_json

        except Exception as e:
            if retry < 5:
                logger.warning(f"{self.session_name} | Can't getting avatar info | Retry attempt: {retry}")
                await asyncio.sleep(delay=randint(5, 10))
                return await self.get_avatar_info(http_client, retry=retry+1)

            logger.error(f"{self.session_name} | Unknown error while getting avatar info | Error: {e}")
            await asyncio.sleep(delay=3)

    async def check_available(self, http_client: aiohttp.ClientSession, retry=0):
        try:
            response = await http_client.get('https://api.catshouse.club/exchange-claim/check-available')
            response.raise_for_status()
            response_bytes = await response.read()
            response_text = brotli.decompress(response_bytes)
            response_json = json.loads(response_text.decode('utf-8'))
            return response_json

        except Exception as e:
            if retry < 5:
                logger.warning(f"{self.session_name} | Can't getting airdrop data | Retry attempt: {retry}")
                await asyncio.sleep(delay=randint(5, 10))
                return await self.check_available(http_client, retry=retry+1)

            logger.error(f"{self.session_name} | Unknown error while getting airdrop data | Error: {e}")
            await asyncio.sleep(delay=3)

    def generate_random_string(self, length=8):
        characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
        random_string = ''
        for _ in range(length):
            random_index = int((len(characters) * int.from_bytes(os.urandom(1), 'big')) / 256)
            random_string += characters[random_index]
        return random_string

    async def processing_avatar_task(self, http_client: aiohttp.ClientSession, retry=0):
        try:
            cat_image = await get_random_cat_image(session_name=self.session_name)
            hash_id = self.generate_random_string(length=16)
            http_client.headers['Content-Type'] = f'multipart/form-data; boundary=----WebKitFormBoundary{hash_id}'
            data = (f'------WebKitFormBoundary{hash_id}\r\n'.encode('utf-8') + cat_image +
                    f'\r\n------WebKitFormBoundary{hash_id}--\r\n'.encode('utf-8'))
            response = await http_client.post('https://api.catshouse.club/user/avatar/upgrade',
                                              data=data)
            http_client.headers['Content-Type'] = headers['Content-Type']
            response.raise_for_status()
            response_bytes = await response.read()
            response_text = brotli.decompress(response_bytes)
            response_json = json.loads(response_text.decode('utf-8'))
            logger.info(
                f"{self.session_name} | Avatar task completed! | Reward: <e>+{response_json['rewards']}</e> CATS")
            return response_json

        except Exception as e:
            if retry < 5:
                logger.warning(f"{self.session_name} | Can't processing avatar task | Retry attempt: {retry}")
                await asyncio.sleep(delay=randint(5, 10))
                return await self.processing_avatar_task(http_client, retry=retry+1)

            logger.error(f"{self.session_name} | Unknown error while processing avatar task | Error: {e}")
            await asyncio.sleep(delay=3)

    async def get_user_exchange(self, http_client: aiohttp.ClientSession, retry=0):
        try:
            response = await http_client.get('https://api.catshouse.club/exchange-claim/user-request')
            if response.content_length == 0:
                logger.info(f"{self.session_name} | User has not linked a wallet")
                return
            response.raise_for_status()
            response_bytes = await response.read()
            response_text = brotli.decompress(response_bytes)
            response_json = json.loads(response_text.decode('utf-8'))
            return response_json

        except Exception as e:
            if retry < 3:
                logger.warning(f"{self.session_name} | Can't getting exchange data | Retry attempt: {retry}")
                await asyncio.sleep(delay=randint(5, 10))
                return await self.get_user_exchange(http_client, retry=retry + 1)

            logger.error(f"{self.session_name} | Unknown error while getting exchange data | Error: {e}")
            await asyncio.sleep(delay=3)

    async def run(self, user_agent: str, proxy: str | None) -> None:
        access_token_created_time = 0
        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None
        headers["User-Agent"] = user_agent

        async with aiohttp.ClientSession(headers=headers, connector=proxy_conn, trust_env=True, auto_decompress=False) as http_client:
            if proxy:
                await self.check_proxy(http_client=http_client, proxy=proxy)

            token_live_time = randint(3500, 3600)
            while True:
                try:
                    sleep_time = randint(settings.SLEEP_TIME[0], settings.SLEEP_TIME[1])
                    if time() - access_token_created_time >= token_live_time:
                        tg_web_data = await self.tg_session.get_tg_web_data()
                        if tg_web_data is None:
                            continue

                        http_client.headers["Authorization"] = "tma " + tg_web_data
                        user_info = await self.login(http_client=http_client)
                        if user_info is None:
                            token_live_time = 0
                            await asyncio.sleep(randint(1000, 1800))
                            continue

                        access_token_created_time = time()
                        token_live_time = randint(3500, 3600)

                        balance = user_info['totalRewards']
                        logger.info(f"{self.session_name} | Balance: <e>{balance}</e> CATS")
                        result = await self.check_available(http_client=http_client)
                        if result:
                            logger.info(f'{self.session_name} '
                                        f'| Has free pass: <lc>{result.get("hasFreePass")}</lc> '
                                        f'| Has OG pass: <lc>{result.get("hasOgPass")}</lc> '
                                        f'| Has transaction: <lc>{result.get("hasTransaction")}</lc> '
                                        f'| Is available for Airdrop: <e>{result.get("isAvailable")}</e>')

                        exchange = await self.get_user_exchange(http_client=http_client)
                        if exchange:
                            logger.info(f"{self.session_name} | "
                                        f"Exchange: {exchange['exchange']} | Address: <y>{exchange['address']}</y>")

                        if settings.AUTO_TASK:
                            await asyncio.sleep(delay=randint(5, 10))
                            await self.processing_tasks(http_client=http_client)

                    if settings.AVATAR_TASK:
                        avatar_info = await self.get_avatar_info(http_client=http_client)
                        og_pass = user_info.get('hasOgPass', False)
                        logger.info(f"{self.session_name} | OG Pass: <y>{og_pass}</y>")
                        if avatar_info:
                            attempt_time = None
                            if avatar_info['attemptTime'] is not None:
                                attempt_time = avatar_info['attemptTime']
                                parsed_time = datetime.strptime(attempt_time, '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()
                                delta_time = datetime.utcnow().timestamp() - parsed_time
                                next_attempt_time = delta_time - timedelta(hours=24).total_seconds()
                                max_attempts = 3 if og_pass else 1
                                used_attempts = avatar_info['attemptsUsed'] if next_attempt_time < 0 else 0
                            if attempt_time is None or used_attempts < max_attempts:
                                for attempt in range(max_attempts - used_attempts):
                                    await asyncio.sleep(delay=randint(5, 10))
                                    await self.processing_avatar_task(http_client=http_client)

                            elif next_attempt_time < 0:
                                sleep_time = min(sleep_time, abs(int(next_attempt_time)))

                    logger.info(f"{self.session_name} | Sleep <y>{round(sleep_time / 60, 1)}</y> min")
                    await asyncio.sleep(delay=sleep_time)

                except InvalidSession as error:
                    raise error

                except Exception as error:
                    logger.error(f"{self.session_name} | Unknown error: {error}")
                    await asyncio.sleep(delay=randint(60, 120))


async def run_tapper(tg_session: TGSession, user_agent: str, proxy: str | None):
    try:
        await Tapper(tg_session=tg_session).run(user_agent=user_agent, proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_session.session_name} | Invalid Session")
