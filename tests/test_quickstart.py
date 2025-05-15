# ruff: noqa: F401, F811, F403

from asyncio import sleep

from pytest import fixture

from tests.quickstart import ExampleRequest, ExampleResponse
from unrest.api import Client, get_instance

user_headers = {"Authorization": "Bearer secretapikey456"}
admin_headers = {"Authorization": "Bearer secretapikey123"}

@fixture
async def client():
    cli = Client(get_instance())
    cli.headers["Authorization"] = user_headers["Authorization"]
    yield cli

async def test_example_object_response(client: Client):
    response = await client.query("/test/random")
    assert response.status_code == 200
    json = response.json()
    assert json is not None
    assert ExampleResponse(**json)



async def test_example_list_response(client: Client):
    payload = ExampleRequest(domain="example.com")
    response = await client.query("/test/composed/5", payload)
    assert response.status_code == 200
    json = response.json()
    assert json is not None
    assert len(json) == 5



async def test_example_logging_and_errors(client: Client):
    response = await client.query("/test/doomed")
    assert response.status_code == 500



async def test_example_query_context_in_app(client: Client):
    response = await client.query("/test/safe")
    assert response.status_code == 401



async def test_example_query_context_in_db(client: Client):
    response = await client.query("/test/also_safe")
    assert response.status_code == 401



async def test_example_auth_restriction_1(client: Client):
    response = await client.query("/test/secret")
    assert response.status_code == 401

    response = await client.query("/test/secret", headers=admin_headers)
    assert response.status_code == 200



async def test_example_auth_restriction_2(client: Client):
    response = await client.query("/test/also_secret")
    assert response.status_code == 401

    response = await client.query("/test/also_secret", headers=admin_headers)
    assert response.status_code == 200



# async def test_example_background_task(client: Client):
#     response = await client.query("/test/background")
#     assert response.status_code == 200
#     json = response.json()
#     assert json == {"ok": True}



# async def test_example_synchronous_task(client: Client):
#     response = await client.query("/test/synchronous/timeout")
#     assert response.status_code == 504
#     response = await client.query("/test/synchronous")
#     assert response.status_code == 200
#     json = response.json()
#     assert json == {"ok": True}



# async def test_example_asynchronous_task(client: Client):
#     response = await client.query("/test/asynchronous")
#     assert response.status_code == 200
#     json = response.json()
#     assert json["task_id"] is not None

#     task_id = json["task_id"]
#     for _ in range(10):
#         await sleep(1)
#         response = await client.query("/test/asynchronous/%s" % task_id)
#         if response.status_code == 202:
#             continue
#         assert response.status_code == 200
#         json = response.json()
#         assert json == {"ok": True}
#         break
