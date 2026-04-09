"""CLI commands for the backend application."""

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.auth.passwords import hash_password
from backend.database import async_session, init_db
from backend.models import User


async def _create_user(username: str, password: str) -> None:
    """Create a user with the given username and bcrypt-hashed password."""
    await init_db()

    async with async_session() as session:
        # Check for existing user first for a clear message
        existing = await session.execute(
            select(User).where(User.username == username)
        )
        if existing.scalar_one_or_none() is not None:
            print(f"Error: user '{username}' already exists.", file=sys.stderr)
            sys.exit(1)

        user = User(
            username=username,
            password_hash=hash_password(password),
        )
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            # Race condition: another process created the user between
            # the check and the commit.
            print(f"Error: user '{username}' already exists.", file=sys.stderr)
            sys.exit(1)

    print(f"User '{username}' created successfully.")


def main() -> None:
    """Entry point for ``python -m backend.cli``."""
    parser = argparse.ArgumentParser(
        prog="backend.cli",
        description="Backend management commands",
    )
    subparsers = parser.add_subparsers(dest="command")

    create_user_parser = subparsers.add_parser(
        "create-user",
        help="Create a new user",
    )
    create_user_parser.add_argument("username", help="Username for the new user")
    create_user_parser.add_argument("password", help="Password for the new user")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "create-user":
        asyncio.run(_create_user(args.username, args.password))


if __name__ == "__main__":
    main()
