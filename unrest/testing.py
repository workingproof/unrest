from contextlib import asynccontextmanager

import pytest
from asgi_lifespan import LifespanManager
from pytest_asyncio import fixture

import unrest.config as config
from unrest.client import Client
from unrest.router import _singleton

config.is_under_test(True)

asyncfixture = fixture(loop_scope="session", scope="session")
asynctest = pytest.mark.asyncio(loop_scope="session")


@asynccontextmanager
async def lifecycle(app):
    async with LifespanManager(app) as manager:
        async with Client(manager.app) as client:
            yield client


@asyncfixture
async def client():
    async with lifecycle(_singleton) as client:
        yield client
