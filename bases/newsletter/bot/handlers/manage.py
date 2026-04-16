import secrets
from datetime import datetime, timezone
from typing import Final

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dishka import FromDishka
from email_validator import EmailNotValidError, validate_email
from jinja2 import Environment
from newsletter.bot.settings import BotSettings
from newsletter.database import (
    ChannelDAO,
    NewsletterSubscriptionDAO,
    TelegramUserDAO,
)
from newsletter.email_sender import IEmailSender
from opentelemetry import trace

router = Router(name="manage")
logger: Final[structlog.BoundLogger] = structlog.get_logger("bot.manage")
tracer: Final[trace.Tracer] = trace.get_tracer("bot.manage")

CHANNELS_PER_PAGE = 5


class ManageStates(StatesGroup):
    waiting_for_new_email: State = State()
    waiting_for_email_code: State = State()
    waiting_for_send_at: State = State()


def _build_channels_keyboard(
    channels: list[tuple[int, str]],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build inline keyboard with channel buttons and pagination."""
    start = page * CHANNELS_PER_PAGE
    end = start + CHANNELS_PER_PAGE
    page_channels = channels[start:end]

    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=name,
                callback_data=f"mgr_sub:{channel_id}",
            )
        ]
        for channel_id, name in page_channels
    ]

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"mgr_page:{page - 1}")
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(text="➡️", callback_data=f"mgr_page:{page + 1}")
        )
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="mgr_back")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(F.text == "⚙️ Управление подписками")
async def manage_subscriptions(
    message: Message,
    state: FSMContext,
    jinja2_env: FromDishka[Environment],
    telegram_user_dao: FromDishka[TelegramUserDAO],
    newsletter_subscription_dao: FromDishka[NewsletterSubscriptionDAO],
):
    if message.from_user is None:
        return
    await state.clear()

    with tracer.start_as_current_span("bot.manage_subscriptions") as span:
        span.set_attribute("telegram_id", message.from_user.id)

        telegram_user = await telegram_user_dao.find_by_telegram_id_with_loaded_user(
            message.from_user.id
        )
        if telegram_user is None:
            template = jinja2_env.get_template("manage_not_registered.html")
            await message.answer(template.render())
            return
        subscriptions = (
            await newsletter_subscription_dao.find_by_user_id_with_loaded_user(
                telegram_user.user_id
            )
        )

        keyboard = _build_manage_menu_keyboard(has_subscriptions=len(subscriptions) > 0)
        template = jinja2_env.get_template("manage_menu.html")
        await message.answer(
            template.render(
                email=telegram_user.user.email,
                subscriptions=[
                    {
                        "channel_name": sub.channel.name,
                        "send_at": sub.send_at,
                    }
                    for sub in subscriptions
                ],
            ),
            reply_markup=keyboard,
        )


def _build_manage_menu_keyboard(
    has_subscriptions: bool,
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="📢 Подписаться на канал",
                callback_data="mgr_new_sub",
            )
        ],
    ]
    if has_subscriptions:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🚫 Отписаться от канала",
                    callback_data="mgr_unsub",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(
                text="✏️ Изменить email",
                callback_data="mgr_edit_email",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "mgr_back")
async def back_to_menu(
    callback: CallbackQuery,
    state: FSMContext,
    jinja2_env: FromDishka[Environment],
    telegram_user_dao: FromDishka[TelegramUserDAO],
    newsletter_subscription_dao: FromDishka[NewsletterSubscriptionDAO],
):
    if callback.message is None:
        return
    await callback.answer()
    await state.clear()

    telegram_user = await telegram_user_dao.find_by_telegram_id_with_loaded_user(
        callback.from_user.id
    )
    if telegram_user is None:
        return
    subscriptions = await newsletter_subscription_dao.find_by_user_id_with_loaded_user(
        telegram_user.user_id
    )

    keyboard = _build_manage_menu_keyboard(has_subscriptions=len(subscriptions) > 0)
    template = jinja2_env.get_template("manage_menu.html")
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            template.render(
                email=telegram_user.user.email,
                subscriptions=[
                    {
                        "channel_name": sub.channel.name,
                        "send_at": sub.send_at,
                    }
                    for sub in subscriptions
                ],
            ),
            reply_markup=keyboard,
        )


@router.callback_query(F.data == "mgr_new_sub")
async def show_available_channels(
    callback: CallbackQuery,
    state: FSMContext,
    channel_dao: FromDishka[ChannelDAO],
    telegram_user_dao: FromDishka[TelegramUserDAO],
    newsletter_subscription_dao: FromDishka[NewsletterSubscriptionDAO],
):
    if callback.message is None:
        return
    await callback.answer()

    telegram_user = await telegram_user_dao.find_by_telegram_id_with_loaded_user(
        callback.from_user.id
    )
    if telegram_user is None:
        return
    subscriptions = await newsletter_subscription_dao.find_by_user_id_with_loaded_user(
        telegram_user.user_id
    )
    subscribed_ids = {sub.channel_id for sub in subscriptions}

    all_channels = await channel_dao.list_with_loaded_subscriptions_and_logo()
    available = [(ch.id, ch.name) for ch in all_channels if ch.id not in subscribed_ids]

    if not available:
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                "Вы уже подписаны на все доступные каналы! 🎉",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🔙 Назад", callback_data="mgr_back"
                            )
                        ]
                    ]
                ),
            )
        return

    await state.update_data(
        available_channels=available,
    )

    total_pages = (len(available) + CHANNELS_PER_PAGE - 1) // CHANNELS_PER_PAGE
    keyboard = _build_channels_keyboard(available, page=0, total_pages=total_pages)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "📢 Выберите канал, на который хотите подписаться:",
            reply_markup=keyboard,
        )


@router.callback_query(F.data.startswith("mgr_page:"))
async def paginate_channels(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.message is None or callback.data is None:
        return
    await callback.answer()

    page = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    available: list[tuple[int, str]] = data.get("available_channels", [])

    if not available:
        return

    total_pages = (len(available) + CHANNELS_PER_PAGE - 1) // CHANNELS_PER_PAGE
    keyboard = _build_channels_keyboard(available, page=page, total_pages=total_pages)
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=keyboard)


@router.callback_query(F.data.startswith("mgr_sub:"))
async def select_channel_to_subscribe(
    callback: CallbackQuery,
    state: FSMContext,
    jinja2_env: FromDishka[Environment],
):
    if callback.message is None or callback.data is None:
        return
    await callback.answer()

    channel_id = int(callback.data.split(":", 1)[1])
    await state.update_data(channel_id=channel_id)
    await state.set_state(ManageStates.waiting_for_send_at)

    template = jinja2_env.get_template("ask_send_at.html")
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            template.render(),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Отмена", callback_data="mgr_back")]
                ]
            ),
        )


@router.message(ManageStates.waiting_for_send_at)
async def process_manage_send_at(
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
    if not text.isdigit() or not 0 <= int(text) <= 23:
        invalid_template = jinja2_env.get_template("invalid_time.html")
        await message.answer(invalid_template.render())
        return

    hour = int(text)
    data = await state.get_data()
    channel_id: int = data["channel_id"]

    telegram_user = await telegram_user_dao.find_by_telegram_id_with_loaded_user(
        message.from_user.id
    )
    if telegram_user is None:
        raise ValueError("Telegram user not found")

    with tracer.start_as_current_span("bot.manage_send_at") as span:
        span.set_attribute("telegram_id", message.from_user.id)
        span.set_attribute("channel_id", channel_id)
        span.set_attribute("send_at", hour)

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


@router.callback_query(F.data == "mgr_unsub")
async def show_subscribed_channels(
    callback: CallbackQuery,
    telegram_user_dao: FromDishka[TelegramUserDAO],
    newsletter_subscription_dao: FromDishka[NewsletterSubscriptionDAO],
):
    if callback.message is None:
        return
    await callback.answer()

    telegram_user = await telegram_user_dao.find_by_telegram_id_with_loaded_user(
        callback.from_user.id
    )
    if telegram_user is None:
        return

    subscriptions = await newsletter_subscription_dao.find_by_user_id_with_loaded_user(
        telegram_user.user_id
    )

    if not subscriptions:
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                "У вас нет активных подписок.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🔙 Назад", callback_data="mgr_back"
                            )
                        ]
                    ]
                ),
            )
        return

    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"❌ {sub.channel.name}",
                callback_data=f"mgr_do_unsub:{sub.channel_id}",
            )
        ]
        for sub in subscriptions
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="mgr_back")])

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "Выберите канал, от которого хотите отписаться:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )


@router.callback_query(F.data.startswith("mgr_do_unsub:"))
async def confirm_unsubscribe(
    callback: CallbackQuery,
    telegram_user_dao: FromDishka[TelegramUserDAO],
    newsletter_subscription_dao: FromDishka[NewsletterSubscriptionDAO],
    channel_dao: FromDishka[ChannelDAO],
):
    if callback.message is None or callback.data is None:
        return
    await callback.answer()

    channel_id = int(callback.data.split(":", 1)[1])

    telegram_user = await telegram_user_dao.find_by_telegram_id_with_loaded_user(
        callback.from_user.id
    )
    if telegram_user is None:
        return

    with tracer.start_as_current_span("bot.unsubscribe") as span:
        span.set_attribute("telegram_id", callback.from_user.id)
        span.set_attribute("channel_id", channel_id)

        request_logger = logger.bind(
            telegram_id=callback.from_user.id,
            channel_id=channel_id,
        )

        subscriptions = (
            await newsletter_subscription_dao.find_by_user_id_with_loaded_user(
                telegram_user.user_id
            )
        )
        sub = next((s for s in subscriptions if s.channel_id == channel_id), None)

        if sub is None:
            request_logger.info("subscription_not_found")
            await callback.answer("Подписка не найдена.", show_alert=True)
            return

        sub.unsubscribed_at = datetime.now(timezone.utc)
        await newsletter_subscription_dao.commit()
        request_logger.info("unsubscribed")

        channel = await channel_dao.find_by_id(channel_id)
        channel_name = channel.name if channel else "Неизвестный канал"

        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                f"✅ Вы успешно отписались от канала «{channel_name}».",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🔙 В меню", callback_data="mgr_back"
                            )
                        ]
                    ]
                ),
            )


@router.callback_query(F.data == "mgr_edit_email")
async def ask_new_email(
    callback: CallbackQuery,
    state: FSMContext,
    jinja2_env: FromDishka[Environment],
):
    if callback.message is None:
        return
    await callback.answer()
    await state.set_state(ManageStates.waiting_for_new_email)

    template = jinja2_env.get_template("manage_ask_email.html")
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            template.render(),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Отмена", callback_data="mgr_back")]
                ]
            ),
        )


@router.message(ManageStates.waiting_for_new_email)
async def process_new_email(
    message: Message,
    state: FSMContext,
    jinja2_env: FromDishka[Environment],
    email_sender: FromDishka[IEmailSender],
    bot_settings: FromDishka[BotSettings],
):
    if message.from_user is None or message.text is None:
        return

    try:
        email_info = validate_email(message.text.strip())
        email = email_info.normalized
    except EmailNotValidError:
        await message.answer("❌ Некорректный email. Попробуйте ещё раз:")
        return

    with tracer.start_as_current_span("bot.manage_new_email") as span:
        span.set_attribute("telegram_id", message.from_user.id)
        span.set_attribute("email", email)

        code = "".join(
            [
                str(secrets.randbelow(10))
                for _ in range(bot_settings.confirmation_code_length)
            ]
        )
        await state.update_data(new_email=email, email_code=code)

        confirmation_template = jinja2_env.get_template("confirmation_email.html")
        await email_sender(
            to_emails=[email],
            subject="Код подтверждения — Telegram рассылка",
            html_content=confirmation_template.render(code=code),
            subscription_id=None,
        )

        await state.set_state(ManageStates.waiting_for_email_code)

        code_sent_template = jinja2_env.get_template("code_sent.html")
        await message.answer(code_sent_template.render(email=email))


@router.message(ManageStates.waiting_for_email_code)
async def process_email_code(
    message: Message,
    state: FSMContext,
    jinja2_env: FromDishka[Environment],
    telegram_user_dao: FromDishka[TelegramUserDAO],
):
    if message.from_user is None or message.text is None:
        return

    entered_code = message.text.strip()
    data = await state.get_data()
    expected_code: str = data["email_code"]
    new_email: str = data["new_email"]

    with tracer.start_as_current_span("bot.manage_email_code") as span:
        span.set_attribute("telegram_id", message.from_user.id)

        if entered_code != expected_code:
            invalid_template = jinja2_env.get_template("invalid_code.html")
            await message.answer(invalid_template.render())
            return

        telegram_user = await telegram_user_dao.find_by_telegram_id_with_loaded_user(
            message.from_user.id
        )
        if telegram_user is None:
            raise ValueError("Telegram user not found")

        telegram_user.user.email = new_email
        await telegram_user_dao.commit()

        await state.clear()

        template = jinja2_env.get_template("manage_email_updated.html")
        await message.answer(template.render(email=new_email))
