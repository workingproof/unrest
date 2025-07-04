# # Tutorial
#
# The following should be 80% sufficient if you are already familiar with
# [Flask](https://flask.palletsprojects.com/en/3.0.x/), [FastAPI](https://fastapi.tiangolo.com/)
# or [Django](https://www.django-rest-framework.org/). It's not rocket science.
#
# However, to avoid being misled by prior experience with those frameworks,
# there are a couple of high-level points to appreciate about the design of **Unrest**:
#
# 1. **It is solely focussed on rapidly developing high-performance web services with Postgres.**
#    It does this by surrounding your application with a thin layer built on [Starlette](https://www.starlette.io/)
#    and [Asyncpg](https://magicstack.github.io/asyncpg/current/), sets things up nicely and 
#    then gets out of the way. Although the framework has some rather nifty features, the abstractions are 
#    all lightweight. Batteries are *not* included.
# 2. **It largely eschews REST semantics -- hence the name.** Instead, it is built around the concept of 
#     [contexts](/contexts) which propogate from API entrypoints, down through your application 
#     logic and into the storage layer. The framework sets up these contexts, which your code then interacts with 
#     rather than directly interacting with the framework.
#
# This context-based approach keeps the codebase focussed on application layer logic, without props drilling, 
# dependency injection or deep dependencies on transport layer details.
#
# The intention is to maintain productivity but preserve options for if and when priorities change from 
# hacking velocity to operational stability and scalability.
#
#
# ## Operational context
#
# The fundamental context in **Unrest** are `query` and `mutate` operations.
#
# The explicit distinction between read and write contexts provides the primitive for higher-level functionality: 
# from scalable database access patterns to role-based access control.
#
# ### State management
#
# The lowest layer of reads and writes are to the database.
#
# **Unrest** is is deliberately not an ORM -- but it still makes
# working programmatically with Postgres quite a lot nicer:
#
# * All database access is abstracted behind dedicated functions.
# * Each function can be annotated as a `query` or `mutate`. Mutations won't (by default) run in a
#   `query` context. This is enforced by both **Unrest** and Postgres.
# * Functions do not hit the database directly, but rather return a query "fragment": 
#   an `async callable` that will hit the database when invoked.
# * Due to their delayed execution, fragments can be composed into more complex queries that retain a very readable CTE structure.
#
# When getting started, you can mostly treat these annotations as syntactic sugar. 
# In production, they provide a basic mechanism for safely growing and operating 
# your system. 
#
# For example:
#
#:python

from unrest import db

@db.query
def get_random_user():
    return db.fetchrow("select * from users order by random() limit 1")


@db.query
def get_users_by_email_domain(domain: str):
    return db.fetch(
        """
        select * from users
        where email like '%@' || $1
        """,
        domain,
    )


@db.query
def get_some_users_by_email_domain(domain: str, n=5):
    # Reuse an existing query rather than duplicate the SQL 
    # or mess around with SQL string manipulation helpers. 
    # Note, this produces and executes a single CTE query.
    return db.fetch(
        """
        select id, email 
        from $1
        order by random()
        limit $2 
        """,
        get_users_by_email_domain(domain),
        n,
    )


@db.mutate
def this_is_dangerous():
    return db.fetch("delete from users where true returning *")


@db.query
def this_is_misleading():
    # NB: This query will not run because it depends on a mutation
    oops = this_is_dangerous()
    return db.fetch("select * from $1", oops)


@db.query
def this_is_also_misleading():
    # NB: This query will also not run because the database connection 
    #     is readonly in a query context
    return db.fetch("delete from users where true returning *")


async def just_a_function() -> str:
    # NB: Fragments can be directly invoked as a context manager
    async with get_random_user() as result:
        return result["email"]

#:end
# ### API routing
#
# The highest layer of reads and writes are API endpoints, which largely set the context for all downstream logic.
#
# Typical API endpoints are dedicated chunks of functionality: a mess of routing, authorization, (de)serialisation 
# and validation. All this may be interleaved with business logic or, as is better practice, delegate to a 
# corresponding layer of pure business logic. 
#
# **Unrest** API endpoints are **not** HTTP request handlers. Request handling is performed within the framework based on the function annotations in decorators and type signatures. 
# API endpoints are essentially regular functions and can be invoked as such, without overhead. 
#
# This separation of the HTTP request/response pipeline and the application layer entry-point 
# functionality allows for directly testing and composing API functions.
#
#:python

from unrest import api, Payload, Unauthorized


class ExampleResponse(Payload):
    id: str
    email: str


class ExampleRequest(Payload):
    domain: str


@api.query("/test/random")
async def example_object_response() -> ExampleResponse:
    async with get_random_user() as result:
        return result


@api.query("/test/composed/{n:int}")
async def example_list_response(req: ExampleRequest, n: int) -> list[ExampleResponse]:
    async with get_some_users_by_email_domain(req.domain, n) as results:
        return results


@api.query("/test/safe")
async def example_enforce_query_context_in_app() -> list[ExampleResponse]:
    try:
        async with this_is_dangerous() as results:
            return results
    except Unauthorized:
        # Phew! Can't accidentally run DB mutations in an API query context!
        raise


#:end
#
#
# ## User context
#
# Until now we have focussed on partitioning logic into read and write operational contexts. 
# 
# With this in place, the next most important contextual information is *"who is trying to perform this operation?"* 
# and, following immediately, *"are they allowed to do that?"*
#
# That is, business logic has a `user` context: distinct from the operational context and distinct from how that user context may be established and propogated.
#
# **Unrest** isn't overly prescriptive about how you model users or permissions. It assumes that knowing the user's identity, 
# their opaque "claims", and the operational context will all be relevant to an authorization decision. This is sufficient 
# for many types of role-based access control (RBAC) but more complex models can be built on this foundation.
# 
# Because context is propagated, **Unrest** doesn't limit authorization guards to API endpoints. Restrictions can be enforced on API endpoints, database queries,
# or pure logic functions deep within your codebase.
#
#
# ### Authentication
#
# Authentication is a mapping from an opaque string `token` to a `user`. **Unrest** can pull tokens 
# from HTTP headers and Cookies and it is simply your job to implement the mapping.
#
#:python

from unrest import db, api, auth, http

@api.authentication("bearer")
async def authenticate_with_api_key(token: str, url: http.URL) -> auth.AuthResponse:
    # This is a trivial example. Use any method you like.
    props = await db._fetchrow("select id, email, claims from users where apikey = $1", token)
    if props:
        return auth.AuthenticatedUser(identity=props["id"], display_name=props["email"], claims=props["claims"]), None
    return auth.UnauthenticatedUser(), None


#:end
#
# TODO: Users
#
# ### Authorization
#
# Authorization is a mapping from a `user` and `operational` context to a boolean decision. 
#
# The 80/20 solution here is a set of "roles" or "claims" that can be assigned to 
# users and asserted before invoking a function. **Unrest** supports this model out of the box.
#
# Assertions are boolean expressions that can be composed using `&`, `|` and `~` operators.
#
# For API endpoints, **Unrest** will assert that a user is at least authenticated by default. Public-facing endpoints 
# must be explicitly marked as such.
#
#:python

from unrest import auth, api, mutate, context


class Roles:
    # This isn't necessary but keeps things tidy
    admin    = auth.Claim("admin")
    support  = auth.Claim("support")
    customer = auth.Claim("customer")
    staff    = auth.Claim("admin") | auth.Claim("support") 

@api.query("/test/healthcheck", auth.Unrestricted) 
async def example_public_endpoint() -> ExampleResponse:
    return ExampleResponse(id="123", email="foo@example.com")


@api.query("/test/secret", Roles.admin) 
async def example_auth_restriction_on_endpoint() -> ExampleResponse:
    async with get_random_user() as result:
        return result

@api.mutate("/test/also_secret", Roles.staff)
async def example_auth_restriction_not_on_endpoint():
    return await not_an_api_endpoint()


@mutate(auth.UserIsAuthenticated & ~Roles.support) 
async def not_an_api_endpoint():
    return {"hello": context.user.display_name}


#:end
#
#
# ## Custom context and logging
#
# One of the benefits of tracking context is that it can be recovered for debugging, incident management and usage analytics.
#
# **Unrest** provides a logger that emits structured logs enriched with contextual information.
#
# Arbitrary custom information can be added to the context in the form of key-value pairs:
#
# * This works as a context manager and applies only for the duration of the block
# * Keys that start with an underscore (`_`) will not be logged
#
# For example
#
#:python

from unrest import context, getLogger

log = getLogger(__name__)

@api.query("/test/doomed")
async def example_errors_logging_and_context() -> ExampleResponse:
    with context(foo="bar", baz=123, _dont_log_this="password123"): 
        try:
            raise RuntimeError("Oh noes!")
        except Exception as ex:
            log.exception(ex)
            raise

#:end
#
# will emit
#
# ```json
#    {
#      "filename": "quickstart.py",
#      "lineno": 280,
#      "message": "Oh noes!",
#      "exc_info": "Traceback (most recent call last):\n ...",
#      "taskName": "Task-2",
#      "context": {
#        "id": "d23b6634-9d23-4a5b-9a6a-8f99ce3e6b73",
#        "entrypoint": "tests.quickstart.example_errors_logging_and_context",
#        "mutation": false,
#        "properties": {
#          "foo": "bar",
#          "baz": 123
#        }
#      },
#      "user": {
#        "id": "9d521ae6-d088-4070-a28a-c23410643392",
#        "display_name": "bar@example.com",
#        "properties": {}
#      },
#      "logger": "tests.quickstart",
#      "timestamp": "2025-06-03T09:45:22.487+00:00",
#      "loglevel": "ERROR"
#    }
# ```
# ### Background tasks
#
# **Unrest** makes defining and running backgroundtasks seamless.
#
# Context is propagated to background tasks, so you can continue 
# to execute and log under the same context as the triggering request.
# Background tasks always have a `mutation` operational context.
#
#:python

from asyncio import sleep as fake_work  # noqa

from unrest.tasks import background

@background()
async def fire_and_forget(job_id) -> None:
    # NB: context is propagated across to the background job
    await fake_work(2)
    job = await db._fetchrow("update bgjobs set completed_at=now() where id=$1 and context_id=$2 and user_id=$3 returning *", job_id, context.id, context.user.identity)
    assert job is not None

#:end
# In the API layer, these can then be used like so
#:python


@api.mutate("/test/background")
async def example_background_task():
    job = await db._fetchrow("insert into bgjobs (context_id, user_id) values ($1, $2) returning *", context.id, context.user.identity)
    await fire_and_forget(job["id"])
    return job

@api.query("/test/background/{jobid}")
async def example_background_task_pickup(jobid: str):
    job = await db._fetchrow("select * from bgjobs where id=$1", jobid)
    assert job is not None
    assert str(job["context_id"]) != str(context.id)
    assert str(job["user_id"]) == str(context.user.identity)
    return job


#:end
#
# ### Conclusion
#
# That's pretty much it!
#
# I'm sure you *could* do all this yourself. But maybe you should get on with shipping that app? ;-)
#
