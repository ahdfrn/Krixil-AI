from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class ModelMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ToolSchema:
    """A tool's shape as offered to the model — deliberately just name/description/JSON schema,
    not app.tools.base.Tool itself, so this layer stays independent of the tool registry."""

    name: str
    description: str
    parameters: dict


@dataclass
class ToolCallRequest:
    name: str
    arguments: dict


@dataclass
class ModelResponse:
    content: str
    model: str
    usage: dict = field(default_factory=dict)
    tool_calls: list[ToolCallRequest] = field(default_factory=list)


class ModelProvider(ABC):
    """Every model backend (cloud or self-hosted) implements this so the rest of the app never
    depends on a concrete vendor. See docs/architecture/phase0.md."""

    name: str

    @abstractmethod
    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse: ...

    # Deliberately `def`, not `async def`: concrete implementations are async generators (they
    # `yield`), which mypy only type-checks correctly against an abstract method declared this
    # way — an `async def` stub here would type as a coroutine *returning* an AsyncIterator
    # instead of *being* one. See mypy docs: more_types.html#asynchronous-iterators.
    @abstractmethod
    def stream(self, messages: list[ModelMessage], **kwargs) -> AsyncIterator[str]: ...

    @abstractmethod
    async def embeddings(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def tool_call(
        self, messages: list[ModelMessage], tools: list[ToolSchema], **kwargs
    ) -> ModelResponse: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
