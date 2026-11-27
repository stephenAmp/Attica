import asyncio
from getpass import getpass

from app.services.bootstrap import (
    BootstrapService,
    BootstrapError,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.core.config import Settings

from app.utils.security import hash_password


async def setup():

    settings = Settings()
    if not settings.is_community:
        print("Setup is only available in Community edition.")
        return 1

    print("\nWelcome to Attica Community Setup\n")

    workspace_name = input("Workspace name: ").strip()
    workspace_email = input("Workspace email: ").strip()
    phone = input("Workspace phone: ").strip()
    location = input("Workspace location: ").strip()

    full_name = input("Administrator name: ").strip()
    email = input("Administrator email: ").strip().lower()

    password = getpass("Password: ")
    confirm_password = getpass("Confirm password: ")

    if not all([
        workspace_name,
        workspace_email,
        phone,
        location,
        full_name,
        email,
    ]):
        print("All fields are required.")
        return 1

    if password != confirm_password:
        print("Passwords do not match.")
        return 1

    if len(password) < 8:
        print("Password must contain at least 8 characters.")
        return 1

    hashed_password = await asyncio.to_thread(
        hash_password,
        password,
    )

    engine = create_async_engine(str(settings.database_url), hide_parameters=True)
    try:
        async with AsyncSession(engine) as session:
            workspace_id = await BootstrapService(session).initialize(
                full_name=full_name,
                email=email,
                hashed_password=hashed_password,
                workspace_name=workspace_name,
                workspace_email=workspace_email,
                phone=phone,
                location=location,
            )
    except BootstrapError as exc:
        print(f"Setup failed: {exc}")
        return 1
    finally:
        await engine.dispose()

    print("\nAttica initialized successfully.")
    print(f"Workspace ID: {workspace_id}")
    print("You can now sign in.")

    return 0


def main():
    try:
        raise SystemExit(asyncio.run(setup()))
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        raise SystemExit(130)


if __name__ == "__main__":
    main()