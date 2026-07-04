"""Two-agent wrappers around the Anthropic Messages API.

Each agent keeps its OWN message history in which *it* is the assistant and
the other agent is the user. That is the cleanest way to run a symmetric
dialogue: from the mentor's point of view the student is 'user', and vice
versa.
"""

from __future__ import annotations

import os
import time

import anthropic

MODEL = os.environ.get("COURSE_MODEL", "claude-sonnet-4-5")
MAX_TOKENS = 1200


class Agent:
    def __init__(self, name: str, system_prompt: str, tools: list | None = None):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.history: list[dict] = []  # this agent's own view of the dialogue
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    def hear(self, text: str) -> None:
        """Record a message from the other agent (as 'user' in this agent's view)."""
        self.history.append({"role": "user", "content": text})

    def _call(self, messages: list[dict], system: str) -> anthropic.types.Message:
        for attempt in range(4):
            try:
                return self.client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=system,
                    messages=messages,
                    tools=self.tools if self.tools else anthropic.NOT_GIVEN,
                )
            except anthropic.APIStatusError as e:
                if e.status_code in (429, 529) and attempt < 3:
                    time.sleep(2**attempt * 2)
                    continue
                raise
        raise RuntimeError("unreachable")

    def speak(self, memory_block: str | None = None, tool_handler=None) -> str:
        """Produce this agent's next turn. If the model calls tools,
        tool_handler(name, args) -> str resolves them, looping until text."""
        system = self.system_prompt
        if memory_block:
            # Memory goes into system context each turn so it never scrolls away.
            system = f"{self.system_prompt}\n\n{memory_block}"

        messages = list(self.history)
        while True:
            response = self._call(messages, system)
            text_parts = [b.text for b in response.content if b.type == "text"]
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                text = "\n".join(text_parts).strip()
                self.history.append({"role": "assistant", "content": text})
                return text

            # Resolve tool calls, then continue the same turn.
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for tu in tool_uses:
                result = tool_handler(tu.name, tu.input) if tool_handler else "ok"
                results.append(
                    {"type": "tool_result", "tool_use_id": tu.id, "content": result}
                )
            messages.append({"role": "user", "content": results})
