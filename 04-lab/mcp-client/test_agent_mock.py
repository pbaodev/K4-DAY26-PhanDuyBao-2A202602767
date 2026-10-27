#!/usr/bin/env python3
"""
End-to-end test của weather agent KHÔNG cần API key.

- MCP server chạy với WEATHER_MOCK=1 (dữ liệu thời tiết giả).
- Model Gemini được thay bằng ScriptedLlm: lần 1 yêu cầu gọi tool, lần 2 tổng hợp
  kết quả tool. Nhờ vậy vẫn kiểm chứng được toàn bộ vòng lặp của ADK:
  list_tools -> model chọn tool -> ADK gọi MCP server -> model nhận kết quả.

Chạy: (server đang chạy với WEATHER_MOCK=1)  uv run python test_agent_mock.py
"""
import asyncio
import warnings
from typing import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

warnings.filterwarnings("ignore")

from weather_agent import root_agent


class ScriptedLlm(BaseLlm):
    """Model giả: gọi tool theo kịch bản, rồi trả lời bằng nội dung tool trả về."""

    model: str = "scripted-llm"

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        last = llm_request.contents[-1]
        responses = [p.function_response for p in last.parts if p.function_response]
        if responses:
            text = "\n".join(str(r.response) for r in responses)
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))
            return
        question = last.parts[0].text.lower()
        if "forecast" in question:
            call = types.FunctionCall(name="get_forecast", args={"city": "Hanoi", "days": 2})
        else:
            call = types.FunctionCall(name="get_current_weather", args={"city": "Hanoi"})
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=call)]))


async def ask(runner: InMemoryRunner, question: str) -> tuple[list[str], str]:
    session = await runner.session_service.create_session(app_name=runner.app_name, user_id="u")
    tool_calls, answer = [], ""
    async for event in runner.run_async(
        user_id="u",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=question)]),
    ):
        for part in (event.content.parts if event.content else []):
            if part.function_call:
                tool_calls.append(part.function_call.name)
            if part.text:
                answer = part.text
    return tool_calls, answer


async def main() -> int:
    root_agent.model = ScriptedLlm()
    runner = InMemoryRunner(agent=root_agent, app_name="weather_test")
    failures = 0
    cases = [
        ("What's the weather in Hanoi?", "get_current_weather", "Temperature"),
        ("Give me a 2-day forecast for Hanoi", "get_forecast", "Chance of Rain"),
    ]
    for question, expected_tool, expected_text in cases:
        tools, answer = await ask(runner, question)
        ok = tools == [expected_tool] and expected_text in answer and "[MOCK DATA" in answer
        failures += not ok
        print(f"{'✅' if ok else '❌'} {question!r} -> tools={tools}")
        print("   " + answer.strip().replace("\\n", "\n   ")[:400])
    await root_agent.tools[0].close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
