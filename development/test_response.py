import asyncio

from dishka import make_async_container
from newsletter.api_client import APIClientProvider, GetChannelIds, IAPIClient


async def main():
    container = make_async_container(APIClientProvider())
    async with container() as request_container:
        client = await request_container.get(IAPIClient)
        result = await client(GetChannelIds())
        print(result)


def run():
    asyncio.run(main())
