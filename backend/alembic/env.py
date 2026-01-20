import sys
from logging.config import fileConfig

from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

sys.path.append(".")

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    from sqlalchemy import text

    provided_connection = config.attributes.get("connection")

    if provided_connection is not None:
        connection = provided_connection
        should_close = False
    else:
        connectable = create_engine(settings.database_url, future=True)
        connection = connectable.connect()
        should_close = True

    try:
        # Create alembic_version table with larger varchar if it doesn't exist
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(128) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            );
        """))
        connection.commit()

        # SQLite dev DBs have historically been created via Base.metadata.create_all(),
        # which means schema exists but alembic_version may be empty.
        # To keep local VS Code tasks stable, detect this scenario and stamp head.
        try:
            dialect = connection.dialect.name
            if dialect == "sqlite":
                count = int(connection.execute(text("select count(*) from alembic_version")).scalar() or 0)
                if count == 0:
                    # If core tables exist, assume schema was bootstrapped outside Alembic.
                    roles_exists = bool(
                        connection.execute(
                            text(
                                "select 1 from sqlite_master where type='table' and name='roles' limit 1"
                            )
                        ).scalar()
                    )
                    if roles_exists:
                        script = ScriptDirectory.from_config(config)
                        head = script.get_current_head()
                        if head:
                            connection.execute(text("delete from alembic_version"))
                            connection.execute(
                                text("insert into alembic_version(version_num) values (:v)"), {"v": head}
                            )
                            connection.commit()
        except Exception:
            # Never block migrations due to this convenience path.
            pass

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()
    finally:
        if should_close:
            connection.close()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
