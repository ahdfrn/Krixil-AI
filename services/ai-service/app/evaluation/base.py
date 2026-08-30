from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelProvider
from app.storage.base import ObjectStorage
from app.tenancy.context import TenantContext


@dataclass
class EvalOutcome:
    passed: bool
    details: dict


EvalCaseFn = Callable[
    [AsyncSession, TenantContext, ModelProvider, ObjectStorage], Awaitable[EvalOutcome]
]


@dataclass(frozen=True)
class EvalCase:
    name: str
    category: str
    run: EvalCaseFn


_REGISTRY: dict[str, EvalCase] = {}


def register_case(case: EvalCase) -> None:
    if case.name in _REGISTRY:
        raise ValueError(f"Eval case '{case.name}' is already registered")
    _REGISTRY[case.name] = case


def list_cases() -> list[EvalCase]:
    return sorted(_REGISTRY.values(), key=lambda c: c.name)
