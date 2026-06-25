# Database Schema & Models

## Plan 2 of 21 — Competency Intelligence Platform MVP

---

### Objective

Implement all PostgreSQL database tables as SQLModel ORM models, configure Alembic for auto-generated migrations, and enable the pgvector extension for content similarity search. After this plan, all core data structures are in place and migratable, forming the data foundation for every subsequent plan.

### Prerequisites

- **Plan 1** (Infrastructure Setup) — Docker Compose with PostgreSQL + pgvector running, project scaffold created.

### Spec References

| Section | Content |
|---------|---------|
| §6.1 PostgreSQL DDL — Core Tables | All CREATE TABLE statements (tenants, users, competencies, skills, skill_edges, employee_learning_states, mastery_history, assessment_results, learning_sessions, content_items) |
| §18.3 Alembic Migration Setup | Alembic commands and configuration |
| §11 Project File Structure | models/ directory (user.py, competency.py, session.py, assessment.py, learning_state.py) |

---

### Files to Create/Modify

```
competency-platform/backend/
├── app/
│   ├── models/
│   │   ├── __init__.py           # Export all models
│   │   ├── tenant.py             # SQLModel Tenant
│   │   ├── user.py               # SQLModel User
│   │   ├── competency.py         # SQLModel Competency + Skill + SkillEdge
│   │   ├── learning_state.py     # SQLModel EmployeeLearningState
│   │   ├── assessment.py         # SQLModel AssessmentResult + MasteryHistory
│   │   ├── session.py            # SQLModel LearningSession + ContentItem
│   │   └── base.py               # Base model mixins (timestamps, UUID PK)
│   └── core/
│       └── db.py                 # Update: import all models for Alembic discovery
├── alembic/
│   ├── alembic.ini
│   ├── env.py                    # Async Alembic env
│   └── versions/                 # Migration files
└── scripts/
    └── init_pgvector.sql         # CREATE EXTENSION vector
```

---

### Detailed Implementation Steps

#### Step 1: Create Base Model Mixin

```python
# app/models/base.py
import uuid
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, DateTime, text
from sqlalchemy.dialects.postgresql import UUID


class UUIDModel(SQLModel):
    """Mixin that adds a UUID primary key."""
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )


class TimestampModel(SQLModel):
    """Mixin that adds created_at and updated_at timestamps."""
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("NOW()"),
            nullable=False,
        ),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("NOW()"),
            onupdate=datetime.utcnow,
            nullable=False,
        ),
    )
```

#### Step 2: Tenant Model

```python
# app/models/tenant.py
import uuid
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON, DateTime, text

class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    name: str = Field(max_length=255, nullable=False)
    slug: str = Field(max_length=100, unique=True, nullable=False)
    settings: Optional[dict] = Field(default={}, sa_column=Column(JSON, server_default="'{}'"))
    created_at: Optional[str] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
```

#### Step 3: User Model

```python
# app/models/user.py
import uuid
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, DateTime, JSON, CheckConstraint, Index, text

class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin','manager','employee')", name="ck_users_role"),
        Index("idx_users_tenant", "tenant_id"),
        Index("idx_users_role", "role"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)
    email: str = Field(max_length=255, unique=True, nullable=False)
    hashed_password: str = Field(nullable=False)
    full_name: str = Field(max_length=255, nullable=False)
    role: str = Field(max_length=50, nullable=False)  # admin | manager | employee
    job_title: Optional[str] = Field(default=None, max_length=255)
    department: Optional[str] = Field(default=None, max_length=255)
    metadata_: Optional[dict] = Field(
        default={},
        sa_column=Column("metadata", JSON, server_default="'{}'"),
    )
    is_active: bool = Field(default=True)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
```

#### Step 4: Competency, Skill, and SkillEdge Models

```python
# app/models/competency.py
import uuid
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import (
    Column, DateTime, JSON, CheckConstraint, Index,
    Float, Integer, Text, text, ARRAY, String,
)

class Competency(SQLModel, table=True):
    __tablename__ = "competencies"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','under_review','active','deprecated')",
            name="ck_competencies_status",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)
    name: str = Field(max_length=255, nullable=False)
    description: Optional[str] = Field(default=None)
    business_relevance: Optional[str] = Field(default=None)
    target_roles: Optional[list[str]] = Field(
        default=[],
        sa_column=Column(ARRAY(String)),
    )
    version_major: int = Field(default=1)
    version_minor: int = Field(default=0)
    status: str = Field(default="draft", max_length=50)
    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    approved_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    approved_at: Optional[datetime] = Field(default=None)
    decomp_confidence: Optional[float] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )


class Skill(SQLModel, table=True):
    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint("hierarchy_level BETWEEN 1 AND 3", name="ck_skills_hierarchy"),
        CheckConstraint("difficulty_level BETWEEN 1 AND 5", name="ck_skills_difficulty"),
        CheckConstraint(
            "learning_strategy IN ('conceptual','procedural','applied','analytical')",
            name="ck_skills_strategy",
        ),
        Index("idx_skills_competency", "competency_id"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    competency_id: uuid.UUID = Field(
        foreign_key="competencies.id",
        nullable=False,
        sa_column_kwargs={"ondelete": "CASCADE"},
    )
    name: str = Field(max_length=255, nullable=False)
    description: Optional[str] = Field(default=None)
    hierarchy_level: int = Field(default=1)
    difficulty_level: int = Field(default=1)
    learning_strategy: Optional[str] = Field(default=None, max_length=50)
    mastery_threshold: float = Field(default=0.80)
    eval_dimensions: Optional[dict] = Field(
        default={},
        sa_column=Column(JSON, server_default="'{}'"),
    )
    estimated_minutes: int = Field(default=60)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )


class SkillEdge(SQLModel, table=True):
    """Skill dependency edges — the DAG structure in PostgreSQL."""
    __tablename__ = "skill_edges"

    prerequisite_id: uuid.UUID = Field(
        foreign_key="skills.id",
        primary_key=True,
        sa_column_kwargs={"ondelete": "CASCADE"},
    )
    dependent_id: uuid.UUID = Field(
        foreign_key="skills.id",
        primary_key=True,
        sa_column_kwargs={"ondelete": "CASCADE"},
    )
    edge_type: str = Field(default="requires", max_length=50)
    strength: float = Field(default=1.0)
```

#### Step 5: Employee Learning State Model

```python
# app/models/learning_state.py
import uuid
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import (
    Column, DateTime, JSON, CheckConstraint, Index,
    UniqueConstraint, text,
)

class EmployeeLearningState(SQLModel, table=True):
    __tablename__ = "employee_learning_states"
    __table_args__ = (
        CheckConstraint("current_score BETWEEN 0 AND 100", name="ck_els_score"),
        CheckConstraint("mastery_level BETWEEN 0 AND 5", name="ck_els_mastery"),
        UniqueConstraint("employee_id", "skill_id", name="uq_els_employee_skill"),
        Index("idx_els_employee", "employee_id"),
        Index("idx_els_skill", "skill_id"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    employee_id: uuid.UUID = Field(
        foreign_key="users.id",
        nullable=False,
        sa_column_kwargs={"ondelete": "CASCADE"},
    )
    skill_id: uuid.UUID = Field(
        foreign_key="skills.id",
        nullable=False,
        sa_column_kwargs={"ondelete": "CASCADE"},
    )
    competency_id: uuid.UUID = Field(foreign_key="competencies.id", nullable=False)
    current_score: float = Field(default=0.0)
    mastery_level: int = Field(default=0)
    mastery_confidence: float = Field(default=0.0)
    knowledge_gaps: Optional[list] = Field(
        default=[],
        sa_column=Column(JSON, server_default="'[]'"),
    )
    misconception_map: Optional[list] = Field(
        default=[],
        sa_column=Column(JSON, server_default="'[]'"),
    )
    learning_velocity: float = Field(default=0.0)
    engagement_score: float = Field(default=0.0)
    total_interactions: int = Field(default=0)
    sessions_count: int = Field(default=0)
    last_assessed_at: Optional[datetime] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
```

#### Step 6: Assessment Result and Mastery History Models

```python
# app/models/assessment.py
import uuid
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import (
    Column, DateTime, JSON, CheckConstraint, Index, text,
)

class AssessmentResult(SQLModel, table=True):
    __tablename__ = "assessment_results"
    __table_args__ = (
        CheckConstraint(
            "assessment_mode IN ('quiz','conversational','scenario','baseline')",
            name="ck_ar_mode",
        ),
        Index("idx_ar_employee_skill", "employee_id", "skill_id"),
        Index("idx_ar_session", "session_id"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    session_id: uuid.UUID = Field(nullable=False)
    employee_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    skill_id: uuid.UUID = Field(foreign_key="skills.id", nullable=False)
    assessment_mode: Optional[str] = Field(default=None, max_length=50)
    prompt_text: str = Field(nullable=False)
    response_text: str = Field(nullable=False)
    response_latency_ms: Optional[int] = Field(default=None)
    score_accuracy: Optional[float] = Field(default=None)
    score_application: Optional[float] = Field(default=None)
    score_reasoning: Optional[float] = Field(default=None)
    score_consistency: Optional[float] = Field(default=None)
    score_confidence: Optional[float] = Field(default=None)
    composite_score: float = Field(nullable=False)
    misconceptions: Optional[list] = Field(
        default=[],
        sa_column=Column(JSON, server_default="'[]'"),
    )
    feedback_points: Optional[list] = Field(
        default=[],
        sa_column=Column(JSON, server_default="'[]'"),
    )
    llm_model_used: Optional[str] = Field(default=None, max_length=100)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )


class MasteryHistory(SQLModel, table=True):
    """Immutable append-only mastery decision log."""
    __tablename__ = "mastery_history"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('UPGRADE','MAINTAIN','DOWNGRADE')",
            name="ck_mh_decision",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    employee_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    skill_id: uuid.UUID = Field(foreign_key="skills.id", nullable=False)
    old_level: Optional[int] = Field(default=None)
    new_level: int = Field(nullable=False)
    decision: Optional[str] = Field(default=None, max_length=20)
    confidence: Optional[float] = Field(default=None)
    evidence_summary: Optional[str] = Field(default=None)
    decided_by: str = Field(default="ai", max_length=50)  # 'ai' or 'manager_override'
    override_reason: Optional[str] = Field(default=None)
    session_id: Optional[uuid.UUID] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
```

#### Step 7: Learning Session and Content Item Models

```python
# app/models/session.py
import uuid
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import (
    Column, DateTime, JSON, CheckConstraint, Index, text,
)
from pgvector.sqlalchemy import Vector

class LearningSession(SQLModel, table=True):
    __tablename__ = "learning_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','paused','completed','timed_out')",
            name="ck_ls_status",
        ),
        CheckConstraint(
            "session_type IN ('baseline','learning','review')",
            name="ck_ls_type",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    employee_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    skill_id: uuid.UUID = Field(foreign_key="skills.id", nullable=False)
    competency_id: uuid.UUID = Field(foreign_key="competencies.id", nullable=False)
    status: str = Field(default="active", max_length=50)
    session_type: str = Field(default="learning", max_length=50)
    started_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
    ended_at: Optional[datetime] = Field(default=None)
    interaction_count: int = Field(default=0)
    final_score: Optional[float] = Field(default=None)
    mastery_reached: bool = Field(default=False)
    path_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )


class ContentItem(SQLModel, table=True):
    __tablename__ = "content_items"
    __table_args__ = (
        CheckConstraint(
            "content_type IN ('explanation','scenario','quiz','dialogue')",
            name="ck_ci_type",
        ),
        Index("idx_content_skill", "skill_id", "content_type", "difficulty_level"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    skill_id: uuid.UUID = Field(foreign_key="skills.id", nullable=False)
    content_type: Optional[str] = Field(default=None, max_length=50)
    difficulty_level: Optional[int] = Field(default=None)
    content_body: str = Field(nullable=False)
    interaction_prompts: Optional[list] = Field(
        default=[],
        sa_column=Column(JSON, server_default="'[]'"),
    )
    expected_schema: Optional[dict] = Field(
        default={},
        sa_column=Column(JSON, server_default="'{}'"),
    )
    quality_score: Optional[float] = Field(default=None)
    times_used: int = Field(default=0)
    avg_score_lift: Optional[float] = Field(default=None)
    llm_model_used: Optional[str] = Field(default=None, max_length=100)
    # pgvector embedding column — 1536 dimensions (text-embedding-3-small)
    embedding: Optional[list[float]] = Field(
        default=None,
        sa_column=Column(Vector(1536)),
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
```

#### Step 8: Models __init__.py — Export All

```python
# app/models/__init__.py
from app.models.tenant import Tenant
from app.models.user import User
from app.models.competency import Competency, Skill, SkillEdge
from app.models.learning_state import EmployeeLearningState
from app.models.assessment import AssessmentResult, MasteryHistory
from app.models.session import LearningSession, ContentItem

__all__ = [
    "Tenant",
    "User",
    "Competency",
    "Skill",
    "SkillEdge",
    "EmployeeLearningState",
    "AssessmentResult",
    "MasteryHistory",
    "LearningSession",
    "ContentItem",
]
```

#### Step 9: Alembic Configuration

```ini
# alembic.ini
[alembic]
script_location = alembic
sqlalchemy.url = driver://user:pass@localhost/dbname
# This is overridden by env.py at runtime

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

#### Step 10: Async Alembic env.py

```python
# alembic/env.py
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from app.core.config import settings

# Import ALL models so Alembic can detect them
from app.models import (  # noqa: F401
    Tenant, User, Competency, Skill, SkillEdge,
    EmployeeLearningState, AssessmentResult, MasteryHistory,
    LearningSession, ContentItem,
)
from sqlmodel import SQLModel

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# Override sqlalchemy.url with env var
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = settings.DATABASE_URL
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

#### Step 11: pgvector Initialization Script

```sql
-- scripts/init_pgvector.sql
-- Run this once against the competency_db database
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify
SELECT * FROM pg_extension WHERE extname = 'vector';
```

#### Step 12: Create HNSW Index on Content Embeddings

This is handled in the Alembic migration but documented here for reference:

```sql
-- After content_items table is created:
CREATE INDEX idx_content_embedding ON content_items
    USING hnsw(embedding vector_cosine_ops);
```

#### Step 13: Update db.py to Import All Models

```python
# app/core/db.py — update to ensure model discovery
from sqlmodel import SQLModel  # noqa: F401
from app.models import *  # noqa: F401, F403 — ensures all models registered

# ... existing get_async_session() code ...
```

---

### Key DDL from Spec (Verbatim Reference)

**Listing 4: Users and Tenants**
```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('admin','manager','employee')),
    job_title VARCHAR(255),
    department VARCHAR(255),
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_role ON users(role);
```

**Listing 5: Competency and Skill Tables**
```sql
CREATE TABLE competencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    business_relevance TEXT,
    target_roles TEXT[],
    version_major INTEGER DEFAULT 1,
    version_minor INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'draft'
        CHECK (status IN ('draft','under_review','active','deprecated')),
    created_by UUID NOT NULL REFERENCES users(id),
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    decomp_confidence FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competency_id UUID NOT NULL REFERENCES competencies(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    hierarchy_level INTEGER DEFAULT 1 CHECK (hierarchy_level BETWEEN 1 AND 3),
    difficulty_level INTEGER DEFAULT 1 CHECK (difficulty_level BETWEEN 1 AND 5),
    learning_strategy VARCHAR(50)
        CHECK (learning_strategy IN ('conceptual','procedural','applied','analytical')),
    mastery_threshold FLOAT DEFAULT 0.80,
    eval_dimensions JSONB DEFAULT '{}',
    estimated_minutes INTEGER DEFAULT 60,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_skills_competency ON skills(competency_id);

CREATE TABLE skill_edges (
    prerequisite_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    dependent_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    edge_type VARCHAR(50) DEFAULT 'requires',
    strength FLOAT DEFAULT 1.0,
    PRIMARY KEY (prerequisite_id, dependent_id)
);
```

**Listing 6: Employee Learning State and Mastery Tables**
```sql
CREATE TABLE employee_learning_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    competency_id UUID NOT NULL REFERENCES competencies(id),
    current_score FLOAT DEFAULT 0.0 CHECK (current_score BETWEEN 0 AND 100),
    mastery_level INTEGER DEFAULT 0 CHECK (mastery_level BETWEEN 0 AND 5),
    mastery_confidence FLOAT DEFAULT 0.0,
    knowledge_gaps JSONB DEFAULT '[]',
    misconception_map JSONB DEFAULT '[]',
    learning_velocity FLOAT DEFAULT 0.0,
    engagement_score FLOAT DEFAULT 0.0,
    total_interactions INTEGER DEFAULT 0,
    sessions_count INTEGER DEFAULT 0,
    last_assessed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(employee_id, skill_id)
);

CREATE TABLE mastery_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL REFERENCES users(id),
    skill_id UUID NOT NULL REFERENCES skills(id),
    old_level INTEGER,
    new_level INTEGER NOT NULL,
    decision VARCHAR(20) CHECK (decision IN ('UPGRADE','MAINTAIN','DOWNGRADE')),
    confidence FLOAT,
    evidence_summary TEXT,
    decided_by VARCHAR(50) DEFAULT 'ai',
    override_reason TEXT,
    session_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE assessment_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    employee_id UUID NOT NULL REFERENCES users(id),
    skill_id UUID NOT NULL REFERENCES skills(id),
    assessment_mode VARCHAR(50) CHECK (assessment_mode IN ('quiz','conversational','scenario','baseline')),
    prompt_text TEXT NOT NULL,
    response_text TEXT NOT NULL,
    response_latency_ms INTEGER,
    score_accuracy FLOAT,
    score_application FLOAT,
    score_reasoning FLOAT,
    score_consistency FLOAT,
    score_confidence FLOAT,
    composite_score FLOAT NOT NULL,
    misconceptions JSONB DEFAULT '[]',
    feedback_points JSONB DEFAULT '[]',
    llm_model_used VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_ar_employee_skill ON assessment_results(employee_id, skill_id);
CREATE INDEX idx_ar_session ON assessment_results(session_id);
```

**Listing 7: Session and Content Tables**
```sql
CREATE TABLE learning_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL REFERENCES users(id),
    skill_id UUID NOT NULL REFERENCES skills(id),
    competency_id UUID NOT NULL REFERENCES competencies(id),
    status VARCHAR(50) DEFAULT 'active'
        CHECK (status IN ('active','paused','completed','timed_out')),
    session_type VARCHAR(50) DEFAULT 'learning'
        CHECK (session_type IN ('baseline','learning','review')),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    interaction_count INTEGER DEFAULT 0,
    final_score FLOAT,
    mastery_reached BOOLEAN DEFAULT FALSE,
    path_snapshot JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE content_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id UUID NOT NULL REFERENCES skills(id),
    content_type VARCHAR(50) CHECK (content_type IN ('explanation','scenario','quiz','dialogue')),
    difficulty_level INTEGER,
    content_body TEXT NOT NULL,
    interaction_prompts JSONB DEFAULT '[]',
    expected_schema JSONB DEFAULT '{}',
    quality_score FLOAT,
    times_used INTEGER DEFAULT 0,
    avg_score_lift FLOAT,
    llm_model_used VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_content_skill ON content_items(skill_id, content_type, difficulty_level);

ALTER TABLE content_items ADD COLUMN embedding vector(1536);
CREATE INDEX idx_content_embedding ON content_items USING hnsw(embedding vector_cosine_ops);
```

---

### Alembic Commands (from §18.3)

```bash
# Generate migration from model changes
alembic revision --autogenerate -m "initial schema"

# Apply all migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1

# Enable pgvector (run once in psql)
# CREATE EXTENSION IF NOT EXISTS vector;
```

---

### Configuration & Environment

Required environment variables (from Plan 1):
```
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/competency_db
DATABASE_URL_SYNC=postgresql://postgres:password@localhost:5432/competency_db
```

pyproject.toml dependencies:
```
sqlmodel>=0.0.16
alembic>=1.13
asyncpg>=0.29
pgvector>=0.3
psycopg[binary]>=3.1
```

---

### Verification Criteria

1. **pgvector extension enabled**: `SELECT * FROM pg_extension WHERE extname = 'vector';` returns a row
2. **Migration generates cleanly**: `alembic revision --autogenerate -m "initial"` creates a migration file with all 10 tables
3. **Migration applies**: `alembic upgrade head` completes without errors
4. **All tables exist**: Query `information_schema.tables` shows all 10 tables
5. **Constraints work**: Insert a user with invalid role → CHECK constraint violation
6. **pgvector works**: Insert a content_item with a 1536-dim vector → succeeds; cosine distance query returns results
7. **Rollback works**: `alembic downgrade -1` cleanly drops all tables

### Notes & Gotchas

- **pgvector must be installed first**: The Docker image `pgvector/pgvector:pg16` includes it, but the extension must be created with `CREATE EXTENSION IF NOT EXISTS vector;` before running Alembic
- **Alembic doesn't auto-detect pgvector columns well**: You may need to add `import pgvector.sqlalchemy` in `env.py` and handle the Vector type registration
- **ARRAY type**: SQLAlchemy's `ARRAY(String)` maps to PostgreSQL `TEXT[]` — ensure the import from `sqlalchemy.dialects.postgresql`
- **JSON defaults**: Use string `'{}'` for server_default, not Python dict
- **Composite primary key on skill_edges**: SQLModel handles this via two `primary_key=True` fields
- **The `metadata` column on users**: Python's `metadata` conflicts with SQLModel internals — use `metadata_` with `sa_column=Column("metadata", ...)` aliasing
