# ruff: noqa: F401, F811, F403

from asyncio import sleep

from tests.quickstart import ExampleRequest, ExampleResponse, api
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


@asynctest
async def test_example_list_response(client: Client):
    payload = ExampleRequest(domain="example.com")
    response = await client.query("/test/composed/5", payload)
    assert response.status_code == 200
    json = response.json()
    assert json is not None
    assert len(json) == 5


@asynctest
async def test_example_logging_and_errors(client: Client):
    response = await client.query("/test/doomed")
    assert response.status_code == 500


@asynctest
async def test_example_query_context_in_app(client: Client):
    response = await client.query("/test/safe")
    assert response.status_code == 403


@asynctest
async def test_example_query_context_in_db(client: Client):
    response = await client.query("/test/also_safe")
    assert response.status_code == 403


@asynctest
async def test_example_unsafe(client: Client):
    response = await client.query("/test/unsafe")
    assert response.status_code == 200
    json = response.json()
    assert json is not None
    resp = ExampleResponse(**json)
    assert resp.email == "bob@somewhere.com"


@asynctest
async def test_example_auth_restriction_1(client: Client):
    response = await client.query("/test/secret")
    assert response.status_code == 401

    response = await client.query("/test/secret", headers=admin)
    assert response.status_code == 200


@asynctest
async def test_example_auth_restriction_2(client: Client):
    response = await client.query("/test/also_secret")
    assert response.status_code == 401

    response = await client.query("/test/also_secret", headers=admin)
    assert response.status_code == 200


@asynctest
async def test_example_background_task(client: Client):
    response = await client.query("/test/background")
    assert response.status_code == 200
    json = response.json()
    assert json == {"ok": True}


@asynctest
async def test_example_synchronous_task(client: Client):
    response = await client.query("/test/synchronous/timeout")
    assert response.status_code == 504
    response = await client.query("/test/synchronous")
    assert response.status_code == 200
    json = response.json()
    assert json == {"ok": True}


@asynctest
async def test_example_asynchronous_task(client: Client):
    response = await client.query("/test/asynchronous")
    assert response.status_code == 200
    json = response.json()
    assert json["task_id"] is not None

    task_id = json["task_id"]
    for _ in range(10):
        await sleep(1)
        response = await client.query("/test/asynchronous/%s" % task_id)
        if response.status_code == 202:
            continue
        assert response.status_code == 200
        json = response.json()
        assert json == {"ok": True}
        break
