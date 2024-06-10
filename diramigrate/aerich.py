from aerich import Command
from . import TORTOISE_ORM 

async def create_migration(config):
    config = TORTOISE_ORM
    command = Command(tortoise_config=config, app='models')
    await command.init()
    await command.migrate('test')
    
async def apply_migrations(config):
    command = Command(tortoise_config=config, app='models')
    await command.upgrade()