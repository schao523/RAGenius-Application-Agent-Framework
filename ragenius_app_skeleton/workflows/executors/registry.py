from __future__ import annotations

from typing import Any, Callable


class ExecutorRegistry:
    def __init__(self) -> None:
        self.tool_executors: dict[str, Callable[..., dict[str, Any]]] = {}
        self.skill_executors: dict[str, Callable[..., dict[str, Any]]] = {}
        self.assemblers: dict[str, Callable[..., dict[str, Any]]] = {}
        self.validators: dict[str, Callable[..., dict[str, Any]]] = {}

    def register_tool(self, name: str, fn: Callable[..., dict[str, Any]]) -> None:
        self.tool_executors[str(name)] = fn

    def register_skill(self, name: str, fn: Callable[..., dict[str, Any]]) -> None:
        self.skill_executors[str(name)] = fn

    def register_assembler(self, name: str, fn: Callable[..., dict[str, Any]]) -> None:
        self.assemblers[str(name)] = fn

    def register_validator(self, name: str, fn: Callable[..., dict[str, Any]]) -> None:
        self.validators[str(name)] = fn

    def get_tool(self, name: str) -> Callable[..., dict[str, Any]] | None:
        return self.tool_executors.get(str(name))

    def get_skill(self, name: str) -> Callable[..., dict[str, Any]] | None:
        return self.skill_executors.get(str(name))

    def get_assembler(self, name: str) -> Callable[..., dict[str, Any]] | None:
        return self.assemblers.get(str(name))

    def get_validator(self, name: str) -> Callable[..., dict[str, Any]] | None:
        return self.validators.get(str(name))
