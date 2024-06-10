from diracore import cli

import click
from click import Context, UsageError

import os
from pathlib import Path
from typing import List

import tomlkit
from tomlkit.exceptions import NonExistentKey

from aerich import Command
from aerich.enums import Color
from aerich.exceptions import DowngradeError
from aerich.utils import add_src_path, get_tortoise_config
from aerich.version import __version__
from aerich.cli import CONFIG_DEFAULT_VALUES, coro

from . import DatabaseConfig


CONFIG_PATH = 'diramigrate.TORTOISE_ORM'
CONFIG_LOCATION = DatabaseConfig().migration_path

async def init(ctx: Context, app='models', config=CONFIG_PATH):
    invoked_subcommand = ctx.invoked_subcommand
    if invoked_subcommand != "db.init":
        config_path = Path(config)
        if not config_path.exists():
            raise UsageError("You must exec init first", ctx=ctx)
        content = config_path.read_text()
        doc = tomlkit.parse(content)
        try:
            tool = doc["tool"]["aerich"]
            location = tool["location"]
            tortoise_orm = tool["tortoise_orm"]
            src_folder = tool.get("src_folder", CONFIG_DEFAULT_VALUES["src_folder"])
        except NonExistentKey:
            raise UsageError("You need run aerich init again when upgrade to 0.6.0+")
        add_src_path(src_folder)
        tortoise_config = get_tortoise_config(ctx, tortoise_orm)
        app = app or list(tortoise_config.get("apps").keys())[0]
        command = Command(tortoise_config=tortoise_config, app=app, location=location)
        ctx.obj = {}
        ctx.obj["command"] = command
        if invoked_subcommand != "init-db":
            if not Path(location, app).exists():
                raise UsageError("You must exec init-db first", ctx=ctx)
            await command.init()
    
@cli.command("db.init", help="Init config file and generate root migrate location.")
@click.option(
    "-t",
    "--tortoise-orm",
    default=CONFIG_PATH,
    help="Tortoise-ORM config module dict variable, like settings.TORTOISE_ORM.",
)
@click.option(
    "--location",
    default=CONFIG_LOCATION,
    show_default=True,
    help="Migrate store location.",
)
@click.option(
    "-s",
    "--src_folder",
    default=CONFIG_DEFAULT_VALUES["src_folder"],
    show_default=False,
    help="Folder of the source, relative to the project root.",
)
@click.pass_context
@coro
async def init_command(ctx: Context, tortoise_orm, location, src_folder):
    config_file = tortoise_orm

    if os.path.isabs(src_folder):
        src_folder = os.path.relpath(os.getcwd(), src_folder)
    # Add ./ so it's clear that this is relative path
    if not src_folder.startswith("./"):
        src_folder = "./" + src_folder

    # check that we can find the configuration, if not we can fail before the config file gets created
    add_src_path(src_folder)
    get_tortoise_config(ctx, tortoise_orm)
    config_path = Path(config_file)
    if config_path.exists():
        content = config_path.read_text()
        doc = tomlkit.parse(content)
    else:
        doc = tomlkit.parse("[tool.aerich]")
    table = tomlkit.table()
    table["tortoise_orm"] = tortoise_orm
    table["location"] = location
    table["src_folder"] = src_folder
    doc["tool"]["aerich"] = table

    config_path.write_text(tomlkit.dumps(doc))

    Path(location).mkdir(parents=True, exist_ok=True)

    click.secho(f"Success create migrate location {location}", fg=Color.green)
    click.secho(f"Success write config to {config_file}", fg=Color.green)
    
    
@cli.command("db.init-db", help="Generate schema and generate app migrate location.")
@click.option(
    "-s",
    "--safe",
    type=bool,
    is_flag=True,
    default=True,
    help="When set to true, creates the table only when it does not already exist.",
    show_default=True,
)
@click.pass_context
@coro
async def init_db(ctx: Context, safe: bool):
    ctx.invoked_subcommand = 'init-db'
    await init(ctx)
    command: Command = ctx.obj["command"]
    app = command.app
    dirname = Path(command.location, app)
    try:
        await command.init_db(safe)
        click.secho(f"Success create app migrate location {dirname}", fg=Color.green)
        click.secho(f'Success generate schema for app "{app}"', fg=Color.green)
    except FileExistsError:
        return click.secho(
            f"Inited {app} already, or delete {dirname} and try again.", fg=Color.yellow
        )
    
    
    
@cli.command("db.migrate", help="Generate migrate changes file.")
@click.option("--name", default="update", show_default=True, help="Migrate name.")
@click.pass_context
@coro
async def migrate(ctx: Context, name):
    await init(ctx)
    command = ctx.obj["command"]
    ret = await command.migrate(name)
    if not ret:
        return click.secho("No changes detected", fg=Color.yellow)
    click.secho(f"Success migrate {ret}", fg=Color.green)
    
    
@cli.command("db.history", help="List all migrate items.")
@click.pass_context
@coro
async def history(ctx: Context):
    await init(ctx)
    command = ctx.obj["command"]
    versions = await command.history()
    if not versions:
        return click.secho("No history, try migrate", fg=Color.green)
    for version in versions:
        click.secho(version, fg=Color.green)
    
    
@cli.command("db.inspectdb", help="Introspects the database tables to standard output as TortoiseORM model.")
@click.option(
    "-t",
    "--table",
    help="Which tables to inspect.",
    multiple=True,
    required=False,
)
@click.pass_context
@coro
async def inspectdb(ctx: Context, table: List[str]):
    await init(ctx)
    command = ctx.obj["command"]
    ret = await command.inspectdb(table)
    click.secho(ret)
    
    
@cli.command("db.heads", help="Show current available heads in migrate location.")
@click.pass_context
@coro
async def heads(ctx: Context):
    await init(ctx)
    command = ctx.obj["command"]
    head_list = await command.heads()
    if not head_list:
        return click.secho("No available heads, try migrate first", fg=Color.green)
    for version in head_list:
        click.secho(version, fg=Color.green)
        
@cli.command("db.upgrade", help="Upgrade to specified version.")
@click.option(
    "--in-transaction",
    "-i",
    default=True,
    type=bool,
    help="Make migrations in transaction or not. Can be helpful for large migrations or creating concurrent indexes.",
)
@click.pass_context
@coro
async def upgrade(ctx: Context, in_transaction: bool):
    await init(ctx)
    command = ctx.obj["command"]
    migrated = await command.upgrade(run_in_transaction=in_transaction)
    if not migrated:
        click.secho("No upgrade items found", fg=Color.yellow)
    else:
        for version_file in migrated:
            click.secho(f"Success upgrade {version_file}", fg=Color.green)


@cli.command("db.downgrade", help="Downgrade to specified version.")
@click.option(
    "-v",
    "--version",
    default=-1,
    type=int,
    show_default=True,
    help="Specified version, default to last.",
)
@click.option(
    "-d",
    "--delete",
    is_flag=True,
    default=False,
    show_default=True,
    help="Delete version files at the same time.",
)
@click.pass_context
@click.confirmation_option(
    prompt="Downgrade is dangerous, which maybe lose your data, are you sure?",
)
@coro
async def downgrade(ctx: Context, version: int, delete: bool):
    await init(ctx)
    command = ctx.obj["command"]
    try:
        files = await command.downgrade(version, delete)
    except DowngradeError as e:
        return click.secho(str(e), fg=Color.yellow)
    for file in files:
        click.secho(f"Success downgrade {file}", fg=Color.green)