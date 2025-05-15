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


class Roles:
    admin = auth.Claim("admin")
    any = auth.UserIsAuthenticated


#:end
#
# At this point your probably expecting to see some API code. It will be clearer to
# work up to that starting from the database backend.
#
# ### The DB layer
#
# **Unrest** is is deliberately not an ORM. But it still makes
# working programmatically with Postgres quite a lot nicer.
#
# Some highlights follow after the code listing:
#
#:python


@db.query
def get_random():
    return db.fetchrow("select * from users order by random() limit 1")


@db.query
def get_parameterised(domain: str):
    return db.fetch(
        """
        select * from users
        where email like '%@' || $1
        """,
        domain,
    )


@db.query
def get_composed(domain: str, n=5):
    return db.fetch(
        """
        select id, email 
        from $1
        order by random()
        limit $2 
        """,
        get_parameterised(domain),
        n,
    )


@db.mutate
def bit_dangerous():
    return db.fetch("delete from users where true returning *")


@db.query
def looks_safe_enough():
    # NB: This query will not run because it depends on a mutation
    oblivious = bit_dangerous()
    return db.fetch("select * from $1", oblivious)


@db.query
def really_is_dangerous():
    # NB: annotated as a query...but still will not run because
    #     database connection will be readonly
    return db.fetch("delete from users where true returning *")


#:end
# Some highlights:
#
# * All database access is abstracted behind functions and thus amenable to IDE tooling.
# * Each function is annotated as `query` or `mutate`. Mutations won't (by default) run in a
#   `query` context. This is enforced by both **Unrest** and Postgres.
# * These functions do not hit the database directly, but rather return an `async callable` that
#   will hit the database when invoked (see below). These callables are called "Fragments".
# * Fragments can be composed. The result is a single database query with a very readable CTE.
#

# ### The API layer
#
# Away from our database queries and business logic we develop our API endpoints.
#
# **Unrest** uses the following to keep them as boilerplate free as possible:
#
# * Clean (de-)serialisation based on natural function signature type annotations.
# * A `context` for accessing certain variables without prop drilling, dependency injection or creating a dependency on HTTP machinery.
#   The `context` can also be customised with key/values that will automatically be included in (structured) logs.
#
#:python


class ExampleResponse(Payload):
    id: str
    email: str


class ExampleRequest(Payload):
    domain: str


@api.query("/test/random")
async def example_object_response() -> ExampleResponse:
    async with get_random() as result:
        return result


@api.query("/test/composed/{n:int}")
async def example_list_response(req: ExampleRequest, n: int) -> list[ExampleResponse]:
    async with get_composed(req.domain, n) as results:
        return results


@api.query("/test/doomed")
async def example_errors_logging_and_context() -> ExampleResponse:
    with context(foo="bar", baz=123, _dont_log_this="password123"): 
        try:
            raise RuntimeError("Oh noes!")
        except Exception as ex:
            log.exception(ex)
            raise


@api.query("/test/safe")
async def example_enforce_query_context_in_app() -> list[ExampleResponse]:
    try:
        async with looks_safe_enough() as results:
            return results
    except Unauthorized:
        log.warning("Phew! Can't accidentally run DB mutations in a query context!")
        raise


@api.query("/test/also_safe")
async def example_enforce_query_context_in_db() -> list[ExampleResponse]:
    try:
        async with really_is_dangerous() as results:
            return results
    except Unauthorized:
        log.warning("Phew! Can't accidentally run DB mutations in a query context!")
        raise


#:end
# ### Authentication and Authorization
#
# **Unrest** doesn't restrict authorization to API endpoints.
# Scope restrictions can be used in either API endpoints
# or functions deep within your codebase.
#
#:python


@api.authenticate()
async def authenticate_with_api_key(token: str) -> auth.User | None:
    props = await db._fetchrow("select id, email, claims from users where apikey = $1", token)
    if props:
        return auth.AuthenticatedUser(props["id"], props["email"], {}, props["claims"])
    return None


@api.query("/test/secret", Roles.admin) 
async def example_auth_restriction_on_endpoint() -> ExampleResponse:
    async with get_random() as result:
        return result

@api.query("/test/also_secret", Roles.any)
async def example_auth_restriction_not_on_endpoint():
    return not_an_api_endpoint()


@query(Roles.admin)
def not_an_api_endpoint():
    return {}


# #:end
# #
# # ### Background tasks
# #
# # **Unrest** makes defining and running backgroundtasks seamless.
# #
# #:python

# from asyncio import sleep as fake_work  # noqa

# from unrest.tasks import asynchronous, background, result, scheduled, synchronous  # noqa


# @background()
# async def fire_and_forget() -> None:
#     await fake_work(2)
#     return


# @scheduled("*/1 * * * *")
# async def runs_every_minute():
#     log.warning("Another minute has passed...")
#     return


# @synchronous(timeout=3.0)
# async def blocks_and_returns(secs: int) -> dict:
#     await fake_work(secs)
#     return {"ok": True}


# @asynchronous()
# async def returns_immediately(secs: int) -> dict:
#     await fake_work(secs)
#     return {"ok": True}


# #:end
# # In the API layer, these can then be used like so
# #:python


# @api.query("/test/background")
# async def example_background_task():
#     await fire_and_forget()
#     return {"ok": True}


# @api.query("/test/synchronous")
# async def example_synchronous_task():
#     return await blocks_and_returns(1)


# @api.query("/test/synchronous/timeout")
# async def example_synchronous_task_timeout():
#     # NB: will run for longer than timeout on task
#     return await blocks_and_returns(10)


# @api.query("/test/asynchronous")
# async def example_asynchronous_task():
#     task_id = await returns_immediately(1)
#     return {"task_id": task_id}


# @api.query("/test/asynchronous/{task_id:str}")
# async def example_asynchronous_task_retrieve(task_id):
#     return await result(task_id)


# #:end
# #
# # ### Conclusion
# #
# # That's pretty much it!
# #
# # I'm sure you *could* do all this yourself. But maybe you should get on with shipping that app? ;-)
# #
