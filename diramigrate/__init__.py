__version__ = '0.1.0'

from config.database import DatabaseConfig


TORTOISE_ORM = DatabaseConfig().tortoise_config()