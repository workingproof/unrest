import os
import shutil
from pathlib import Path

import asyncclick as click

import unrest.config as config
from unrest import migrations


@click.group()
def cli():
    pass


@cli.group()
def db():
    pass


@cli.command()
async def init():
    """
    Initialise a repo with basic structure
    """
    try:
        _files = []
        _dirs = []
        root = str(Path(__file__).parent / "init")
        for cur_path, directories, files in os.walk(root):
            rel_path = cur_path.replace(root, ".")
            for dir in directories:
                # dsrc = os.path.join(root, cur_path, dir)
                dtgt = os.path.join(rel_path, dir)
                if os.path.exists(dtgt):
                    raise RuntimeError("Directory exists: %s" % dtgt)
                _dirs.append(dtgt)
            for file in files:
                fsrc = os.path.join(root, cur_path, file)
                ftgt = os.path.join(rel_path, file)
                if os.path.exists(ftgt):
                    raise RuntimeError("File exists: %s" % ftgt)
                _files.append((fsrc, ftgt))
        for dir in _dirs:
            os.mkdir(dir)
        for file in _files:
            shutil.copyfile(*file)

    except Exception as ex:
        print("ERROR: %s" % str(ex))


@db.command()
async def reset():
    """
    Drop and recreate the database
    """
    await migrations.init()
    await migrations.reset()
    await migrations.migrate(execute=True, dryrun=False)


@db.command()
async def apply():
    """
    Apply outstanding migrations
    """
    await migrations.migrate(execute=True, dryrun=False)


@db.command()
async def check():
    """
    Test outstanding migrations
    """
    await migrations.migrate(execute=True, dryrun=True)


@db.command()
async def status():
    """
    Check for outstanding migrations
    """
    await migrations.migrate(execute=False, dryrun=False)


@db.command()
@click.argument("description")
def create(description):
    """
    Create a new migration
    """
    with migrations.create(description) as f:
        f.write("-- %s\n\n" % description)


@db.command()
async def snapshot():
    """
    Snapshot the database structure
    """
    dsn = config.get("UNREST_ADMIN_URI")
    if dsn is None:
        raise RuntimeError("No appropriate DSN for admin role")
    os.system("pg_dump -d '%s' --schema-only --no-owner --no-acl | sed -e '/^--/d'" % dsn)


def main():
    try:
        cli()
    except Exception as ex:
        click.echo("ERROR: %s" % str(ex))


if __name__ == "__main__":
    main()
