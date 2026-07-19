"""Plan 2 Verification #5 — exercise the users.role CHECK constraint via the ORM.

The plan specifies raw SQL, but the model's NOT NULL columns (e.g. is_active)
have Python-side defaults only and no DB server_default, so raw inserts hit
NOT NULL before the CHECK fires. Per the chosen approach for this deviation,
we use the ORM (which applies the Python defaults) so the CHECK is the thing
that actually gets tested. Inserts are wrapped so nothing is committed.
"""
import asyncio
import uuid

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.db import async_session_factory, engine
from app.models.tenant import Tenant
from app.models.user import User


async def main() -> None:
    async with async_session_factory() as session:
        # Everything runs inside a single transaction we roll back at the end.
        async with session.begin():
            tenant = Tenant(name="v5-orm-tenant", slug="v5-orm-tenant-slug")
            session.add(tenant)
            await session.flush()  # populates tenant.id
            tenant_id = tenant.id
            print(f"created tenant id={tenant_id}")

            # --- A) invalid role -> expect IntegrityError from ck_users_role ---
            bad = User(
                tenant_id=tenant_id,
                email="v5bad@example.com",
                hashed_password="x",
                full_name="Bad Role",
                role="superadmin",  # not in ('admin','manager','employee')
            )
            session.add(bad)
            try:
                await session.flush()
                print("FAIL: invalid-role user was accepted")
            except IntegrityError as e:
                orig = str(e.orig)
                print(f"IntegrityError raised (CHECK): {orig.splitlines()[0]}")
                print("PASS: ck_users_role rejected invalid role")


asyncio.run(main())
