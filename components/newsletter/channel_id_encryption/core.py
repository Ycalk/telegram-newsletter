from typing import Protocol, override

from dishka import Provider, Scope, provide
from dishka.dependency_source import CompositeDependencySource
from hashids import Hashids

from .settings import ChannelIdEncryptionSettings


class IChannelIdEncryption(Protocol):
    def encrypt(self, channel_id: int) -> str: ...

    def decrypt(self, encrypted_channel_id: str) -> int: ...


class ChannelIdEncryption(IChannelIdEncryption):
    def __init__(self, settings: ChannelIdEncryptionSettings):
        self.hashids: Hashids = Hashids(salt=settings.channel_id_encryption_key)

    @override
    def encrypt(self, channel_id: int) -> str:
        return self.hashids.encode(channel_id)

    @override
    def decrypt(self, encrypted_channel_id: str) -> int:
        decoded_data = self.hashids.decode(encrypted_channel_id)
        if not decoded_data:
            raise ValueError("Invalid encrypted channel ID")
        return decoded_data[0]


class ChannelIdEncryptionProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> ChannelIdEncryptionSettings:
        return ChannelIdEncryptionSettings()  # type: ignore # pyright: ignore

    channel_id_encryption: CompositeDependencySource = provide(
        ChannelIdEncryption, provides=IChannelIdEncryption, scope=Scope.APP
    )
