import asyncio
import secrets
from typing import Final

import structlog
from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    URLInputFile,
)
from dishka import FromDishka
from email_validator import validate_email
from jinja2 import Environment
from newsletter.api_client import GetChannel, IAPIClient
from newsletter.channel_id_encryption import IChannelIdEncryption
from newsletter.database import (
    NewsletterSubscriptionDAO,
    TelegramUserDAO,
    UserDAO,
)
from newsletter.dto import Channel
from newsletter.email_sender import IEmailSender
from opentelemetry import trace

from .settings import BotSettings

router = Router(name="main")
logger: Final[structlog.BoundLogger] = structlog.get_logger("bot.main")
tracer: Final[trace.Tracer] = trace.get_tracer("bot.main")


class SubscriptionStates(StatesGroup):
    waiting_for_email: State = State()
    waiting_for_code: State = State()


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

        telegram_user = await telegram_user_dao.find_by_telegram_id_with_loaded_user(
            message.from_user.id
        )
        if telegram_user is None:
            request_logger.info("telegram_user_not_found")
            await message.answer(
                welcome_template.render(user_email=None, subscribed_channels=None)
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
            channels = await asyncio.gather(
                *[
                    api_client(GetChannel(channel_id=sub.channel_id))
                    for sub in subscriptions
                ],
                return_exceptions=True,
            )

            await message.answer(
                welcome_template.render(
                    user_email=telegram_user.user.email,
                    subscribed_channels=[
                        channel.name
                        for channel in channels
                        if isinstance(channel, Channel)
                    ],
                )
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

        channel = await api_client(GetChannel(channel_id=channel_id))
        request_logger = request_logger.bind(channel=channel)
        request_logger.info("channel_found")
        span.set_attribute("channel_id", channel_id)
        span.set_attribute("channel_name", channel.name)

        channel_template = jinja2_env.get_template("channel.html")
        text = channel_template.render(channel=channel)
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


@router.callback_query(F.data.startswith("subscribe:"))
async def subscribe_callback(
    callback: CallbackQuery,
    state: FSMContext,
    api_client: FromDishka[IAPIClient],
    jinja2_env: FromDishka[Environment],
    telegram_user_dao: FromDishka[TelegramUserDAO],
    newsletter_subscription_dao: FromDishka[NewsletterSubscriptionDAO],
):
    if callback.message is None or callback.data is None:
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)

    channel_id = int(callback.data.split(":", 1)[1])

    with tracer.start_as_current_span("bot.subscribe") as span:
        span.set_attribute("channel_id", channel_id)
        span.set_attribute("telegram_id", callback.from_user.id)

        request_logger = logger.bind(
            channel_id=channel_id,
            telegram_id=callback.from_user.id,
        )
        request_logger.info("subscribe_callback")

        telegram_user = await telegram_user_dao.find_by_telegram_id_with_loaded_user(
            callback.from_user.id
        )

        if telegram_user is not None:
            request_logger.info("user_already_registered")
            await newsletter_subscription_dao.create(
                user_id=telegram_user.user_id,
                channel_id=channel_id,
            )
            await newsletter_subscription_dao.commit()

            channel = await api_client(GetChannel(channel_id=channel_id))
            success_template = jinja2_env.get_template("subscription_success.html")
            await callback.message.answer(
                success_template.render(
                    channel_name=channel.name,
                    email=telegram_user.user.email,
                )
            )
            return

        request_logger.info("user_not_registered_starting_fsm")
        await state.update_data(channel_id=channel_id)
        await state.set_state(SubscriptionStates.waiting_for_email)

        ask_email_template = jinja2_env.get_template("ask_email.html")
        await callback.message.answer(ask_email_template.render())


@router.message(SubscriptionStates.waiting_for_email)
async def process_email(
    message: Message,
    state: FSMContext,
    jinja2_env: FromDishka[Environment],
    email_sender: FromDishka[IEmailSender],
    bot_settings: FromDishka[BotSettings],
):
    if message.from_user is None or message.text is None:
        return

    email_info = validate_email(message.text.strip())
    email = email_info.normalized

    with tracer.start_as_current_span("bot.process_email") as span:
        span.set_attribute("telegram_id", message.from_user.id)

        request_logger = logger.bind(
            telegram_id=message.from_user.id,
            email=email,
        )
        request_logger.info("email_validated")

        span.set_attribute("email", email)

        code = "".join(
            [
                str(secrets.randbelow(10))
                for _ in range(bot_settings.confirmation_code_length)
            ]
        )
        await state.update_data(email=email, confirmation_code=code)

        confirmation_template = jinja2_env.get_template("confirmation_email.html")
        await email_sender(
            to_emails=[email],
            subject="Код подтверждения — Telegram рассылка",
            html_content=confirmation_template.render(code=code),
            subscription_id=None,
        )
        request_logger.info("confirmation_email_sent")

        await state.set_state(SubscriptionStates.waiting_for_code)

        code_sent_template = jinja2_env.get_template("code_sent.html")
        await message.answer(code_sent_template.render(email=email))


@router.message(SubscriptionStates.waiting_for_code)
async def process_confirmation_code(
    message: Message,
    state: FSMContext,
    api_client: FromDishka[IAPIClient],
    jinja2_env: FromDishka[Environment],
    user_dao: FromDishka[UserDAO],
    telegram_user_dao: FromDishka[TelegramUserDAO],
    newsletter_subscription_dao: FromDishka[NewsletterSubscriptionDAO],
):
    if message.from_user is None or message.text is None:
        return

    entered_code = message.text.strip()
    data = await state.get_data()
    expected_code: str = data["confirmation_code"]
    email: str = data["email"]
    channel_id: int = data["channel_id"]

    with tracer.start_as_current_span("bot.process_confirmation_code") as span:
        span.set_attribute("telegram_id", message.from_user.id)
        span.set_attribute("channel_id", channel_id)

        request_logger = logger.bind(
            telegram_id=message.from_user.id,
            channel_id=channel_id,
            email=email,
        )

        if entered_code != expected_code:
            request_logger.info("invalid_code")
            invalid_code_template = jinja2_env.get_template("invalid_code.html")
            await message.answer(invalid_code_template.render())
            return

        request_logger.info("code_confirmed")
        span.set_attribute("email", email)

        user = await user_dao.create(email=email)
        await telegram_user_dao.create(
            user_id=user.id,
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            username=message.from_user.username,
        )
        await newsletter_subscription_dao.create(
            user_id=user.id,
            channel_id=channel_id,
        )
        await newsletter_subscription_dao.commit()

        request_logger.info("user_created_and_subscribed")
        await state.clear()

        channel = await api_client(GetChannel(channel_id=channel_id))
        success_template = jinja2_env.get_template("registration_success.html")
        await message.answer(
            success_template.render(
                email=email,
                channel_name=channel.name,
            )
        )
