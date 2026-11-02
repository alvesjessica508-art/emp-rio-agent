from datetime import datetime

import pytest

from emporio_agent import config
from emporio_agent.data_store import DataStore
from emporio_agent.tools import ToolBox


@pytest.fixture(scope="session")
def store() -> DataStore:
    return DataStore()


@pytest.fixture
def clock():
    """Relógio mutável: clock.value = datetime(...)."""

    class Clock:
        value = datetime(2026, 3, 25, 10, 30, tzinfo=config.STORE_TZ)  # quarta-feira

        def __call__(self):
            return self.value

    return Clock()


@pytest.fixture
def toolbox(store, clock, tmp_path) -> ToolBox:
    return ToolBox(store=store, now=clock, var_dir=tmp_path)
