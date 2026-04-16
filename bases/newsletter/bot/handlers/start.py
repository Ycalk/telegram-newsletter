from typing import Final

import structlog
from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    URLInputFile,
)
from dishka import FromDishka
from jinja2 import Environment
from newsletter.api_client import IAPIClient
from newsletter.channel_id_encryption import IChannelIdEncryption
from newsletter.database import (
    ChannelDAO,
    NewsletterSubscriptionDAO,
    TelegramUserDAO,
)
from opentelemetry import trace

router = Router(name="start")
logger: Final[structlog.BoundLogger] = structlog.get_logger("bot.start")
tracer: Final[trace.Tracer] = trace.get_tracer("bot.start")


@router.message(CommandStart())
async def start_command(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    encryption: FromDishka[IChannelIdEncryption],
    api_client: FromDishka[IAPIClient],
    jinja2_env: FromDishka[Environment],
    telegram_user_dao: FromDishka[TelegramUserDAO],
    newsletter_subscription_dao: FromDishka[NewsletterSubscriptionDAO],
    channel_dao: FromDishka[ChannelDAO],
):
    if message.from_user is None:
        return
    await state.clear()

    with tracer.start_as_current_span("bot.start") as span:
        span.set_attribute("user_id", message.from_user.id)
        span.set_attribute("username", message.from_user.username or "none")
        span.set_attribute("first_name", message.from_user.first_name)
        span.set_attribute("last_name", message.from_user.last_name or "none")

        request_logger = logger.bind(
            user_id=message.from_user.id,
            username=message.from_user.username or "none",
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name or "none",
        )
        request_logger.info("start_command")
        welcome_template = jinja2_env.get_template("welcome.html")

        reply_keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⚙️ Управление подписками")]],
            resize_keyboard=True,
        )

        telegram_user = await telegram_user_dao.find_by_telegram_id_with_loaded_user(
            message.from_user.id
        )

        if telegram_user is None:
            request_logger.info("telegram_user_not_found")
            await message.answer(
                welcome_template.render(user_email=None, subscribed_channels=None),
                reply_markup=reply_keyboard,
            )
        else:
            request_logger = request_logger.bind(user_id=str(telegram_user.user_id))
            request_logger.info("telegram_user_found")
            span.set_attribute("user_id", str(telegram_user.user_id))
            subscriptions = (
                await newsletter_subscription_dao.find_by_user_id_with_loaded_user(
                    telegram_user.user_id
                )
            )

            await message.answer(
                welcome_template.render(
                    user_email=telegram_user.user.email,
                    subscribed_channels=[
                        subscription.channel.name for subscription in subscriptions
                    ],
                ),
                reply_markup=reply_keyboard,
            )

        if not command.args:
            if telegram_user is None:
                request_logger.info("no_args")
                span.set_attribute("args", "none")
                no_subscription_template = jinja2_env.get_template(
                    "no_channel_subscription.html"
                )
                await message.answer(no_subscription_template.render())
            return

        span.set_attribute("args", command.args)
        channel_id = encryption.decrypt(command.args)
        request_logger = request_logger.bind(channel_id=channel_id)
        request_logger.info("channel_id_decrypted")

        channel = await channel_dao.find_by_id_with_loaded_logo(channel_id)
        if channel is None:
            request_logger.info("channel_not_found")
            raise ValueError("Channel not found")

        request_logger.info("channel_found")
        span.set_attribute("channel_id", channel_id)
        span.set_attribute("channel_name", channel.name)

        channel_template = jinja2_env.get_template("channel.html")
        text = channel_template.render(
            channel_name=channel.name, channel_description=channel.description
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Подписаться на рассылку",
                        callback_data=f"subscribe:{channel_id}",
                    )
                ]
            ]
        )

        if channel.logo is not None:
            image_url = api_client.get_media_url(channel.logo.file_name)
            request_logger.info("got_logo_url", channel_logo=image_url)
            span.set_attribute("channel_logo", image_url)
            await message.answer_photo(
                photo=URLInputFile(image_url),
                caption=text,
                reply_markup=keyboard,
            )
        else:
            await message.answer(
                text=text,
                reply_markup=keyboard,
            )
