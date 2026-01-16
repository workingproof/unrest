# ruff: noqa: F401, F811, F403

from asyncio import sleep

from pytest import fixture, mark

from tests.quickstart import ExampleRequest, ExampleResponse
from unrest.api import Client, get_instance

null_headers = {"Accept": "application/json"}
staff_headers = {"Authorization": "Bearer secretapikey456", "Accept": "application/json"}
admin_headers = {"Authorization": "Bearer secretapikey123", "Accept": "application/json"}

@fixture
async def client():
    app = get_instance()
    #app = "http://localhost:8000"  # for real server testing
    cli = Client(app)
    cli.headers["Authorization"] = staff_headers["Authorization"]
    yield cli

@mark.asyncio(loop_scope="session")
async def test_example_object_response(client: Client):
    response = await client.query("/test/random")
    assert response.status_code == 200
    json = response.json()
    assert json is not None
    assert ExampleResponse(**json)


@mark.asyncio(loop_scope="session")
async def test_example_list_response(client: Client):
    payload = ExampleRequest(domain="example.com")
    response = await client.query("/test/composed/5", payload)
    assert response.status_code == 200
    json = response.json()
    assert json is not None
    assert len(json) == 5


@mark.asyncio(loop_scope="session")
async def test_example_logging_and_errors(client: Client):
    response = await client.query("/test/doomed")
    assert response.status_code == 500

@mark.asyncio(loop_scope="session")
async def test_public_endpoint(client: Client):
    response = await client.query("/test/healthcheck")
    assert response.status_code == 200

@mark.asyncio(loop_scope="session")
async def test_example_query_context_in_app(client: Client):
    response = await client.query("/test/safe")
    assert response.status_code == 401

@mark.asyncio(loop_scope="session")
async def test_example_auth_restriction_1(client: Client):
    response = await client.query("/test/secret", headers=null_headers)
    assert response.status_code == 401

    response = await client.query("/test/secret", headers=admin_headers)
    assert response.status_code == 200


@mark.asyncio(loop_scope="session")
async def test_example_auth_restriction_2(client: Client):
    response = await client.mutate("/test/also_secret", headers=null_headers)
    assert response.status_code == 401

    response = await client.mutate("/test/also_secret", headers=staff_headers)
    assert response.status_code == 401

    response = await client.mutate("/test/also_secret", headers=admin_headers)
    assert response.status_code == 200

@mark.asyncio(loop_scope="session")
async def test_example_background_task(client: Client):
    response = await client.mutate("/test/background")
    assert response.status_code == 200
    job1 = response.json()
    assert job1 is not None
    
    bg_job_ran = False
    for _ in range(10):
        response = await client.query("/test/background/%s" % job1["id"])
        assert response.status_code == 200
        job2 = response.json()
        assert job2 is not None
        assert job2["id"] == job1["id"]
        if job2["completed_at"] is not None:
            bg_job_ran = True
            break
        await sleep(1)

    assert bg_job_ran
