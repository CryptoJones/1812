#!/usr/bin/env python3
"""
1812 — Discord chatbot
"""

import argparse
import asyncio
import logging
import signal
import json
import sys
import time
from typing import AsyncIterator

import discord
from discord import app_commands
from discord.ext import commands

import db
from config import settings
from llm import build_backend, LLMBackend
from rate_limiter import RateLimiter
from web import run_web_in_background

# --- Structured JSON logging ---

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        })

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
log = logging.getLogger("1812")

# Suppress discord.py's own verbose logging
logging.getLogger("discord").setLevel(logging.WARNING)

# --- Bot setup ---

PERSONAS: dict[str, str] = {
    "default":   settings.system_prompt,
    "concise":   settings.system_prompt + " Be extremely concise. One or two sentences max unless the question demands more.",
    "creative":  settings.system_prompt + " Lean into creative, lateral thinking. Surprising angles welcome.",
    "technical": settings.system_prompt + " Go deep on technical detail. Show your work. Include code when it helps.",
}

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
rate_limiter = RateLimiter(
    max_requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)
llm: LLMBackend = build_backend()


# --- Helpers ---

def system_prompt_for(server_id: int | None) -> str:
    return PERSONAS.get("default", settings.system_prompt)


async def resolve_system_prompt(server_id: int | None) -> str:
    if server_id:
        custom = await db.get_server_system_prompt(server_id)
        if custom:
            return custom
    return settings.system_prompt


async def build_context(channel_id: int, server_id: int | None, user_id: int, new_content: list | str) -> list[dict]:
    system = await resolve_system_prompt(server_id)

    # Inject per-user memory if available
    memory = await db.get_user_memory(user_id)
    if memory:
        system = f"{system}\n\nWhat you know about this user: {memory}"

    history = await db.get_channel_history(channel_id)

    # Summarise if history is too long
    if len(history) >= settings.summarise_at:
        summary = await summarise_history(history)
        await db.replace_channel_history(channel_id, [
            {"role": "assistant", "content": f"[Summary of earlier conversation]: {summary}"}
        ])
        history = await db.get_channel_history(channel_id)

    # Keep last N messages
    if len(history) > settings.max_history_messages:
        history = history[-settings.max_history_messages:]

    messages = [{"role": "system", "content": system}] + history
    messages.append({"role": "user", "content": new_content})
    return messages


async def summarise_history(history: list[dict]) -> str:
    summarise_prompt = [
        {"role": "system", "content": "You are a summariser. Summarise the following conversation concisely in 3-5 sentences."},
        {"role": "user", "content": "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history)},
    ]
    result = ""
    async for chunk in llm.stream(summarise_prompt):
        result += chunk
    return result


MAX_DISCORD_MSG = 1990  # 2000 limit minus room for the "▌" cursor


async def stream_reply(message: discord.Message, messages: list[dict]) -> str:
    """Stream LLM response, editing the Discord message every ~1 second.

    Splits the response across multiple Discord messages when it exceeds the
    2000-char per-message limit, preferring to break on newlines.
    """
    sent = await message.reply("▌")
    full = ""      # everything generated, returned for DB storage
    current = ""   # text in the message currently being edited
    last_edit = asyncio.get_event_loop().time()

    async for chunk in llm.stream(messages):
        full += chunk
        current += chunk

        while len(current) > MAX_DISCORD_MSG:
            split_at = current.rfind("\n", 0, MAX_DISCORD_MSG)
            if split_at <= 0:
                split_at = MAX_DISCORD_MSG
            head, current = current[:split_at], current[split_at:].lstrip("\n")
            await sent.edit(content=head)
            sent = await message.channel.send("▌")
            last_edit = asyncio.get_event_loop().time()

        now = asyncio.get_event_loop().time()
        if now - last_edit >= 1.0:
            await sent.edit(content=current + "▌")
            last_edit = now

    if current:
        await sent.edit(content=current)
    elif full:
        await sent.delete()
    else:
        await sent.edit(content="(no response)")

    return full


def build_image_content(text: str, attachments: list[discord.Attachment]) -> list | str:
    """Build OpenAI vision-compatible content if images are attached."""
    images = [a for a in attachments if a.content_type and a.content_type.startswith("image/")]
    if not images:
        return text

    content: list = [{"type": "text", "text": text}]
    for img in images:
        content.append({"type": "image_url", "image_url": {"url": img.url}})
    return content


# --- Events ---

@bot.event
async def on_ready():
    await db.init_db()
    await bot.tree.sync()
    run_web_in_background()
    log.info(f"1812 online as {bot.user} (ID: {bot.user.id})")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions
    bot_role_ids = {r.id for r in message.guild.me.roles} if message.guild else set()
    is_role_mentioned = any(r.id in bot_role_ids for r in message.role_mentions)

    if not is_dm and not is_mentioned and not is_role_mentioned:
        await bot.process_commands(message)
        return

    # Rate limit
    if not rate_limiter.is_allowed(message.author.id):
        wait = rate_limiter.seconds_until_reset(message.author.id)
        await message.reply(f"Slow down. Try again in {wait}s.")
        return

    text = message.content.replace(f"<@{bot.user.id}>", "").strip()
    if not text and not message.attachments:
        await message.reply("Yeah?")
        return

    content = build_image_content(text or "What's in this image?", message.attachments)
    server_id = message.guild.id if message.guild else None

    try:
        messages = await build_context(message.channel.id, server_id, message.author.id, content)
        reply = await stream_reply(message, messages)

        await db.add_message(message.channel.id, "user", text or "[image]", message.author.id, str(message.author))
        await db.add_message(message.channel.id, "assistant", reply)

        log.info({"event": "reply", "channel": message.channel.id, "user": str(message.author)})
    except Exception as e:
        log.error({"event": "error", "error": str(e)})
        await message.reply(f"Something went wrong: {type(e).__name__}")
        raise

    await bot.process_commands(message)


# --- Slash Commands ---

@bot.tree.command(name="clear", description="Clear conversation history for this channel.")
async def slash_clear(interaction: discord.Interaction):
    await db.clear_channel_history(interaction.channel_id)
    await interaction.response.send_message("Conversation history cleared.", ephemeral=True)
    log.info({"event": "clear", "channel": interaction.channel_id, "user": str(interaction.user)})


@bot.tree.command(name="persona", description="Switch 1812's persona for this server.")
@app_commands.describe(name="Persona name: default, concise, creative, technical")
async def slash_persona(interaction: discord.Interaction, name: str):
    if name not in PERSONAS:
        options = ", ".join(PERSONAS.keys())
        await interaction.response.send_message(f"Unknown persona. Options: {options}", ephemeral=True)
        return

    if interaction.guild:
        await db.set_server_system_prompt(interaction.guild.id, interaction.guild.name, PERSONAS[name])

    await interaction.response.send_message(f"Persona set to **{name}**.", ephemeral=True)
    log.info({"event": "persona", "persona": name, "guild": str(interaction.guild_id)})


@bot.tree.command(name="model", description="Switch the LLM model (admin only).")
@app_commands.describe(model="Model name e.g. gpt-4o, gpt-4o-mini, claude-3-5-sonnet-20241022")
@app_commands.default_permissions(administrator=True)
async def slash_model(interaction: discord.Interaction, model: str):
    global llm
    settings.llm_model = model
    llm = build_backend()
    await interaction.response.send_message(f"Model switched to **{model}**.", ephemeral=True)
    log.info({"event": "model_switch", "model": model, "user": str(interaction.user)})


@bot.tree.command(name="remember", description="Tell 1812 something to remember about you.")
@app_commands.describe(text="What should 1812 remember?")
async def slash_remember(interaction: discord.Interaction, text: str):
    existing = await db.get_user_memory(interaction.user.id)
    updated = f"{existing}\n{text}".strip() if existing else text
    await db.set_user_memory(interaction.user.id, str(interaction.user), updated)
    await interaction.response.send_message("Got it. I'll remember that.", ephemeral=True)


@bot.tree.command(name="forget", description="Clear everything 1812 remembers about you.")
async def slash_forget(interaction: discord.Interaction):
    await db.set_user_memory(interaction.user.id, str(interaction.user), "")
    await interaction.response.send_message("Memory cleared.", ephemeral=True)


# --- Graceful shutdown ---

def _parse_argv(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI parsing extracted so unit tests can drive it without sys.argv mutation."""
    parser = argparse.ArgumentParser(
        prog="1812",
        description="1812 — Discord chatbot with configurable LLM backends.",
    )
    parser.add_argument(
        "--shutdown-after",
        type=int,
        default=None,
        metavar="MINUTES",
        help=(
            "Auto-shutdown the bot after this many minutes of runtime. "
            "Overrides the shutdown_after_minutes config / env value. "
            "Omit (or pass 0) for unbounded runtime."
        ),
    )
    return parser.parse_args(argv)


def resolve_shutdown_minutes(
    cli_value: int | None,
    config_value: int | None,
) -> int | None:
    """CLI argument wins; falls back to the config value; None = unbounded.

    `0` from the CLI is treated as an explicit "unbounded" sentinel so an
    operator can wipe an env-configured timeout from the command line
    without having to delete the env var.
    """
    if cli_value is not None:
        return cli_value if cli_value > 0 else None
    return config_value


async def auto_shutdown_after(minutes: int, bot_to_close: discord.Client) -> None:
    """Sleep for `minutes`, then call bot.close() to trigger a clean shutdown.

    Logged at start (so the operator sees the deadline they're committed to)
    and again right before closing the bot (so it's clear *why* the bot
    exited if it lands in a log aggregator without context).
    """
    log.info({"event": "auto_shutdown_armed", "minutes": minutes})
    await asyncio.sleep(minutes * 60)
    log.info({"event": "auto_shutdown_firing", "minutes": minutes})
    await bot_to_close.close()


async def main(argv: list[str] | None = None) -> None:
    args = _parse_argv(argv)
    shutdown_minutes = resolve_shutdown_minutes(
        args.shutdown_after, settings.shutdown_after_minutes
    )

    loop = asyncio.get_running_loop()

    def shutdown(signum: int):
        log.info({"event": "shutdown", "signal": signum})
        loop.create_task(bot.close())

    loop.add_signal_handler(signal.SIGTERM, shutdown, signal.SIGTERM)
    loop.add_signal_handler(signal.SIGINT, shutdown, signal.SIGINT)

    if shutdown_minutes is not None:
        # Background timer task — cancelled automatically when the event
        # loop shuts down. We don't await it directly because the bot's
        # gateway loop is the foreground task.
        loop.create_task(auto_shutdown_after(shutdown_minutes, bot))

    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
