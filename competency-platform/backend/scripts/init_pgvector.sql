-- scripts/init_pgvector.sql
-- Run this once against the competency_db database
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify
SELECT * FROM pg_extension WHERE extname = 'vector';
