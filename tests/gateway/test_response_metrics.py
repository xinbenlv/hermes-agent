import importlib
from types import SimpleNamespace

import pytest

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, SendResult
from gateway.session import SessionSource


class CaptureAdapter(BasePlatformAdapter):
    def __init__(self, platform=Platform.TELEGRAM):
        super().__init__(PlatformConfig(enabled=True, token="***"), platform)
        self.sent = []

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        return None

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append(
            {
                "chat_id": chat_id,
                "content": content,
                "reply_to": reply_to,
                "metadata": metadata,
            }
        )
        return SendResult(success=True, message_id="m-1")

    async def get_chat_info(self, chat_id: str):
        return {"id": chat_id}


def _make_runner():
    gateway_run = importlib.import_module("gateway.run")
    GatewayRunner = gateway_run.GatewayRunner
    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    return runner


def test_format_response_metrics_summary_for_supported_platform():
    runner = _make_runner()
    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="chat-1",
        user_id="u1",
        user_name="u1",
        chat_type="dm",
    )

    summary = runner._format_response_metrics_summary(
        source=source,
        agent_result={
            "final_response": "done",
            "input_tokens": 10_000,
            "output_tokens": 2_450,
            "model": "openai/gpt-5.4",
        },
        elapsed_seconds=18,
        enabled=True,
    )

    assert summary == "— 18s · 12.4K tok · gpt-5.4"


def test_format_response_metrics_summary_skips_unsupported_platform():
    runner = _make_runner()
    source = SessionSource(
        platform=Platform.WEBHOOK,
        chat_id="chat-1",
        user_id="u1",
        user_name="u1",
        chat_type="dm",
    )

    summary = runner._format_response_metrics_summary(
        source=source,
        agent_result={
            "final_response": "done",
            "input_tokens": 10_000,
            "output_tokens": 2_450,
            "model": "openai/gpt-5.4",
        },
        elapsed_seconds=18,
        enabled=True,
    )

    assert summary is None


def test_format_response_metrics_summary_skips_when_gate_disabled():
    runner = _make_runner()
    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="chat-1",
        user_id="u1",
        user_name="u1",
        chat_type="dm",
    )

    summary = runner._format_response_metrics_summary(
        source=source,
        agent_result={
            "final_response": "done",
            "input_tokens": 10_000,
            "output_tokens": 2_450,
            "model": "openai/gpt-5.4",
        },
        elapsed_seconds=18,
    )

    assert summary is None


@pytest.mark.asyncio
async def test_send_response_metrics_followup_uses_thread_metadata():
    runner = _make_runner()
    adapter = CaptureAdapter(platform=Platform.TELEGRAM)
    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="chat-1",
        user_id="u1",
        user_name="u1",
        chat_type="group",
        thread_id="17585",
    )

    await runner._send_response_metrics_followup(
        adapter=adapter,
        source=source,
        metrics_summary="— 18s · 12.4K tok · gpt-5.4",
    )

    assert adapter.sent == [
        {
            "chat_id": "chat-1",
            "content": "— 18s · 12.4K tok · gpt-5.4",
            "reply_to": None,
            "metadata": {"thread_id": "17585"},
        }
    ]
