# Neo4j Knowledge Graph

## Plan 4 of 21 — Competency Intelligence Platform MVP

---

### Objective

Set up the Neo4j skill knowledge graph: define node labels and relationships in Cypher, implement the async Neo4j Python driver, build CRUD operations for competency subgraphs (create, read, update, delete skill nodes and edges), and establish constraint/index definitions. After this plan, the Competency Architect Agent can write decomposed skill DAGs into Neo4j, and query operations like prerequisite traversal and topological ordering work correctly.

### Prerequisites

- **Plan 1** (Infrastructure Setup) — Neo4j 5 Community running in Docker
- **Plan 2** (Database Schema) — Skill/Competency UUIDs established in PostgreSQL

### Spec References

| Section | Content |
|---------|---------|
| §6.2 Neo4j Schema — Skill Knowledge Graph | Node labels, relationships, Cypher examples (Listing 8) |
| §11 Project File Structure | core/neo4j.py |
| §3 Competency Architect Agent | Neo4j graph query tool |
| §3 Mastery Evaluation Agent | Neo4j prerequisite mastery check |

---

### Files to Create/Modify

```
competency-platform/backend/app/
├── core/
│   └── neo4j.py              # Neo4j async driver setup, connection pool
├── services/
│   └── skill_graph.py        # Skill graph CRUD operations (Cypher)
└── scripts/
    └── init_neo4j.cypher     # Constraint and index creation script
```

---

### Detailed Implementation Steps

#### Step 1: Neo4j Driver Configuration

```python
# app/core/neo4j.py
from neo4j import AsyncGraphDatabase, AsyncDriver
from app.core.config import settings
from contextlib import asynccontextmanager
from typing import AsyncGenerator

_driver: AsyncDriver | None = None


async def init_neo4j() -> AsyncDriver:
    """Initialize the Neo4j async driver. Call once at app startup."""
    global _driver
    _driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        max_connection_pool_size=50,
        connection_acquisition_timeout=30,
    )
    # Verify connectivity
    await _driver.verify_connectivity()
    return _driver


async def close_neo4j():
    """Close the Neo4j driver. Call at app shutdown."""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None


def get_neo4j_driver() -> AsyncDriver:
    """Get the initialized Neo4j driver instance."""
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialized. Call init_neo4j() first.")
    return _driver


@asynccontextmanager
async def get_neo4j_session() -> AsyncGenerator:
    """Async context manager for Neo4j sessions."""
    driver = get_neo4j_driver()
    async with driver.session(database="neo4j") as session:
        yield session
```

#### Step 2: Neo4j Constraints and Indexes

```cypher
// scripts/init_neo4j.cypher
// Run once to set up constraints and indexes

// Unique constraints
CREATE CONSTRAINT competency_id_unique IF NOT EXISTS
    FOR (c:Competency) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT skill_id_unique IF NOT EXISTS
    FOR (s:Skill) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT employee_id_unique IF NOT EXISTS
    FOR (e:Employee) REQUIRE e.id IS UNIQUE;

// Indexes for fast lookups
CREATE INDEX competency_tenant_idx IF NOT EXISTS
    FOR (c:Competency) ON (c.tenant_id);

CREATE INDEX skill_name_idx IF NOT EXISTS
    FOR (s:Skill) ON (s.name);

CREATE INDEX competency_status_idx IF NOT EXISTS
    FOR (c:Competency) ON (c.status);
```

#### Step 3: Neo4j Schema — Node Labels and Relationships (from §6.2 Listing 8)

```cypher
// Node Labels and Properties

// Competency node
CREATE (:Competency {
    id: 'uuid',
    name: 'string',
    version: 'string',    // "1.0"
    status: 'string',
    tenant_id: 'uuid'
})

// Skill node
CREATE (:Skill {
    id: 'uuid',
    name: 'string',
    description: 'string',
    level: integer,        // hierarchy level 1-3
    difficulty: integer,   // 1-5
    strategy: 'string'
})

// Employee node (for mastery tracking)
CREATE (:Employee {
    id: 'uuid',
    name: 'string'
})

// Relationships
(:Competency)-[:HAS_SKILL {order: integer}]->(:Skill)
(:Skill)-[:REQUIRES {strength: float}]->(:Skill)
(:Skill)-[:SIMILAR_TO {similarity: float}]->(:Skill)
(:Employee)-[:HAS_MASTERY {
    level: integer,
    score: float,
    confidence: float,
    updated_at: datetime
}]->(:Skill)
```

#### Step 4: Skill Graph CRUD Service

```python
# app/services/skill_graph.py
"""Neo4j skill graph operations — Cypher queries for competency subgraphs."""
import uuid
from typing import Optional
from app.core.neo4j import get_neo4j_session


class SkillGraphService:
    """Service for managing skill DAGs in Neo4j."""

    # --- CREATE OPERATIONS ---

    @staticmethod
    async def create_competency_subgraph(
        competency_id: str,
        competency_name: str,
        version: str,
        status: str,
        tenant_id: str,
        skill_nodes: list[dict],
        skill_edges: list[dict],
    ) -> dict:
        """Create a full competency subgraph with skills and edges.
        
        From spec §6.2 Listing 8:
        MERGE (c:Competency {id: $comp_id})
        MERGE (s1:Skill {id: $skill1_id, name: 'System Design Basics'})
        MERGE (c)-[:HAS_SKILL {order: 1}]->(s1)
        MERGE (s1)-[:REQUIRES {strength: 1.0}]->(s2)
        """
        async with get_neo4j_session() as session:
            # Step 1: Create/merge competency node
            await session.run(
                """
                MERGE (c:Competency {id: $comp_id})
                SET c.name = $name,
                    c.version = $version,
                    c.status = $status,
                    c.tenant_id = $tenant_id
                """,
                comp_id=competency_id,
                name=competency_name,
                version=version,
                status=status,
                tenant_id=tenant_id,
            )

            # Step 2: Create skill nodes and HAS_SKILL edges
            for idx, skill in enumerate(skill_nodes):
                await session.run(
                    """
                    MATCH (c:Competency {id: $comp_id})
                    MERGE (s:Skill {id: $skill_id})
                    SET s.name = $name,
                        s.description = $description,
                        s.level = $level,
                        s.difficulty = $difficulty,
                        s.strategy = $strategy
                    MERGE (c)-[:HAS_SKILL {order: $order}]->(s)
                    """,
                    comp_id=competency_id,
                    skill_id=skill["id"],
                    name=skill["name"],
                    description=skill.get("description", ""),
                    level=skill.get("hierarchy_level", 1),
                    difficulty=skill.get("difficulty_level", 1),
                    strategy=skill.get("learning_strategy", "conceptual"),
                    order=idx + 1,
                )

            # Step 3: Create REQUIRES edges (prerequisite dependencies)
            for edge in skill_edges:
                await session.run(
                    """
                    MATCH (prereq:Skill {id: $prereq_id})
                    MATCH (dep:Skill {id: $dep_id})
                    MERGE (prereq)-[:REQUIRES {strength: $strength}]->(dep)
                    """,
                    prereq_id=edge["prerequisite_id"],
                    dep_id=edge["dependent_id"],
                    strength=edge.get("strength", 1.0),
                )

        return {"competency_id": competency_id, "skills_created": len(skill_nodes)}

    # --- READ OPERATIONS ---

    @staticmethod
    async def get_skill_graph(competency_id: str) -> dict:
        """Get full skill DAG with prerequisites for a competency.
        
        From spec §6.2 Listing 8:
        MATCH path = (c:Competency {id: $comp_id})-[:HAS_SKILL*]->(s:Skill)
        WITH s, [r IN relationships(path) | type(r)] AS rels
        MATCH (s)-[:REQUIRES]->(prereq:Skill)
        RETURN s, collect(prereq) as prerequisites
        ORDER BY length(path)
        """
        async with get_neo4j_session() as session:
            # Get all skills for this competency
            result = await session.run(
                """
                MATCH (c:Competency {id: $comp_id})-[:HAS_SKILL]->(s:Skill)
                OPTIONAL MATCH (s)-[r:REQUIRES]->(prereq:Skill)
                RETURN s {.id, .name, .description, .level, .difficulty, .strategy} AS skill,
                       collect(DISTINCT prereq {.id, .name}) AS prerequisites,
                       collect(DISTINCT {prerequisite_id: prereq.id, strength: r.strength}) AS edges
                ORDER BY s.level, s.difficulty
                """,
                comp_id=competency_id,
            )
            records = [record.data() async for record in result]

            nodes = []
            edges = []
            for record in records:
                nodes.append(record["skill"])
                for edge in record.get("edges", []):
                    if edge.get("prerequisite_id"):
                        edges.append({
                            "prerequisite_id": edge["prerequisite_id"],
                            "dependent_id": record["skill"]["id"],
                            "strength": edge.get("strength", 1.0),
                        })

            return {"nodes": nodes, "edges": edges}

    @staticmethod
    async def get_skill_prerequisites(skill_id: str) -> list[dict]:
        """Get all prerequisite skills (recursive traversal)."""
        async with get_neo4j_session() as session:
            result = await session.run(
                """
                MATCH path = (prereq:Skill)-[:REQUIRES*]->(target:Skill {id: $skill_id})
                RETURN prereq {.id, .name, .level, .difficulty} AS prerequisite,
                       length(path) AS depth
                ORDER BY depth DESC
                """,
                skill_id=skill_id,
            )
            return [record.data() async for record in result]

    @staticmethod
    async def get_topological_order(competency_id: str) -> list[str]:
        """Get topologically sorted skill IDs (dependencies first)."""
        async with get_neo4j_session() as session:
            result = await session.run(
                """
                MATCH (c:Competency {id: $comp_id})-[:HAS_SKILL]->(s:Skill)
                WITH collect(s) AS skills
                UNWIND skills AS s
                OPTIONAL MATCH (s)-[:REQUIRES]->(dep:Skill)
                WITH s, collect(dep.id) AS deps
                RETURN s.id AS skill_id, s.name AS name, deps AS dependencies
                """,
                comp_id=competency_id,
            )
            records = [record.data() async for record in result]

            # Kahn's algorithm for topological sort
            in_degree = {}
            graph = {}
            for rec in records:
                sid = rec["skill_id"]
                in_degree[sid] = 0
                graph[sid] = []

            for rec in records:
                for dep in rec["dependencies"]:
                    if dep in graph:
                        graph[dep].append(rec["skill_id"])
                        in_degree[rec["skill_id"]] = in_degree.get(rec["skill_id"], 0) + 1

            queue = [sid for sid, deg in in_degree.items() if deg == 0]
            sorted_ids = []
            while queue:
                node = queue.pop(0)
                sorted_ids.append(node)
                for neighbor in graph.get(node, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            return sorted_ids

    # --- UPDATE OPERATIONS ---

    @staticmethod
    async def add_skill_node(
        competency_id: str, skill_id: str, name: str,
        description: str = "", level: int = 1,
        difficulty: int = 1, strategy: str = "conceptual",
    ):
        """Add a single skill node to a competency."""
        async with get_neo4j_session() as session:
            await session.run(
                """
                MATCH (c:Competency {id: $comp_id})
                MERGE (s:Skill {id: $skill_id})
                SET s.name = $name, s.description = $desc,
                    s.level = $level, s.difficulty = $diff,
                    s.strategy = $strategy
                MERGE (c)-[:HAS_SKILL]->(s)
                """,
                comp_id=competency_id, skill_id=skill_id,
                name=name, desc=description, level=level,
                diff=difficulty, strategy=strategy,
            )

    @staticmethod
    async def add_prerequisite_edge(
        prerequisite_id: str, dependent_id: str, strength: float = 1.0,
    ):
        """Add a REQUIRES edge between two skills."""
        async with get_neo4j_session() as session:
            await session.run(
                """
                MATCH (prereq:Skill {id: $prereq_id})
                MATCH (dep:Skill {id: $dep_id})
                MERGE (prereq)-[:REQUIRES {strength: $strength}]->(dep)
                """,
                prereq_id=prerequisite_id, dep_id=dependent_id,
                strength=strength,
            )

    @staticmethod
    async def update_employee_mastery(
        employee_id: str, skill_id: str,
        level: int, score: float, confidence: float,
    ):
        """Update or create employee mastery relationship."""
        async with get_neo4j_session() as session:
            await session.run(
                """
                MERGE (e:Employee {id: $emp_id})
                WITH e
                MATCH (s:Skill {id: $skill_id})
                MERGE (e)-[m:HAS_MASTERY]->(s)
                SET m.level = $level,
                    m.score = $score,
                    m.confidence = $confidence,
                    m.updated_at = datetime()
                """,
                emp_id=employee_id, skill_id=skill_id,
                level=level, score=score, confidence=confidence,
            )

    # --- DELETE OPERATIONS ---

    @staticmethod
    async def remove_skill_node(skill_id: str):
        """Remove a skill node and all its relationships."""
        async with get_neo4j_session() as session:
            await session.run(
                "MATCH (s:Skill {id: $skill_id}) DETACH DELETE s",
                skill_id=skill_id,
            )

    @staticmethod
    async def remove_prerequisite_edge(prerequisite_id: str, dependent_id: str):
        """Remove a REQUIRES edge between two skills."""
        async with get_neo4j_session() as session:
            await session.run(
                """
                MATCH (prereq:Skill {id: $prereq_id})-[r:REQUIRES]->(dep:Skill {id: $dep_id})
                DELETE r
                """,
                prereq_id=prerequisite_id, dep_id=dependent_id,
            )

    @staticmethod
    async def delete_competency_subgraph(competency_id: str):
        """Delete entire competency subgraph (competency + all skills + edges)."""
        async with get_neo4j_session() as session:
            await session.run(
                """
                MATCH (c:Competency {id: $comp_id})-[:HAS_SKILL]->(s:Skill)
                DETACH DELETE s
                WITH c
                DETACH DELETE c
                """,
                comp_id=competency_id,
            )

    # --- VALIDATION ---

    @staticmethod
    async def check_cycle(competency_id: str) -> bool:
        """Check if the skill DAG has cycles. Returns True if cycle detected."""
        async with get_neo4j_session() as session:
            result = await session.run(
                """
                MATCH (c:Competency {id: $comp_id})-[:HAS_SKILL]->(s:Skill)
                WITH collect(s) AS skills
                UNWIND skills AS s
                OPTIONAL MATCH path = (s)-[:REQUIRES*]->(s)
                RETURN count(path) > 0 AS has_cycle
                """,
                comp_id=competency_id,
            )
            record = await result.single()
            return record["has_cycle"] if record else False

    @staticmethod
    async def check_all_prerequisites_mastered(
        employee_id: str, skill_id: str,
    ) -> dict:
        """Check if all prerequisites for a skill are mastered by the employee.
        Used by Mastery Evaluation Agent."""
        async with get_neo4j_session() as session:
            result = await session.run(
                """
                MATCH (prereq:Skill)-[:REQUIRES]->(target:Skill {id: $skill_id})
                OPTIONAL MATCH (e:Employee {id: $emp_id})-[m:HAS_MASTERY]->(prereq)
                RETURN prereq.id AS prereq_id,
                       prereq.name AS prereq_name,
                       COALESCE(m.level, 0) AS mastery_level,
                       COALESCE(m.score, 0.0) AS score,
                       prereq.level AS required_level
                """,
                skill_id=skill_id, emp_id=employee_id,
            )
            records = [record.data() async for record in result]
            all_met = all(
                r["mastery_level"] >= 3  # PROFICIENT threshold
                for r in records
            )
            return {
                "all_prerequisites_met": all_met,
                "prerequisites": records,
            }

    @staticmethod
    async def find_similar_skills(skill_name: str, limit: int = 5) -> list[dict]:
        """Find existing skills with similar names (for deduplication)."""
        async with get_neo4j_session() as session:
            result = await session.run(
                """
                MATCH (s:Skill)
                WHERE toLower(s.name) CONTAINS toLower($name)
                RETURN s {.id, .name, .description, .level} AS skill
                LIMIT $limit
                """,
                name=skill_name, limit=limit,
            )
            return [record.data()["skill"] async for record in result]
```

#### Step 5: App Startup/Shutdown Integration

```python
# app/main.py — add to startup/shutdown
from app.core.neo4j import init_neo4j, close_neo4j

@app.on_event("startup")
async def startup_event():
    await init_neo4j()
    # Run constraint creation
    from app.core.neo4j import get_neo4j_session
    async with get_neo4j_session() as session:
        await session.run("CREATE CONSTRAINT competency_id_unique IF NOT EXISTS FOR (c:Competency) REQUIRE c.id IS UNIQUE")
        await session.run("CREATE CONSTRAINT skill_id_unique IF NOT EXISTS FOR (s:Skill) REQUIRE s.id IS UNIQUE")
        await session.run("CREATE CONSTRAINT employee_id_unique IF NOT EXISTS FOR (e:Employee) REQUIRE e.id IS UNIQUE")

@app.on_event("shutdown")
async def shutdown_event():
    await close_neo4j()
```

---

### Configuration & Environment

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password
```

Docker Compose (from Plan 1):
```yaml
neo4j:
    image: neo4j:5-community
    environment:
        NEO4J_AUTH: neo4j/your-neo4j-password
        NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
    ports: ["7474:7474", "7687:7687"]
    volumes: [neo4jdata:/data]
```

Dependencies:
```
neo4j>=5.0
```

---

### Verification Criteria

1. **Neo4j accessible**: Browser at `http://localhost:7474` shows Neo4j console
2. **Constraints created**: `SHOW CONSTRAINTS` in Cypher shell shows 3 uniqueness constraints
3. **Subgraph creation**: Call `create_competency_subgraph()` → verify nodes/edges in Neo4j browser
4. **Skill graph retrieval**: Call `get_skill_graph()` → returns correct nodes and edges
5. **Prerequisite traversal**: Call `get_skill_prerequisites()` → returns recursive chain
6. **Topological sort**: Call `get_topological_order()` → returns dependencies-first order
7. **Cycle detection**: Create a cycle → `check_cycle()` returns True
8. **Mastery check**: `check_all_prerequisites_mastered()` correctly evaluates prerequisite chain
9. **Delete**: `delete_competency_subgraph()` removes all nodes and edges cleanly

### Notes & Gotchas

- **Neo4j Community Edition**: No multi-database support — use the default `neo4j` database
- **APOC plugin**: Include in Docker Compose for advanced path operations if needed
- **Async driver**: Use `neo4j.AsyncGraphDatabase.driver()` — the sync driver will block asyncio
- **UUID as strings**: Neo4j stores UUIDs as strings, not native UUID type — always pass `str(uuid)`
- **Transaction management**: For multi-step operations (create subgraph), consider using explicit transactions for atomicity
- **Graph Data Science plugin**: Listed in Docker Compose but not needed for MVP — useful for future similarity calculations
