CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    mode TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_interaction TIMESTAMPTZ,
    preferences JSONB
);


DO $$
DECLARE
    existing_pk_name TEXT;
BEGIN
    -- Legacy app table (memory_id/memory_text) conflicts with Mem0 pgvector storage (id/vector/payload).
    -- Rename only that old app-specific shape so Mem0 can create/manage the active collection table.
    IF to_regclass('public.memories') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'memories' AND column_name = 'memory_text'
       )
       AND NOT EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'memories' AND column_name = 'payload'
       ) THEN
        IF to_regclass('public.memories_legacy') IS NULL THEN
            ALTER TABLE public.memories RENAME TO memories_legacy;
        END IF;
    END IF;

    -- Older Mem0 pgvector variants may have vector/payload but no `id` column.
    -- Add and backfill `id` so current Mem0 queries (SELECT id, vector <=> ...) work.
    IF to_regclass('public.memories') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'memories' AND column_name = 'vector'
       )
       AND EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'memories' AND column_name = 'payload'
       )
       AND NOT EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'memories' AND column_name = 'id'
       ) THEN
        ALTER TABLE public.memories ADD COLUMN id UUID;

        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'memories' AND column_name = 'memory_id'
        ) THEN
            EXECUTE 'UPDATE public.memories SET id = memory_id::uuid WHERE id IS NULL';
        END IF;

        UPDATE public.memories SET id = gen_random_uuid() WHERE id IS NULL;
        ALTER TABLE public.memories ALTER COLUMN id SET NOT NULL;

        SELECT c.conname
        INTO existing_pk_name
        FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        JOIN pg_namespace n ON t.relnamespace = n.oid
        WHERE n.nspname = 'public' AND t.relname = 'memories' AND c.contype = 'p'
        LIMIT 1;

        IF existing_pk_name IS NOT NULL THEN
            EXECUTE format('ALTER TABLE public.memories DROP CONSTRAINT %I', existing_pk_name);
        END IF;

        ALTER TABLE public.memories ADD PRIMARY KEY (id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS personality_states (
    state_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(user_id),
    warmth INTEGER,
    curiosity INTEGER,
    assertiveness INTEGER,
    humor INTEGER,
    emotional_depth INTEGER,
    version INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    changes JSONB
);

CREATE TABLE IF NOT EXISTS conversation_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(user_id),
    role TEXT,
    message TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS decision_logs (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    event_type TEXT NOT NULL,
    user_id TEXT REFERENCES users(user_id),
    source TEXT NOT NULL,
    summary TEXT NOT NULL,
    details JSONB
);
