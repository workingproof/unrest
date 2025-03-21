# ruff: noqa: F401, F811, F403

from asyncio import sleep

from demo import ExampleRequest, ExampleResponse, api

from unrest.testing import Client, asyncfixture, asynctest, lifecycle

admin = {"Authorization": "Bearer secretapikey123"}


@asyncfixture
async def client():
    async with lifecycle(api) as client:
        yield client


@asynctest
async def test_example_object_response(client: Client):
    response = await client.query("/test/random")
    assert response.status_code == 200
    json = response.json()
    assert json is not None
    assert ExampleResponse(**json)
