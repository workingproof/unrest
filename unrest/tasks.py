from asyncio import create_task, sleep
from contextlib import asynccontextmanager
from functools import wraps
from inspect import iscoroutinefunction

from taskiq import TaskiqScheduler
from taskiq.exceptions import ResultGetError, TaskiqResultTimeoutError
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend


from contexts import context, config, getLogger

log = getLogger(__name__)


class TaskTimeout(TaskiqResultTimeoutError):
    pass


class TaskNotReady(ResultGetError):
    pass


# if config.is_under_test() is not None:
#     self.started = False
#     self.broker = InMemoryBroker()
#     self.results = self.broker.result_backend
#     self.scheduler = TaskiqScheduler(broker=self.broker, sources=[LabelScheduleSource(self.broker)])
# else:
uri = config.get("UNREST_REDIS_URI", "redis://localhost:6379")
results = RedisAsyncResultBackend(redis_url=uri, result_ex_time=3600)
broker = ListQueueBroker(url=uri).with_result_backend(results)
scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])

_tasked = []
_scheduled = []
_pending = []


@asynccontextmanager
async def lifespan(app):
    if len(_scheduled) > 0 or len(_tasked) > 0:
        await results.startup()
        await broker.startup()
        await scheduler.startup()

    if len(_pending) > 0:
        for f in _pending:
            create_task(f())
    yield {}


async def result(task_id):
    if await results.is_result_ready(task_id):
        try:
            res = await results.get_result(task_id)
        except Exception:
            raise TaskNotReady("Please try again later")
        res.raise_for_error()
        return res.return_value
    raise TaskNotReady("Please try again later")


def scheduled(schedule):
    def inner(f: callable):
        if not iscoroutinefunction(f):
            raise RuntimeError("Background task %s is not async" % f.__name__)

        @wraps(f)
        async def inner(*args, **kwargs):
            context.set(False)
            return await f(*args, **kwargs)

        _task = (broker.task(schedule=[{"cron": schedule}]))(inner)
        _scheduled.append(_task)
        return f

    return inner


def background():
    def inner(f: callable):
        if not iscoroutinefunction(f):
            raise RuntimeError("Background task %s is not async" % f.__name__)

        @wraps(f)
        async def inner(*args, **kwargs):
            context.set(False)
            return await f(*args, **kwargs)

        _task = (broker.task())(inner)
        _tasked.append(_task)

        @wraps(f)
        async def wrapper(*args, **kwargs):
            await _task.kiq(*args, **kwargs)

        return wrapper

    return inner


def synchronous(timeout=10.0):
    def inner(f: callable):
        if not iscoroutinefunction(f):
            raise RuntimeError("Background task %s is not async" % f.__name__)

        @wraps(f)
        async def inner(*args, **kwargs):
            context.set(False)
            return await f(*args, **kwargs)

        _task = (broker.task())(inner)
        _tasked.append(_task)

        @wraps(f)
        async def wrapper(*args, **kwargs):
            task = await _task.kiq(*args, **kwargs)
            try:
                res = await task.wait_result(timeout=timeout)
                return res.return_value
            except Exception:
                raise TaskTimeout()

        return wrapper

    return inner


def asynchronous():
    def inner(f: callable):
        if not iscoroutinefunction(f):
            raise RuntimeError("Background task %s is not async" % f.__name__)

        @wraps(f)
        async def inner(*args, **kwargs):
            context.set(False)
            return await f(*args, **kwargs)

        _task = (broker.task())(inner)
        _tasked.append(_task)

        @wraps(f)
        async def wrapper(*args, **kwargs):
            task = await _task.kiq(*args, **kwargs)
            return task.task_id

        return wrapper

    return inner


def lightweight(every=10.0):
    def inner(f: callable):
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
