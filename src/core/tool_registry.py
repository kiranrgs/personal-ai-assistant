"""Tool registry: every integration exposes one or more `Tool`s here. The
orchestrator hands the whole list to the LLM as function-calling schemas.

Any tool whose action is irreversible or touches money/payments/calls/smart
home actuation must set `requires_confirmation=True` and its handler must
return a `PendingConfirmation` (never execute directly). The orchestrator
turns that into a Telegram confirm prompt; the real action only runs from
`core.confirmation.execute_confirmed_action` after the user taps Confirm.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class PendingConfirmation:
    action_type: str
    summary: str
    payload: dict[str, Any]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema for the function's arguments
    handler: Callable[..., Any]
    requires_confirmation: bool = False
    # Called with the confirmed payload when the user approves the action.
    executor: Optional[Callable[[dict[str, Any]], Any]] = None

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    if tool.requires_confirmation and tool.executor is None:
        raise ValueError(f"Tool '{tool.name}' requires confirmation but has no executor")
    _REGISTRY[tool.name] = tool
    return tool


def get_tool(name: str) -> Optional[Tool]:
    return _REGISTRY.get(name)


def all_tools() -> list[Tool]:
    return list(_REGISTRY.values())


def all_schemas() -> list[dict[str, Any]]:
    return [t.to_schema() for t in _REGISTRY.values()]
