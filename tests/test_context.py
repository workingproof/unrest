from pytest import raises
from contextlib import contextmanager
from unrest.contexts import context, usercontext, query, mutate, auth, ContextError, config, Unauthorized

class Roles:
    foo: auth.UserPredicate = auth.Claim("foo")
    bar: auth.UserPredicate = auth.Claim("bar")


@contextmanager
def user(**kwargs):
    yield auth.AuthenticatedUser(
        id="1",
        display_name="testuser",
        props={},
        claims=kwargs)

@contextmanager
def nonuser(**kwargs):
    yield auth.UnauthenticatedUser(
        id="1",
        display_name="testuser",
        props={},
        claims=kwargs)


@query(Roles.foo | Roles.bar)
async def some_query(val: str):
    return {"ok": True, "val": val}

@mutate(Roles.foo)
async def some_mutate(val: str):
    return {"ok": True, "val": val}

@query(Roles.foo)
async def bad_query(val: str):
    return await some_mutate(val)

async def test_is_under_test():
    assert config.is_under_test()

async def test_happy_path():
    val = "test"
    expected = {"ok": True, "val": val}

    # Both calls succeed if has write perms
    with user(foo=True) as some_user:
        with usercontext(some_user):
            result = await some_query(val)
            assert result == expected

        with usercontext(some_user):
            result = await some_mutate(val)
            assert result == expected

        with usercontext(some_user):
            with raises(ContextError):
                await bad_query(val)
  


    # Only query succeeds with query perms
    with user(foo=False) as some_user:
        with usercontext(some_user):
            result = await some_query(val)
            assert result == expected

        with usercontext(some_user):
            with raises(Unauthorized):
                result = await some_mutate(val)
                assert result == expected

        with usercontext(some_user):
            with raises(ContextError):
                await bad_query(val)


    # None succeed without perms
    with user() as some_user:
        with usercontext(some_user):
            with raises(Unauthorized):
                result = await some_query(val)
                assert result == expected

        with usercontext(some_user):
            with raises(Unauthorized):
                result = await some_mutate(val)
                assert result == expected

    # Logical expressions
    with user(bar=False) as some_user:
        with usercontext(some_user):
            result = await some_query(val)
            assert result == expected

            with raises(Unauthorized):
                await some_mutate(val)
                
async def test_escalation():
    val = "test"
    expected = {"ok": True, "val": val}

    with nonuser(foo=True) as some_user:
        with usercontext(some_user):
            with raises(Unauthorized):
                await some_query(val)

            with user(foo=True) as some_user:
                with usercontext(some_user):
                    result = await some_query(val)
                    assert result == expected

