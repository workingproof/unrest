from unrest import Application, auth, broker, context, db, getLogger, scheduler  # noqa

app = Application("html")
log = getLogger(__name__)


@db.query
@auth.scope("user")
def get_todos():
    return db.fetch("select * from todos where user_id=$1 order by created_at desc", context.user.identity)


@db.mutate
@auth.scope("user")
def put_todo(description):
    return db.fetchrow("insert into todos (user_id, description) values ($1, $2) returning *", context.user.identity, description)


@db.mutate
@auth.scope("user")
def delete_todo(id):
    return db.execute("delete from todos where todo_id = $1", id)


@auth.scheme("session")
async def authenticate_via_cookie(token: str):
    try:
        user = await db._fetchrow("select user_id::text, username from users where user_id=$1", token)
        if user is not None:
            return auth.User(user, claims=["user"])
    except:  # noqa
        pass


@app.post("/login")
async def login(email: str = None):
    user = await db._fetchrow("select * from users where username=$1", email)
    if user is None:
        return app.abort(401)
    headers = {"Set-Cookie": "session=" + str(user["user_id"]) + "; Path=/; HttpOnly"}
    return app.redirect("/", status_code=303, headers=headers)


@app.get("/logout")
async def logout():
    headers = {"Set-Cookie": "session=; Path=/; HttpOnly"}
    return app.redirect("/", status_code=303, headers=headers)


@app.get("/")
async def homepage():
    try:
        query = get_todos()
        return app.render("index.html", {"todos": await query()})
    except:  # noqa
        return app.render("index.html")


@app.post("/add")
async def add(description: str = None):
    try:
        mutation = put_todo(description)
        await mutation()
    except:  # noqa
        pass
    return app.redirect("/", status_code=303)


@app.get("/remove/{id}")
async def remove(id):
    try:
        with context.unsafe():
            mutation = delete_todo(id)
            await mutation()
    except:  # noqa
        pass
    return app.redirect("/", status_code=303)
