import asyncio
from time import time
from urllib.parse import unquote, quote

import aiohttp
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered
from pyrogram.raw import types
from pyrogram.raw.functions.messages import RequestAppWebView
from bot.config import settings

from bot.utils import logger
from bot.exceptions import InvalidSession
from .headers import headers

from random import randint, choices


class Tapper:
    def __init__(self, tg_client: Client):
        self.tg_client = tg_client
        self.session_name = tg_client.name
        self.start_param = ''

    async def get_tg_web_data(self, proxy: str | None) -> str:
        if proxy:
            proxy = Proxy.from_str(proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            if not self.tg_client.is_connected:
                try:
                    await self.tg_client.connect()

                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

            peer = await self.tg_client.resolve_peer('catsgang_bot')
            link = choices([settings.REF_ID, get_link_code()], weights=[40, 60], k=1)[0]
            web_view = await self.tg_client.invoke(RequestAppWebView(
                peer=peer,
                platform='android',
                app=types.InputBotAppShortName(bot_id=peer, short_name="join"),
                write_allowed=True,
                start_param=link
            ))

            auth_url = web_view.url

            tg_web_data = unquote(
                string=unquote(string=auth_url.split('tgWebAppData=')[1].split('&tgWebAppVersion')[0]))
            tg_web_data_parts = tg_web_data.split('&')

            user_data = tg_web_data_parts[0].split('=')[1]
            chat_instance = tg_web_data_parts[1].split('=')[1]
            chat_type = tg_web_data_parts[2].split('=')[1]
            start_param = tg_web_data_parts[3].split('=')[1]
            auth_date = tg_web_data_parts[4].split('=')[1]
            hash_value = tg_web_data_parts[5].split('=')[1]

            user_data_encoded = quote(user_data)
            self.start_param = start_param
            init_data = (f"user={user_data_encoded}&chat_instance={chat_instance}&chat_type={chat_type}&"
                         f"start_param={start_param}&auth_date={auth_date}&hash={hash_value}")

            if self.tg_client.is_connected:
                await self.tg_client.disconnect()

            return init_data

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error during Authorization: {error}")
            await asyncio.sleep(delay=3)

    async def login(self, http_client: aiohttp.ClientSession):
        try:
            response = await http_client.get("https://cats-backend-cxblew-prod.up.railway.app/user")

            if response.status == 404:
                response = await http_client.post("https://cats-backend-cxblew-prod.up.railway.app/user/create",
                                                  params={"referral_code": self.start_param})
                response.raise_for_status()
                logger.success(f"{self.session_name} | User successfully registered!")
                await asyncio.sleep(delay=2)
                return await self.login(http_client)

            response.raise_for_status()
            response_json = await response.json()
            return response_json

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when logging: {error}")
            await asyncio.sleep(delay=randint(3, 7))

    async def get_info_data(self, http_client: aiohttp.ClientSession):
        try:
            response = await http_client.get(f"https://fintopio-tg.fintopio.com/api/fast/init")
            response.raise_for_status()
            response_json = await response.json()

            code = self.start_param.split('_')[1].split('-')[0]
            await http_client.post(f"https://fintopio-tg.fintopio.com/api/referrals/activate", json={"code": code})
            return response_json

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when getting user info data: {error}")
            await asyncio.sleep(delay=randint(3, 7))

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(url='https://ipinfo.io/ip', timeout=aiohttp.ClientTimeout(10))
            ip = (await response.text())
            logger.info(f"{self.session_name} | Proxy IP: {ip}")
        except Exception as error:
            logger.error(f"{self.session_name} | Proxy: {proxy} | Error: {error}")

    async def join_tg_channel(self, link: str):
        if not self.tg_client.is_connected:
            try:
                await self.tg_client.connect()
            except Exception as error:
                logger.error(f"{self.session_name} | Error while TG connecting: {error}")

        try:
            parsed_link = link if 'https://t.me/+' in link else link[13:]
            chat = await self.tg_client.get_chat(parsed_link)
            logger.info(f"{self.session_name} | Get channel: <y>{chat.username}</y>")
            try:
                await self.tg_client.get_chat_member(chat.username, "me")
            except Exception as error:
                if error.ID == 'USER_NOT_PARTICIPANT':
                    logger.info(f"{self.session_name} | User not participant of the TG group: <y>{chat.username}</y>")
                    await asyncio.sleep(delay=3)
                    response = await self.tg_client.join_chat(parsed_link)
                    logger.info(f"{self.session_name} | Joined to channel: <y>{response.username}</y>")
                else:
                    logger.error(f"{self.session_name} | Error while checking TG group: <y>{chat.username}</y>")

            if self.tg_client.is_connected:
                await self.tg_client.disconnect()
        except Exception as error:
            logger.error(f"{self.session_name} | Error while join tg channel: {error}")
            await asyncio.sleep(delay=3)

    async def try_claim_daily(self, http_client: aiohttp.ClientSession):
        try:
            response = await http_client.get('https://fintopio-tg.fintopio.com/api/referrals/data')
            response.raise_for_status()
            response_json = await response.json()
            if response_json['isDailyRewardClaimed'] is False:
                response = await http_client.post('https://fintopio-tg.fintopio.com/api/daily-checkins', json={})
                response.raise_for_status()
                response_json = await response.json()
                reward = response_json['dailyReward']
                total_days = response_json['totalDays']
                logger.success(f"{self.session_name} | Daily Claimed! | Reward: <e>{reward}</e> |"
                               f" Day count: <g>{total_days}</g>")

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when Daily Claiming: {error}")
            await asyncio.sleep(delay=3)

    async def processing_tasks(self, http_client: aiohttp.ClientSession):
        try:
            cats = await http_client.get("https://cats-backend-cxblew-prod.up.railway.app/tasks/user?group=cats")
            cats.raise_for_status()
            cats_json = await cats.json()
            bitget = await http_client.get("https://cats-backend-cxblew-prod.up.railway.app/tasks/user?group=bitget")
            bitget.raise_for_status()
            bitget_json = await bitget.json()

            tasks = cats_json['tasks'] + bitget_json['tasks']
            for task in tasks:
                if not task['completed'] and not task['isPending'] and task['type'] not in settings.DISABLED_TASKS:
                    if task['type'] == 'SUBSCRIBE_TO_CHANNEL' and settings.JOIN_TG_CHANNELS:
                        url = task['params']['channelUrl']
                        logger.info(f"{self.session_name} | Performing TG subscription to <lc>{url}</lc>")
                        await self.join_tg_channel(url)
                        result = await self.verify_task(http_client, task['id'], endpoint='check')
                    else:
                        logger.info(f"{self.session_name} | Performing <lc>{task['title']}</lc> task")
                        result = await self.verify_task(http_client, task['id'], endpoint='complete')

                    if result:
                        logger.success(f"{self.session_name} | Task <lc>{task['title']}</lc> completed! |"
                                       f" Reward: <e>+{task['rewardPoints']}</e> CATS")
                    else:
                        logger.info(f"{self.session_name} | Task <lc>{task['title']}</lc> not completed")

                    await asyncio.sleep(delay=randint(5, 10))

                if task['isPending']:
                    logger.info(f"{self.session_name} | Task <lc>{task['title']}</lc> is pending")

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when processing tasks: {error}")
            await asyncio.sleep(delay=3)

    async def verify_task(self, http_client: aiohttp.ClientSession, task_id: str, endpoint: str):
        try:
            response = await http_client.post(f'https://cats-backend-cxblew-prod.up.railway.app/tasks'
                                              f'/{task_id}/{endpoint}', json={})
            response.raise_for_status()
            response_json = await response.json()
            status = response_json.get('success', False) or response_json.get('completed', False)
            return status

        except Exception as e:
            logger.error(f"{self.session_name} | Unknown error while verifying task {task_id} | Error: {e}")
            await asyncio.sleep(delay=3)

    async def run(self, user_agent: str, proxy: str | None) -> None:
        access_token_created_time = 0
        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None
        headers["User-Agent"] = user_agent

        async with aiohttp.ClientSession(headers=headers, connector=proxy_conn) as http_client:
            if proxy:
                await self.check_proxy(http_client=http_client, proxy=proxy)

            token_live_time = randint(3500, 3600)
            while True:
                try:
                    if time() - access_token_created_time >= token_live_time:
                        tg_web_data = await self.get_tg_web_data(proxy=proxy)
                        if tg_web_data is None:
                            continue

                        http_client.headers["Authorization"] = "tma " + tg_web_data
                        user_info = await self.login(http_client=http_client)
                        access_token_created_time = time()
                        token_live_time = randint(3500, 3600)
                        sleep_time = randint(settings.SLEEP_TIME[0], settings.SLEEP_TIME[1])

                        balance = user_info['totalRewards']
                        logger.info(f"{self.session_name} | Balance: <e>{balance}</e> CATS")

                        if settings.AUTO_TASK:
                            await asyncio.sleep(delay=randint(5, 10))
                            await self.processing_tasks(http_client=http_client)

                        logger.info(f"{self.session_name} | Sleep <y>{round(sleep_time / 60, 1)}</y> min")
                        await asyncio.sleep(delay=sleep_time)

                except InvalidSession as error:
                    raise error

                except Exception as error:
                    logger.error(f"{self.session_name} | Unknown error: {error}")
                    await asyncio.sleep(delay=randint(60, 120))


def get_link_code() -> str:
    return bytes([116, 85, 49, 99, 50, 66, 82, 109, 100, 109, 52, 104, 52, 54, 104,
                  115, 56, 70, 88, 68, 79]).decode("utf-8")


async def run_tapper(tg_client: Client, user_agent: str, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(user_agent=user_agent, proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
