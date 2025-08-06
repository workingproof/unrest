from asyncio import create_task, sleep
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import wraps
from inspect import iscoroutinefunction
from typing import Any, Awaitable, Callable

from taskiq import AsyncTaskiqDecoratedTask, InMemoryBroker, TaskiqScheduler
from taskiq.exceptions import ResultGetError, TaskiqResultTimeoutError
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend


from unrest.contexts import context, config, getLogger
from unrest.contexts._context import Context, operationalcontext, restorecontext, usercontext
from unrest.contexts.auth import AuthResponse, AuthenticatedUser, Tenant, TokenAuthFunction, UnauthenticatedUser, Unrestricted, UserPredicateFunction

log = getLogger(__name__)


class TaskTimeout(TaskiqResultTimeoutError):
    pass


class TaskNotReady(ResultGetError):
    pass

_started = False
_tasked: list[AsyncTaskiqDecoratedTask] = []
_scheduled: list[AsyncTaskiqDecoratedTask] = []
_pending: list[Callable] = []


if config.is_under_test():
    broker = InMemoryBroker()
    results = broker.result_backend
    scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])
else:
    uri = config.get("REDIS_URI", "redis://localhost:6379")
    if uri:
        results = RedisAsyncResultBackend(redis_url=uri, result_ex_time=3600) # type: ignore
        broker = ListQueueBroker(url=uri).with_result_backend(results) # type: ignore
        scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])
    else:
        raise RuntimeError("REDIS_URI must be set")


async def kiq(task: AsyncTaskiqDecoratedTask, *args, **kwargs):
    global _started
    if not _started:
        _started = True
        if len(_scheduled) > 0 or len(_tasked) > 0:
            await results.startup()
            await broker.startup()
            await scheduler.startup()

        if len(_pending) > 0:
            for f in _pending:
                create_task(f())
    await task.kiq(*args, **kwargs)



def background(pred: UserPredicateFunction = Unrestricted):
    def inner(f: Callable):
        if not iscoroutinefunction(f):
            raise RuntimeError("Background task %s is not async" % f.__name__)

        @wraps(f)
        async def inner(context:dict, fargs:list, fkwargs:dict, is_authenticated: bool) -> None:
            try:
                context["user"] = AuthenticatedUser(**context["user"]) if is_authenticated else UnauthenticatedUser(**context["user"])
                context["tenant"] = Tenant(**context["tenant"])
                context["_global"] = None
                ctx = Context(**context)
                with restorecontext(ctx): 
                    async with operationalcontext(True, f, pred):
                        await f(*fargs, **fkwargs)
            except Exception as e:
                log.exception("Error in background task %s: %s", f.__name__, e)

        _task = (broker.task())(inner)
        _tasked.append(_task)

        @wraps(f)
        async def wrapper(*args, **kwargs) -> None:
            await kiq(_task, context=context._ctx.copy(), 
                             fargs=list(args),
                             fkwargs=dict(kwargs),
                             is_authenticated=context.user.is_authenticated)

        return wrapper

    return inner



def scheduled(schedule):
    def inner(f: Callable):
        if not iscoroutinefunction(f):
            raise RuntimeError("Background task %s is not async" % f.__name__)

        @wraps(f)
        async def inner(*args, **kwargs):
            # NB: no context to set restore here, but should still set one up
            return await f(*args, **kwargs)

        _task = (broker.task(schedule=[{"cron": schedule}]))(inner)
        _scheduled.append(_task)
        return f

    return inner


# async def result(task_id):
#     if await results.is_result_ready(task_id):
#         try:
#             res = await results.get_result(task_id)
#         except Exception:
#             raise TaskNotReady("Please try again later")
#         res.raise_for_error()
#         return res.return_value
#     raise TaskNotReady("Please try again later")


# def synchronous(timeout=10.0):
#     def inner(f: callable):
#         if not iscoroutinefunction(f):
#             raise RuntimeError("Background task %s is not async" % f.__name__)

#         @wraps(f)
#         async def inner(*args, **kwargs):
#             context.set(False)
#             return await f(*args, **kwargs)

#         _task = (broker.task())(inner)
#         _tasked.append(_task)

#         @wraps(f)
#         async def wrapper(*args, **kwargs):
#             task = await _task.kiq(*args, **kwargs)
#             try:
#                 res = await task.wait_result(timeout=timeout)
#                 return res.return_value
#             except Exception:
#                 raise TaskTimeout()

#         return wrapper

#     return inner


# def asynchronous():
#     def inner(f: callable):
#         if not iscoroutinefunction(f):
#             raise RuntimeError("Background task %s is not async" % f.__name__)

#         @wraps(f)
#         async def inner(*args, **kwargs):
#             context.set(False)
#             return await f(*args, **kwargs)

#         _task = (broker.task())(inner)
#         _tasked.append(_task)

#         @wraps(f)
#         async def wrapper(*args, **kwargs):
#             task = await _task.kiq(*args, **kwargs)
#             return task.task_id

#         return wrapper

#     return inner


def lightweight(every=10.0):
    def inner(f: Callable):
        if not iscoroutinefunction(f):
            raise RuntimeError("Background task %s is not async" % f.__name__)

        async def wrapper():
            while True:
                try:
                    # TODO: restore context?
                    await f()
                except Exception:
                    pass
                await sleep(every)

        _pending.append(wrapper)
        return f

    return inner
