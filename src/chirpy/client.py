import aiohttp
import asyncio

import json
import sys

from typing import AsyncGenerator, Optional

from chirpy.types import UserId, SessionId

host = "localhost"
port = "8000"
url = f"http://{host}:{port}"


class ChatApiClient:
    def __init__(self, base_url: str):
        self.url = base_url
        self.token = None
        self.headers: dict[str, str] = {}
        self.dest: Optional[str] = None

    async def login(self, username: str, secret: str) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{url}/token",
                data={
                    "grant_type": "password",
                    "username": username,
                    "password": secret,
                    "scope": None,
                    "client_id": None,
                    "client_secret": None,
                },
            ) as resp:
                payload = await resp.json()
                self.token = payload.get("access_token")

        self.headers = {"Authorization": f"Bearer {self.token}"}

    async def guest_login(self) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{url}/guest-token",
            ) as resp:
                payload = await resp.json()
                self.token = payload.get("access_token")

        self.headers = {"Authorization": f"Bearer {self.token}"}

    async def invite(self, dest: SessionId, user_id: UserId) -> None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{url}/chat/{dest}/invite",
                    headers=self.headers,
                    json={"user_id": user_id},
                    raise_for_status=True,
                ) as resp:
                    return await resp.json()
        except (
            asyncio.exceptions.TimeoutError,
            aiohttp.client_exceptions.ServerDisconnectedError,
            aiohttp.client_exceptions.ClientConnectorError,
            aiohttp.client_exceptions.ClientResponseError,
            ConnectionResetError,
            ConnectionAbortedError,
        ) as e:
            print(e)

    async def me(self) -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/chat/me", headers=self.headers) as resp:
                    return await resp.json()
        except (
            asyncio.exceptions.TimeoutError,
            aiohttp.client_exceptions.ServerDisconnectedError,
            aiohttp.client_exceptions.ClientConnectorError,
            aiohttp.client_exceptions.ClientResponseError,
            ConnectionResetError,
            ConnectionAbortedError,
        ) as e:
            print(e)

    async def sessions(self) -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/chat/me/sessions", headers=self.headers) as resp:
                    return await resp.json()
        except (
            asyncio.exceptions.TimeoutError,
            aiohttp.client_exceptions.ServerDisconnectedError,
            aiohttp.client_exceptions.ClientConnectorError,
            aiohttp.client_exceptions.ClientResponseError,
            ConnectionResetError,
            ConnectionAbortedError,
        ) as e:
            print(e)

    async def chat_session(self) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{url}/chat", headers=self.headers) as resp:
                return await resp.json()

    async def post(self, dest: SessionId, message: str) -> None:
        try:
            assert dest is not None
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{url}/chat/{dest}/post",
                    headers=self.headers,
                    json={"content": message},
                    raise_for_status=True,
                ) as resp:
                    ...
        except (
            asyncio.exceptions.TimeoutError,
            aiohttp.client_exceptions.ServerDisconnectedError,
            aiohttp.client_exceptions.ClientConnectorError,
            aiohttp.client_exceptions.ClientResponseError,
            ConnectionResetError,
            ConnectionAbortedError,
        ) as e:
            print(e)

    async def listen(self) -> AsyncGenerator[dict, None]:
        headers = self.headers
        # headers["Content-Type"] = "text/event-stream"
        headers["Cache-Control"] = "no-cache"
        headers["Connection"] = "keep-alive"
        headers["X-Accel-Buffering"] = "no"

        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{url}/chat/listen", headers=headers, raise_for_status=True
                    ) as resp:
                        async for line in resp.content:
                            event_payload = json.loads(line)
                            yield event_payload
            except (
                asyncio.exceptions.TimeoutError,
                aiohttp.client_exceptions.ServerDisconnectedError,
                aiohttp.client_exceptions.ClientConnectorError,
                aiohttp.client_exceptions.ClientResponseError,
                ConnectionResetError,
                ConnectionAbortedError,
            ) as e:
                print("Connection down. Retrying!")
                await asyncio.sleep(1.0)


async def listen_loop(client: ChatApiClient) -> None:
    async for event in client.listen():
        session = event["session"]
        client.dest = session
        source = event["origin"]["username"]
        message = event["message"]
        print(f"{source}#{session} >> {message.strip()}")


async def post_loop(client: ChatApiClient) -> None:
    async def ainput(string: str) -> str:
        await asyncio.get_event_loop().run_in_executor(
            None, lambda s=string: sys.stdout.write(s + "")
        )
        return await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)

    while True:
        message = (await ainput("")).strip()
        if message.startswith("/"):
            client.dest = message[1:]
            if not client.dest:
                session = await client.chat_session()
                client.dest = session["id"]
            print(f"Sending to session {client.dest}")
            continue

        await client.post(client.dest, message)


async def run() -> None:
    client = ChatApiClient(url)
    if sys.argv[1] == "guest":
        await client.guest_login()
    else:
        await client.login(sys.argv[1], sys.argv[1])
    t = asyncio.create_task(listen_loop(client))
    p = asyncio.create_task(post_loop(client))
    await asyncio.gather(t, p)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
