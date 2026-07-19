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
