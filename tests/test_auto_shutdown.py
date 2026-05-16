"""Tests for the auto-shutdown CLI flag + resolution helper + timer coroutine.

We don't bring up the full Discord bot — just the small surface that:
  - parses --shutdown-after
  - resolves CLI vs config precedence
  - the auto_shutdown_after coroutine that sleeps then closes the bot
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot import _parse_argv, auto_shutdown_after, resolve_shutdown_minutes


# --- _parse_argv ---


def test_parse_argv_default_shutdown_is_none():
    args = _parse_argv([])
    assert args.shutdown_after is None


def test_parse_argv_accepts_positive_integer():
    args = _parse_argv(["--shutdown-after", "30"])
    assert args.shutdown_after == 30


def test_parse_argv_accepts_zero_as_explicit_unbounded():
    # 0 is the explicit "wipe the env-configured value" sentinel.
    args = _parse_argv(["--shutdown-after", "0"])
    assert args.shutdown_after == 0


def test_parse_argv_rejects_non_integer():
    with pytest.raises(SystemExit):
        _parse_argv(["--shutdown-after", "30m"])


# --- resolve_shutdown_minutes ---


def test_resolve_both_none_returns_none():
    assert resolve_shutdown_minutes(None, None) is None


def test_resolve_cli_wins_when_set():
    # CLI=15, config=60 → 15 wins.
    assert resolve_shutdown_minutes(15, 60) == 15


def test_resolve_cli_zero_means_unbounded_overriding_config():
    # 0 from CLI is the "explicitly clear the env-configured value" path —
    # see resolve_shutdown_minutes docstring.
    assert resolve_shutdown_minutes(0, 60) is None


def test_resolve_cli_negative_treated_as_unbounded():
    # Defensive — argparse alone doesn't forbid negative ints. Treat anything
    # not-strictly-positive as unbounded rather than scheduling a negative-
    # sleep timer.
    assert resolve_shutdown_minutes(-5, 60) is None


def test_resolve_falls_back_to_config_when_cli_none():
    assert resolve_shutdown_minutes(None, 45) == 45


def test_resolve_config_zero_passes_through():
    # The Settings field validator forbids 0 / negative at load time, but if
    # someone constructs a Settings with no validator (mocked), the helper
    # itself shouldn't crash on a 0. Falls through to None semantics elsewhere
    # in the caller; here we just assert no exception.
    assert resolve_shutdown_minutes(None, 0) == 0


# --- auto_shutdown_after ---


@pytest.mark.asyncio
async def test_auto_shutdown_after_calls_bot_close():
    """After the configured sleep, the coroutine must invoke bot.close()."""
    bot_mock = MagicMock()
    bot_mock.close = AsyncMock()

    # Patch asyncio.sleep so the test doesn't actually sleep for a minute.
    async def fake_sleep(seconds):
        # Capture the requested duration so the test can assert it.
        fake_sleep.captured = seconds

    fake_sleep.captured = None

    import bot as bot_module

    orig_sleep = bot_module.asyncio.sleep
    bot_module.asyncio.sleep = fake_sleep
    try:
        await auto_shutdown_after(2, bot_mock)
    finally:
        bot_module.asyncio.sleep = orig_sleep

    assert fake_sleep.captured == 120  # 2 minutes in seconds
    bot_mock.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_shutdown_after_can_be_cancelled():
    """If the bot exits before the timer fires (operator-triggered SIGINT,
    for example), the timer task should cancel cleanly without invoking
    close()."""
    bot_mock = MagicMock()
    bot_mock.close = AsyncMock()

    task = asyncio.create_task(auto_shutdown_after(60, bot_mock))
    # Yield once so the task starts.
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # close() must NOT have been called — we cancelled before the sleep
    # completed.
    bot_mock.close.assert_not_awaited()


# --- pytest-asyncio config ---
# The project's pytest.ini sets `asyncio_mode = auto` (verified during
# planning); these tests rely on that. If a future refactor changes the
# mode, the @pytest.mark.asyncio decorators above keep these tests valid.
