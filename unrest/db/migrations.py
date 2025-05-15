import os
import random
import re
import string
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import AsyncGenerator
from urllib.parse import urlparse

import asyncclick as click
import asyncpg

from contexts import config


def role(role):
    dsn = config.get(role)
    if dsn is None:
        return None
    return urlparse(dsn)


def _deets():
    schema = "public" # TODO
    admin = role("POSTGRES_ADMIN_URI")
    if admin is None:
        raise RuntimeError("POSTGRES_ADMIN_URI role is required")
    return schema, admin


@asynccontextmanager
async def connection(role) -> AsyncGenerator[asyncpg.connection.Connection, None]:
    dsn = config.get(role)
    if dsn is None:
        raise RuntimeError("No DSN for role %s" % role)
    conn = await asyncpg.connect(dsn)
    yield conn
    await conn.close()


@asynccontextmanager
async def lock() -> AsyncGenerator[asyncpg.connection.Connection, None]:
    name = 123456
    async with connection("POSTGRES_ADMIN_URI") as conn:
        res = await conn.fetchrow("SELECT pg_try_advisory_lock($1) as lock", name)
        if not res["lock"]:
            raise RuntimeError("Unable to aquire DB lock '%s'" % name)
        try:
            yield conn
        except Exception as ex:
            raise ex
        finally:
            res = await conn.fetchrow("""SELECT pg_advisory_unlock($1) as unlock""", name)
            if not res["unlock"]:
                raise RuntimeError("Unable to release DB lock '%s'" % name)


async def init():
    """
    Setup the database and admin user
    """
    _, admin = _deets()
    async with connection("POSTGRES_SUPER_URI") as db:
        try:
            await db.execute("DROP DATABASE IF EXISTS %s" % admin.path[1:])  #  WITH FORCE
            await db.execute("CREATE DATABASE %s" % (admin.path[1:]))  #  OWNER %s
        except Exception as ex:
            print("ERROR initialising database: %s" % ex)
            pass

        try:
            await db.execute("DROP USER IF EXISTS %s" % admin.username)
            await db.execute("CREATE USER %s WITH /*SUPERUSER*/ CREATEROLE LOGIN ENCRYPTED PASSWORD '%s'" % (admin.username, admin.password))
        except Exception as ex:
            print("ERROR initialising database: %s" % ex)
            pass

        try:
            await db.execute("GRANT ALL ON DATABASE %s TO %s" % (admin.path[1:], admin.username))
            await db.execute("GRANT CREATE ON DATABASE %s TO %s" % (admin.path[1:], admin.username))
            await db.execute("ALTER DATABASE %s OWNER TO %s" % (admin.path[1:], admin.username))
            # await db.execute("ALTER DATABASE %s SET timezone = 'UTC'" % admin.path[1:])
            await db.execute("ALTER USER %s WITH SUPERUSER" % (admin.username))
        except:  # noqa
            pass


async def reset():
    """
    Reset the database and schema
    """
    schema, admin = _deets()

    async with connection("POSTGRES_ADMIN_URI") as db:
        # Create empty schema and grant admin control
        tables = await db.fetch("SELECT tablename FROM pg_tables WHERE schemaname = $1", schema)
        if len(tables) == 0:
            if schema != "public":
                await db.execute("CREATE SCHEMA IF NOT EXISTS %s" % schema)
                await db.execute("GRANT USAGE, CREATE ON SCHEMA %s TO %s" % (schema, admin.username))
                await db.execute("GRANT ALL ON SCHEMA %s TO %s" % (schema, admin.username))
                await db.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA %s TO %s" % (schema, admin.username))
                await db.execute("GRANT CREATE ON SCHEMA %s to %s;" % (schema, admin.username))
                await db.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %s to %s;" % (schema, admin.username))
        else:
            for tbl in tables:
                try:
                    await db.execute("DROP TABLE IF EXISTS %s CASCADE" % tbl["tablename"])
                    print("DROPPED %s" % tbl["tablename"])
                except Exception as ex:
                    print("ERROR DROPPING %s : %s" % (tbl["tablename"], ex))

        await db.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA %s' % schema)

        # create roles and application accounts
        # neon needs rhe roles to have passwords even if no login
        try:
            await db.execute(
                """
                CREATE ROLE readonly_access WITH PASSWORD '%(pass)s';
                CREATE ROLE readwrite_access WITH PASSWORD '%(pass)s';        
                """
                % {"pass": "".join(random.choices(string.ascii_lowercase + string.ascii_uppercase + string.digits, k=20))}
            )
        except Exception as ex:
            print("ERROR creating roles: %s" % ex)
            pass

        await db.execute(
            """
            GRANT USAGE ON SCHEMA %(schema)s TO readonly_access;                                              
            GRANT SELECT ON ALL TABLES IN SCHEMA %(schema)s TO readonly_access;
            ALTER DEFAULT PRIVILEGES FOR ROLE readonly_access IN SCHEMA %(schema)s GRANT SELECT ON TABLES TO readonly_access;

            GRANT USAGE ON SCHEMA %(schema)s TO readwrite_access;
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %(schema)s to readwrite_access;   
            GRANT USAGE ON ALL SEQUENCES IN SCHEMA %(schema)s TO readwrite_access;
            ALTER DEFAULT PRIVILEGES FOR ROLE readwrite_access IN SCHEMA %(schema)s GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO readwrite_access;
            ALTER DEFAULT PRIVILEGES FOR ROLE readwrite_access IN SCHEMA %(schema)s GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO readwrite_access;
            """
            % {"schema": schema}
        )

        # create readonly/readwrite login accounts
        slave = role("POSTGRES_QUERY_URI")
        if slave is not None:
            if slave.path != admin.path:
                raise RuntimeError("Misconfigured POSTGRES_QUERY_URI")
            await db.execute("DROP USER IF EXISTS %s" % slave.username)
            await db.execute("CREATE USER %s WITH INHERIT LOGIN ENCRYPTED PASSWORD '%s'" % (slave.username, slave.password))
            await db.execute("GRANT readonly_access TO %s" % slave.username)

        master = role("POSTGRES_MUTATE_URI")
        if master is not None:
            if master.hostname != admin.hostname or master.path != admin.path:
                raise RuntimeError("Misconfigured POSTGRES_MUTATE_URI")
            await db.execute("DROP USER IF EXISTS %s" % master.username)
            await db.execute("CREATE USER %s WITH INHERIT LOGIN ENCRYPTED PASSWORD '%s'" % (master.username, master.password))
            await db.execute("GRANT readwrite_access TO %s" % master.username)

    # initialise control tables
    async with lock() as db:
        await db.execute(
            """            
            CREATE TABLE %(schema)s._migrations (
                version text PRIMARY KEY,
                description text NOT NULL,
                sql text NOT NULL,
                executed_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
            );
        """
            % {"schema": schema}
        )


async def migrate(execute: bool = False, dryrun: bool = True):
    """
    Apply all (outstanding) migrations
    """
    schema, _ = _deets()

    def find_migrations(migrations_dir=".", current_version: str = None):
        migrations = []
        for path, dirnames, filenames in os.walk(migrations_dir):
            for file in filenames:
                if file.endswith(".sql"):
                    match = re.match(r"(\d{12})__(.*?)\.sql", file)
                    if match:
                        click.echo("%s...." % file)
                        migrations.append({
                            "path": os.path.join(path, file),
                            "file": file,
                            "version": match.group(1),
                            "title": match.group(2),
                            "applied": None if current_version is None else current_version >= match.group(1)
                        })
        migrations.sort(key=lambda x: x["version"])
        return migrations

    async with lock() as db:
        result = await db.fetchrow("SELECT MAX(version) as latest_version FROM %s._migrations" % schema)
        current_version = result["latest_version"]
        click.echo("Last migration applied: %s" % current_version)
        sorted_migrations = find_migrations(current_version=current_version)
        applicable_migrations = (
            [m for m in sorted_migrations if not m["applied"]]
            if current_version
            else sorted_migrations
        )
        applicable = len(applicable_migrations)
        click.echo("Migrations to apply: %d" % applicable)

        if execute:
            tx = db.transaction()
            await tx.start()
            try:
                for i, migration in enumerate(applicable_migrations):
                    try:
                        with open(migration["path"]) as f:
                            script_contents = f.read()
                            await db.execute(script_contents)
                            await db.execute(
                                "INSERT INTO %s._migrations (version, description, sql) VALUES ($1, $2, $3)" % schema,
                                migration["version"],
                                migration["title"],
                                script_contents,
                            )
                            click.echo("Applied %d/%d %s" % (i + 1, applicable, migration["file"]))
                    except Exception as ex:
                        click.echo("ERROR %d/%d %s: %s" % (i + 1, applicable, migration["file"], str(ex)))
                        raise

                await db.execute("GRANT SELECT ON ALL TABLES IN SCHEMA %s to readonly_access" % schema)
                await db.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %s to readwrite_access" % schema)
                await db.execute("REVOKE ALL ON %s._migrations FROM readonly_access" % schema)
                await db.execute("REVOKE ALL ON %s._migrations FROM readwrite_access" % schema)
                await tx.commit()
            except Exception:
                await tx.rollback()
            finally:
                if dryrun:
                    await tx.rollback()

        else:
            for i, migration in enumerate(applicable_migrations):
                click.echo("Pending %d/%d %s" % (i + 1, applicable, migration))


@contextmanager
def create(description):
    migrations_dir = "."
    file_creation_time = datetime.utcnow()
    file_title = re.sub(r"\W+", "_", description.lower())
    file_name = "%s__%s.sql" % (file_creation_time.strftime("%Y%m%d%H%M"), file_title)
    up_path = os.path.join(migrations_dir, file_name)
    if os.path.exists(up_path):
        raise RuntimeError("Migration already exists")
    with open(up_path, "w") as f:
        yield f
