from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.tenancy.context import TenantContext


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# HIGH and CRITICAL always require human approval before executing — this is the spec's rule,
# not a per-tool choice, so it isn't a field on Tool itself.
APPROVAL_REQUIRED_LEVELS = {RiskLevel.HIGH, RiskLevel.CRITICAL}

# The third parameter is really "an instance of this Tool's own input_model" — each registered
# handler is typed with its specific pydantic subclass, which Python's Callable can't express
# contravariantly without generics. Typed Any here rather than BaseModel so those concrete
# handler signatures type-check; the actual guarantee is enforced at runtime, not statically —
# request_tool_execution() always validates via tool.input_model before calling tool.handler.
ToolHandler = Callable[[AsyncSession, TenantContext, Any], Awaitable[dict]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    risk_level: RiskLevel
    required_permission: str
    handler: ToolHandler
    timeout_seconds: float = 30.0


_REGISTRY: dict[str, Tool] = {}


def register_tool(tool: Tool) -> None:
    if tool.name in _REGISTRY:
        raise ValueError(f"Tool '{tool.name}' is already registered")
    _REGISTRY[tool.name] = tool


def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(name)


def list_tools() -> list[Tool]:
    return sorted(_REGISTRY.values(), key=lambda t: t.name)
