
from pytest import fixture, raises
from unrest import context, Payload, getLogger, auth, Unauthorized, query, mutate, ContextError
from unrest import api, auth

from unrest import Server
from unrest.api import Client

import base64

log = getLogger(__name__)


class Roles:
    admin = auth.Claim("admin")
    any = auth.UserIsAuthenticated

class ExampleResponse(Payload):
    id: str
    email: str


class ExampleRequest(Payload):
    email: str


@query()
def anyone_can_access_this():
    return None

@query(Roles.any)
def an_example_query():
    return None

@query(Roles.admin)
def an_example_admin_query():
    return None

@mutate(Roles.any)
def an_example_mutation():
    return None



@api.authenticate("basic") 
async def authenticate_with_basic_auth(token: str) -> auth.User | None:
    try:
        decoded = base64.b64decode(token).decode("ascii")
        username, password = decoded.split(":")
        return auth.AuthenticatedUser("", username, {}, {})
    except Exception as exc:
        log.warning('Invalid basic auth credentials')
    return None


@api.query("/object/{object_id}")
async def get_object(object_id: str) -> ExampleResponse:
    return ExampleResponse(id=object_id, email="foo@bar.com")


@api.query("/list/{n:int}")
async def get_objects(req: ExampleRequest, n: int) -> list[ExampleResponse]:
    results = []
    for i in range(n):
        results.append(ExampleResponse(id=str(i), email=req.email))
    return results



@api.query("/unsafe")
async def enforce_query_context() -> None:
    try:
        an_example_mutation()
    except ContextError:
        log.warning("Phew! Can't accidentally run mutations in a query context!")
        raise

@api.mutate("/safe")
async def enforce_mutate_context() -> None:
    an_example_mutation()
    
@api.query("/protected", Roles.admin) 
async def auth_restriction_on_endpoint():
    an_example_admin_query()

@api.query("/also_protected")
async def auth_restriction_not_on_endpoint():
    an_example_admin_query()


@fixture
def authenticated_user():
    from unrest.contexts import usercontext
    with usercontext(auth.AuthenticatedUser("123", "jon", {}, {})):
        yield

@fixture
def client():
    cli = Client(Server()) # FIXME
    cli.headers["Authorization"] = "Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ=="
    yield cli

async def test_happy_path_directly(authenticated_user):
    obj = await get_object("obj123")
    assert obj.id == "obj123"

    objs = await get_objects(ExampleRequest(email="foo@bar.com"), 10)
    assert len(objs) == 10
    assert all([obj.email == "foo@bar.com" for obj in objs])

    with raises(ContextError):
        await enforce_query_context()

    await enforce_mutate_context()

    with raises(Unauthorized):
        await auth_restriction_on_endpoint()

    with raises(Unauthorized):
        await auth_restriction_not_on_endpoint()        


async def test_happy_path_indirectly(client: Client):
    resp = await client.query("/object/obj123")
    assert resp.is_success
    obj = resp.json()
    assert obj is not None
    assert obj["id"] == "obj123"

    resp = await client.query("/list/5", ExampleRequest(email="foo@bar.com"))
    assert resp.is_success
    obj = resp.json()
    assert obj is not None
    assert len(obj) == 5


    resp = await client.query("/unsafe")
    assert not resp.is_success
    assert resp.status_code == 403

    resp = await client.mutate("/safe")
    assert resp.is_success

    resp = await client.query("/protected")
    assert resp.status_code == 401

    resp = await client.query("/also_protected")        
    assert resp.status_code == 401
