import asyncio

from dishka import make_async_container
from newsletter.channel_id_encryption import (
    ChannelIdEncryptionProvider,
    IChannelIdEncryption,
)


async def main():
    container = make_async_container(ChannelIdEncryptionProvider())
    encryptor = await container.get(IChannelIdEncryption)
    s = encryptor.encrypt(1111641330)
    print(s)
    print(encryptor.decrypt(s))


def run():
    asyncio.run(main())
