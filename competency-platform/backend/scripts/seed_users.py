"""
Seed script — creates a tenant, admin, manager and employee users.
Run once after alembic upgrade head.
"""
import asyncio
import uuid
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User

# Import Tenant model
from sqlalchemy import text

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

USERS = [
    {
        "email": "admin@company.com",
        "password": "password123",
        "full_name": "Admin User",
        "role": "admin",
        "job_title": "Platform Administrator",
        "department": "IT",
    },
    {
        "email": "manager@company.com",
        "password": "password123",
        "full_name": "Sarah Manager",
        "role": "manager",
        "job_title": "Engineering Manager",
        "department": "Engineering",
    },
    {
        "email": "employee@company.com",
        "password": "password123",
        "full_name": "John Employee",
        "role": "employee",
        "job_title": "Software Engineer",
        "department": "Engineering",
    },
]


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        # Create tenant if not exists (schema: id, name, slug, settings, created_at)
        await conn.execute(text("""
            INSERT INTO tenants (id, name, slug, settings, created_at)
            VALUES (:id, 'Demo Company', 'demo-company', '{}', NOW())
            ON CONFLICT (id) DO NOTHING
        """), {"id": str(TENANT_ID)})
        print(f"  ✓ Tenant 'Demo Company' ensured (id={TENANT_ID})")

        # Insert users
        for u in USERS:
            await conn.execute(text("""
                INSERT INTO users (tenant_id, email, hashed_password, full_name, role, job_title, department, is_active, created_at, updated_at)
                VALUES (:tenant_id, :email, :hashed_password, :full_name, :role, :job_title, :department, true, NOW(), NOW())
                ON CONFLICT (email) DO NOTHING
            """), {
                "tenant_id": str(TENANT_ID),
                "email": u["email"],
                "hashed_password": get_password_hash(u["password"]),
                "full_name": u["full_name"],
                "role": u["role"],
                "job_title": u["job_title"],
                "department": u["department"],
            })
            print(f"  ✓ Seeded user: {u['email']} (role={u['role']})")

    await engine.dispose()
    print("\nSeed complete! Test credentials:")
    for u in USERS:
        print(f"  {u['role']:10s}  {u['email']:30s}  password: {u['password']}")


if __name__ == "__main__":
    asyncio.run(seed())
