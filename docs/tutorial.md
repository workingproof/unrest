# Tutorial

The following should be 80% sufficient if you are already familiar with
[Flask](https://flask.palletsprojects.com/en/3.0.x/), [FastAPI](https://fastapi.tiangolo.com/)
or [Django](https://www.django-rest-framework.org/). It's not rocket science.

However, to avoid being misled by prior experience with those frameworks,
there are a couple of high-level points to appreciate about the design of **Unrest**:

1. **It is solely focussed on rapidly developing high-performance web apps with Postgres.**
It does this by surrounding your application with a thin layer built on [Starlette](https://www.starlette.io/)
and [Asyncpg](https://magicstack.github.io/asyncpg/current/), sets things up nicely and 
then gets out of the way. Although the framework has some rather nifty features, the abstractions are 
all lightweight. Batteries are *not* included.
2. **It largely eschews REST semantics -- hence the name.** Instead, it is built around the concept of 
`query` and `mutate` [contexts](/contexts) which propogate from API entrypoints, down through your application 
logic and into the storage layer. The framework sets up these contexts, which your code then interacts with 
rather than directly interacting with the framework.

This context-based approach keeps the codebase focussed on business logic. No props drilling, 
dependency injection or creating deep dependencies on e.g. HTTP peculiarities.

The explicit distinction between read and write contexts provides a primitive for higher-level functionality: 
from role-based access control to scalable database access patterns.

The intention is to maintain productivity but preserve options for if and when priorities change from 
hacking velocity to operational stability and scalability.


## Contexts

### State management

The lowest layer of reads and writes are to the database.

**Unrest** is is deliberately not an ORM -- but it still makes
working programmatically with Postgres quite a lot nicer:

* All database access is abstracted behind dedicated functions.
* Each function can be annotated as a `query` or `mutate`. Mutations won't (by default) run in a
`query` context. This is enforced by both **Unrest** and Postgres.
* Functions do not hit the database directly, but rather return a "Fragment": 
an `async callable` that will hit the database when invoked.
* Fragments can be composed into more complex queries with a very readable CTE.

When getting started, you can mostly treat these annotations as syntactic sugar. 
In production, they provide a basic mechanism for safely growing and operating 
your system. 

For example:


```python

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
    # or mess around with SQL string manipulation. Note that
    # this results in a single CTE query.
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
    # NB: annotated as a query...but still will not run because
    #     the database connection for queries will be readonly
    return db.fetch("delete from users where true returning *")


async def just_a_function():
    # NB: Fragments can be directly invoked as context managers
    async with get_random_user() as result:
        return result

```

### API routing

The highest layer of reads and writes are API endpoints, which largely set the context for all downstream logic.

Typical API endpoints are dedicated chunks of functionality: a mess of routing, authorization, (de)serialisation 
and validation. All this may be interleaved with business logic or, as is better practice, delegated to a 
corresponding layer of pure business logic. 

**Unrest** performs all this automatically and exposes key information extracted from the request behind the provided context. 
API endpoints are thus largely regular functions, albeit with some annotations, focused more directly on business logic. 


```python

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


```


In contrast to existing web frameworks, functions like `example_list_response` are 
**not** dedicated HTTP request handlers. They can be invoked directly, and without overhead, 
e.g.

```
objs = example_list_response(ExampleRequest(domain="example.com"), 5)
```

However, in the context of an HTTP request, **Unrest** will automatically handle routing 
of the request based on the annotation and (de)serialisation of the request and response 
payloads based on the function signature type annotations. 

The separation of the HTTP request/response pipeline and the application layer entry-point 
functionality allows for directly testing and composing API functions.


### Users and permissions

Until now we have focussed on partitioning logic into read and write contexts. 

Once you have this in place, the next most important contextual information is *"who is trying to perform this read or write operation?"* 
and, following immediately, *"are they allowed to do that?"*

That is, our logic has a `user` context, distinct from how that may be established and propogated.

**Unrest** isn't very prescriptive about your user or auth model. It assumes that knowing the user, 
their "claims", and the read or write context will all be relevant to a decision. This is sufficient 
for role-based access control (RBAC) but more complex models can be built on that foundation.

It also doesn't limit authorization to API endpoints. Restrictions can be enforced on API endpoints, database queries,
or pure logic functions deep within your codebase.


#### Authentication

Authentication is a mapping from an opaque string `token` to a `user`. **Unrest** can pull tokens 
from HTTP headers and Cookies and it is simply your job to implement the mapping.


```python

from unrest import db, api, auth

@api.authenticate("bearer")
async def authenticate_with_api_key(token: str) -> auth.User | None:
    # This is a trivial example. Use any method you like.
    props = await db._fetchrow("select id, email, claims from users where apikey = $1", token)
    if props:
        return auth.AuthenticatedUser(props["id"], props["email"], {}, props["claims"])
    return None


```


#### Authorization

Authorization is a mapping from a `user` and a `context` to a boolean decision. 

The 80/20 solution here is a set of "roles" or "claims" that can be assigned to 
users and asserted before invoking a function. **Unrest** supports this model out of the box.

Assertions are boolean expressions that can be composed using `&`, `|` and `~` operators.


```python

from unrest import auth, api, query


class Roles:
    # This isn't necessary but keeps things tidy
    admin = auth.Claim("admin")
    anybody = auth.UserIsAuthenticated

@api.query("/test/secret", Roles.admin & Roles.anybody) 
async def example_auth_restriction_on_endpoint() -> ExampleResponse:
    async with get_random_user() as result:
        return result

@api.query("/test/also_secret", Roles.admin | Roles.anybody)
async def example_auth_restriction_not_on_endpoint():
    return not_an_api_endpoint()


@query(Roles.anybody & ~Roles.admin) 
def not_an_api_endpoint():
    return {}


```

By default, **Unrest** will assert that the user is authenticated on API endpoints. Public-facing endpoints 
must be explicitly marked as such.


### User-defined context and logging


```python

@api.query("/test/doomed")
async def example_errors_logging_and_context() -> ExampleResponse:
    with context(foo="bar", baz=123, _dont_log_this="password123"): 
        try:
            raise RuntimeError("Oh noes!")
        except Exception as ex:
            log.exception(ex)
            raise

```


### Background tasks

**Unrest** makes defining and running backgroundtasks seamless.


```python

from asyncio import sleep as fake_work  # noqa

from unrest.tasks import asynchronous, background, result, scheduled, synchronous  # noqa


@background()
async def fire_and_forget() -> None:
    await fake_work(2)
    return


@scheduled("*/1 * * * *")
async def runs_every_minute():
    log.warning("Another minute has passed...")
    return


@synchronous(timeout=3.0)
async def blocks_and_returns(secs: int) -> dict:
    await fake_work(secs)
    return {"ok": True}


@asynchronous()
async def returns_immediately(secs: int) -> dict:
    await fake_work(secs)
    return {"ok": True}


```

In the API layer, these can then be used like so

```python


@api.query("/test/background")
async def example_background_task():
    await fire_and_forget()
    return {"ok": True}


@api.query("/test/synchronous")
async def example_synchronous_task():
    return await blocks_and_returns(1)


@api.query("/test/synchronous/timeout")
async def example_synchronous_task_timeout():
    # NB: will run for longer than timeout on task
    return await blocks_and_returns(10)


@api.query("/test/asynchronous")
async def example_asynchronous_task():
    task_id = await returns_immediately(1)
    return {"task_id": task_id}


@api.query("/test/asynchronous/{task_id:str}")
async def example_asynchronous_task_retrieve(task_id):
    return await result(task_id)


```


### Conclusion

That's pretty much it!

I'm sure you *could* do all this yourself. But maybe you should get on with shipping that app? ;-)

