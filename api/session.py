"""Request-local Streamlit session-state adapter for the legacy workflow."""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from types import SimpleNamespace
from typing import Any

from ui import single_stock_workflow


_request_state: ContextVar[dict[str, Any] | None] = ContextVar("strategy_api_session_state", default=None)
_original_streamlit = single_stock_workflow.st


class RequestSessionState(MutableMapping[str, Any]):
    def _mapping(self) -> dict[str, Any]:
        state = _request_state.get()
        if state is None:
            return _original_streamlit.session_state
        return state

    def __getitem__(self, key: str) -> Any:
        return self._mapping()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._mapping()[key] = value

    def __delitem__(self, key: str) -> None:
        del self._mapping()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping())

    def __len__(self) -> int:
        return len(self._mapping())


_proxy = RequestSessionState()
# Only the workflow module is adapted. The process-wide ``streamlit`` module is
# left untouched, while ContextVar keeps concurrent API jobs isolated.
single_stock_workflow.st = SimpleNamespace(session_state=_proxy)


@contextmanager
def request_session_state(initial: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    state = dict(initial or {})
    token = _request_state.set(state)
    try:
        yield state
    finally:
        _request_state.reset(token)
