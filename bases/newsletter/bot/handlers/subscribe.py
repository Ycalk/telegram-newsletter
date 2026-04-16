import secrets
from typing import Final

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
)
from dishka import FromDishka
from email_validator import validate_email
from jinja2 import Environment
from newsletter.bot.settings import BotSettings
from newsletter.database import (
    ChannelDAO,
    NewsletterSubscriptionDAO,
    TelegramUserDAO,
    UserDAO,
)
from newsletter.email_sender import IEmailSender
from opentelemetry import trace

router = Router(name="subscribe")
logger: Final[structlog.BoundLogger] = structlog.get_logger("bot.subscribe")
tracer: Final[trace.Tracer] = trace.get_tracer("bot.subscribe")


class SubscriptionStates(StatesGroup):
    waiting_for_email: State = State()
    waiting_for_code: State = State()
    waiting_for_send_at: State = State()


@router.callback_query(F.data.startswith("subscribe:"))
async def subscribe_callback(
    callback: CallbackQuery,
    state: FSMContext,
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
            subscriptions = (
                await newsletter_subscription_dao.find_by_user_id_with_loaded_user(
                    telegram_user.user_id
                )
            )
            if any(sub.channel_id == channel_id for sub in subscriptions):
                request_logger.info("user_already_subscribed")
                await callback.answer(
                    "Вы уже подписаны на этот канал!", show_alert=True
                )
                return

            request_logger.info("user_already_registered_asking_time")
            await state.update_data(channel_id=channel_id)
            await state.set_state(SubscriptionStates.waiting_for_send_at)

            ask_time_template = jinja2_env.get_template("ask_send_at.html")
            await callback.message.answer(ask_time_template.render())
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
    jinja2_env: FromDishka[Environment],
    user_dao: FromDishka[UserDAO],
    telegram_user_dao: FromDishka[TelegramUserDAO],
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
        request_logger.info("user_created_asking_time")
        await telegram_user_dao.commit()

        await state.update_data(channel_id=channel_id)
        await state.set_state(SubscriptionStates.waiting_for_send_at)

        ask_time_template = jinja2_env.get_template("ask_send_at.html")
        await message.answer(ask_time_template.render())


@router.message(SubscriptionStates.waiting_for_send_at)
async def process_send_at(
    message: Message,
    state: FSMContext,
    jinja2_env: FromDishka[Environment],
    newsletter_subscription_dao: FromDishka[NewsletterSubscriptionDAO],
    channel_dao: FromDishka[ChannelDAO],
    telegram_user_dao: FromDishka[TelegramUserDAO],
):
    if message.from_user is None or message.text is None:
        return

    text = message.text.strip()
    if not text.isdigit():
        invalid_time_template = jinja2_env.get_template("invalid_time.html")
        await message.answer(invalid_time_template.render())
        return

    hour = int(text)
    if not 0 <= hour <= 23:
        invalid_time_template = jinja2_env.get_template("invalid_time.html")
        await message.answer(invalid_time_template.render())
        return

    data = await state.get_data()
    channel_id: int = data["channel_id"]

    telegram_user = await telegram_user_dao.find_by_telegram_id_with_loaded_user(
        message.from_user.id
    )
    if telegram_user is None:
        raise ValueError("Telegram user not found")

    with tracer.start_as_current_span("bot.process_send_at") as span:
        span.set_attribute("telegram_id", message.from_user.id)
        span.set_attribute("channel_id", channel_id)
        span.set_attribute("send_at", hour)

        request_logger = logger.bind(
            telegram_id=message.from_user.id,
            channel_id=channel_id,
            send_at=hour,
        )

        subscriptions = (
            await newsletter_subscription_dao.find_by_user_id_with_loaded_user(
                telegram_user.user_id, skip_unsubscribe=False
            )
        )
        existing_sub = next(
            (sub for sub in subscriptions if sub.channel_id == channel_id), None
        )

        if existing_sub is not None:
            existing_sub.unsubscribed_at = None
            existing_sub.send_at = hour
        else:
            await newsletter_subscription_dao.create(
                user_id=telegram_user.user_id,
                channel_id=channel_id,
                send_at=hour,
            )

        request_logger.info("subscription_created")

        await state.clear()
        await newsletter_subscription_dao.commit()

        channel = await channel_dao.find_by_id(channel_id)
        if channel is None:
            raise ValueError("Channel not found")

        success_template = jinja2_env.get_template("subscription_success.html")
        await message.answer(
            success_template.render(
                email=telegram_user.user.email,
                channel_name=channel.name,
                send_at=hour,
            )
        )
