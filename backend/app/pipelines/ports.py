"""Ports the pipelines module needs from other domains."""

from typing import Protocol

from .domain import Run


class RunStarter(Protocol):
    """Attach a user to a paper's processing, starting one when there is none."""

    def request(self, *, user_id, paper_id) -> Run: ...
