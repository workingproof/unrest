# Unrest

A lean and mean web framework for Python / Postgres.

## Quickstart

```
    $ pip install unrest
```

```python
from unrest import db, api, Server
from myapp import Widget

@db.query
def get_random_widget():
    return db.fetchrow("select * from widgets order by random() limit 1")


@api.query("/random")
async def get_a_random_widget() -> Widget:
    async with get_random_widget() as result:
        return result


server = Server()
```

```
    $ uvicorn app:server --host "0.0.0.0" --port 8080
```

## Next steps

* [Learn](tutorial) what **Unrest** has to offer a more realistic codebase

* [Compare](comparison) **Unrest** with **FastAPI** in terms of ergonomics and performance 