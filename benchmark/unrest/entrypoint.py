#
# The following walkthrough should be 80% sufficient if you are already familiar with
# [Flask](https://flask.palletsprojects.com/en/3.0.x/), [FastAPI](https://fastapi.tiangolo.com/)
# or [Django](https://www.django-rest-framework.org/). It's not rocket science.
#
# However, to avoid being misled by any prior experience with those frameworks,
# there are a couple of high-level points to appreciate:
#
# 1. **Unrest** is solely focussed on rapidly developing high-performance apps with Postgres.
#    Although it has some nice features, the abstractions are lightweight and batteries are *not* included.
# 2. **Unrest** surrounds your application with a thin layer built on [Starlette](https://www.starlette.io/),
#    [Asyncpg](https://magicstack.github.io/asyncpg/current/) and [Taskiq](https://taskiq-python.github.io/).
#    It sets things up nicely and then gets out of the way.
# 3. **Unrest** eschews REST semantics -- *hence the name*. Instead there are `query` and `mutate` contexts
#    that propagate from the API layer to the DB layer.
#
# With all that said, we can
#
# ```
# $ pip install unrest
# ```
#
# and then import some typical symbols
#:python

from unrest import context, getLogger, query, Unauthorized, Payload
from unrest import db, api, auth

log = getLogger(__name__)

@db.query
def random():
    return db.fetchrow("select * from users order by random() limit 1")


class ExampleResponse(Payload):
    id: str
    email: str


@api.authenticate("bearer")
async def authenticate_with_api_key(token: str) -> auth.User | None:
    props = await db._fetchrow("select id, email, claims from users where apikey = $1", token)
    if props:
        return auth.AuthenticatedUser(props["id"], props["email"], {}, props["claims"])
    return None

@api.query("/static")
async def get_static() -> ExampleResponse:
    return ExampleResponse(id="123", email="foo@bar.com")

@api.query("/random")
async def get_random() -> ExampleResponse:
    async with random() as result:
        return result


from unrest import Server
server = Server()



