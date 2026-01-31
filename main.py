#!/usr/bin/env python3
"""
Cloudflare DNS Manager Bot

A Telegram bot for managing Cloudflare DNS records via API.
Supports both polling and webhook modes.

Usage:
    python main.py          # Run with polling (default)
    USE_WEBHOOK=true python main.py  # Run with webhook
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from dotenv import load_dotenv

from bot.handlers import commands_router, callbacks_router
from bot.middlewares.auth import AuthMiddleware
from bot.services.cloudflare import CloudflareAPI

# Load environment variables
load_dotenv()

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "bot.log")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE),
    ],
)

# Suppress noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


def get_config() -> dict:
    """Load and validate configuration from environment variables."""
    config = {
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "telegram_proxy": os.getenv("TELEGRAM_PROXY", ""),  # socks5://host:port
        "cf_api_token": os.getenv("CLOUDFLARE_API_TOKEN"),
        "cf_zone_id": os.getenv("CLOUDFLARE_ZONE_ID"),
        "allowed_users": os.getenv("ALLOWED_USER_IDS", ""),
        "use_webhook": os.getenv("USE_WEBHOOK", "false").lower() == "true",
        "webhook_url": os.getenv("WEBHOOK_URL", ""),
        "webhook_path": os.getenv("WEBHOOK_PATH", "/webhook"),
        "webhook_host": os.getenv("WEBHOOK_HOST", "0.0.0.0"),
        "webhook_port": int(os.getenv("WEBHOOK_PORT", "8080")),
        "webhook_secret": os.getenv("WEBHOOK_SECRET", ""),
    }

    # Validate required fields
    missing = []
    if not config["telegram_token"]:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not config["cf_api_token"]:
        missing.append("CLOUDFLARE_API_TOKEN")
    # cf_zone_id is now optional - user can select zone via /zones command
    if not config["allowed_users"]:
        missing.append("ALLOWED_USER_IDS")

    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    # Parse allowed user IDs
    try:
        config["allowed_user_ids"] = {
            int(uid.strip())
            for uid in config["allowed_users"].split(",")
            if uid.strip()
        }
    except ValueError as e:
        logger.error(f"Invalid ALLOWED_USER_IDS format: {e}")
        sys.exit(1)

    if not config["allowed_user_ids"]:
        logger.error("ALLOWED_USER_IDS is empty - no users would be able to use the bot")
        sys.exit(1)

    # Validate webhook config if enabled
    if config["use_webhook"] and not config["webhook_url"]:
        logger.error("WEBHOOK_URL is required when USE_WEBHOOK is true")
        sys.exit(1)

    return config


async def on_startup(bot: Bot, config: dict) -> None:
    """Called when bot starts up."""
    logger.info("Bot starting up...")

    if config["use_webhook"]:
        webhook_url = f"{config['webhook_url']}{config['webhook_path']}"
        await bot.set_webhook(
            url=webhook_url,
            secret_token=config["webhook_secret"] if config["webhook_secret"] else None,
        )
        logger.info(f"Webhook set to: {webhook_url}")
    else:
        # Delete any existing webhook when using polling
        await bot.delete_webhook()
        logger.info("Webhook deleted, using polling mode")


async def on_shutdown(bot: Bot, cf: CloudflareAPI) -> None:
    """Called when bot shuts down."""
    logger.info("Bot shutting down...")
    await cf.close()
    await bot.session.close()


async def run_polling(bot: Bot, dp: Dispatcher, config: dict, cf: CloudflareAPI) -> None:
    """Run the bot in polling mode."""
    await on_startup(bot, config)

    try:
        logger.info("Starting polling...")
        await dp.start_polling(bot, cf=cf)
    finally:
        await on_shutdown(bot, cf)


async def run_webhook(bot: Bot, dp: Dispatcher, config: dict, cf: CloudflareAPI) -> None:
    """Run the bot in webhook mode."""
    await on_startup(bot, config)

    app = web.Application()

    # Create webhook handler
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=config["webhook_secret"] if config["webhook_secret"] else None,
        cf=cf,  # Pass CloudflareAPI to handlers
    )

    webhook_handler.register(app, path=config["webhook_path"])
    setup_application(app, dp, bot=bot)

    # Add shutdown handler
    async def cleanup(app: web.Application) -> None:
        await on_shutdown(bot, cf)

    app.on_cleanup.append(cleanup)

    # Run the web server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config["webhook_host"], config["webhook_port"])

    try:
        logger.info(f"Starting webhook server on {config['webhook_host']}:{config['webhook_port']}")
        await site.start()
        # Keep running
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


def create_bot_and_dispatcher(config: dict) -> tuple[Bot, Dispatcher, CloudflareAPI]:
    """Create and configure the bot, dispatcher, and services."""
    # Initialize bot session (with optional proxy)
    session = None
    if config["telegram_proxy"]:
        session = AiohttpSession(proxy=config["telegram_proxy"])
        logger.info(f"Using proxy: {config['telegram_proxy']}")

    # Initialize bot
    bot = Bot(
        token=config["telegram_token"],
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
        session=session,
    )

    # Initialize Cloudflare API client
    cf = CloudflareAPI(
        api_token=config["cf_api_token"],
        default_zone_id=config["cf_zone_id"],
    )

    # Initialize dispatcher with memory storage for FSM
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register auth middleware
    auth_middleware = AuthMiddleware(config["allowed_user_ids"])
    dp.message.middleware(auth_middleware)
    dp.callback_query.middleware(auth_middleware)

    # Register routers
    dp.include_router(commands_router)
    dp.include_router(callbacks_router)

    logger.info(f"Authorized users: {config['allowed_user_ids']}")
    if config["cf_zone_id"]:
        logger.info(f"Default zone ID: {config['cf_zone_id'][:8]}...")
    else:
        logger.info("No default zone - user must select via /zones")

    return bot, dp, cf


def main() -> None:
    """Main entry point."""
    logger.info("=" * 50)
    logger.info("Cloudflare DNS Manager Bot")
    logger.info("=" * 50)

    config = get_config()
    bot, dp, cf = create_bot_and_dispatcher(config)

    if config["use_webhook"]:
        logger.info("Running in WEBHOOK mode")
        asyncio.run(run_webhook(bot, dp, config, cf))
    else:
        logger.info("Running in POLLING mode")
        asyncio.run(run_polling(bot, dp, config, cf))


if __name__ == "__main__":
    main()