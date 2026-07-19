"""Plan 2 Verification #6 — insert a content_item with a 1536-dim vector and
run a cosine-distance nearest-neighbour query.

Uses pgvector's <=> operator (cosine distance). Wraps everything in one
transaction that rolls back, so no rows are persisted.
"""
import asyncio

from sqlalchemy import text

from app.core.db import async_session_factory
from app.models.competency import Competency, Skill
from app.models.session import ContentItem
from app.models.tenant import Tenant
from app.models.user import User


def vec_uniform(val: float) -> list[float]:
    """A 1536-dim vector filled with a single non-zero value."""
    return [val] * 1536


def vec_split() -> list[float]:
    """A 1536-dim vector pointing in a clearly different direction:
    +1 in the first half, -1 in the second half. Non-zero norm."""
    return [1.0] * 768 + [-1.0] * 768


async def main() -> None:
    async with async_session_factory() as session:
        async with session.begin():
            tenant = Tenant(name="v6-orm-tenant", slug="v6-orm-tenant-slug")
            session.add(tenant)
            await session.flush()
            owner = User(
                tenant_id=tenant.id,
                email="v6owner@example.com",
                hashed_password="x",
                full_name="V6 Owner",
                role="admin",
            )
            session.add(owner)
            await session.flush()
            comp = Competency(
                tenant_id=tenant.id,
                name="V6 Comp",
                created_by=owner.id,
            )
            session.add(comp)
            await session.flush()
            skill = Skill(
                competency_id=comp.id,
                name="V6 Skill",
                hierarchy_level=1,
                difficulty_level=1,
                learning_strategy="conceptual",
            )
            session.add(skill)
            await session.flush()

            item_near = ContentItem(
                skill_id=skill.id,
                content_type="explanation",
                difficulty_level=1,
                content_body="nearest embedding target",
                embedding=vec_uniform(1.0),
            )
            item_far = ContentItem(
                skill_id=skill.id,
                content_type="explanation",
                difficulty_level=1,
                content_body="far embedding",
                embedding=vec_split(),
            )
            session.add_all([item_near, item_far])
            await session.flush()
            print(f"inserted content_items: near id={item_near.id}, far id={item_far.id}")
            print("PASS: insert of 1536-dim vector succeeded")

            # cosine-distance ANN query: query vector == near vector,
            # so near should rank first with tiny distance, far last with ~0.5
            q = text(
                """
                SELECT id, content_body,
                       (embedding <=> (:q)::vector) AS cosine_distance
                FROM content_items
                ORDER BY embedding <=> (:q)::vector
                """
            )
            res = await session.execute(q, {"q": str(vec_uniform(1.0))})
            rows = res.all()
            print(f"cosine query returned {len(rows)} rows:")
            for r in rows:
                print(f"  {r[0]}  dist={r[2]}  body={r[1]!r}")
            assert len(rows) == 2, "expected 2 content_items"
            assert rows[0][1] == "nearest embedding target", "nearest row should rank first"
            near_d, far_d = rows[0][2], rows[1][2]
            assert near_d < far_d, f"near({near_d}) should be < far({far_d})"
            print(f"near distance {near_d} < far distance {far_d}: PASS")
            print("PASS: cosine distance query returns results in correct order")


asyncio.run(main())
