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

CREATE TABLE IF NOT EXISTS reinforcement_events (
    reinforcement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    user_id TEXT REFERENCES users(user_id),
    score DOUBLE PRECISION NOT NULL,
    label TEXT NOT NULL,
    task_succeeded BOOLEAN NOT NULL DEFAULT TRUE,
    concise BOOLEAN NOT NULL DEFAULT TRUE,
    helpful BOOLEAN NOT NULL DEFAULT TRUE,
    emotionally_aligned BOOLEAN NOT NULL DEFAULT TRUE,
    reasoning JSONB
);

CREATE TABLE IF NOT EXISTS scheduler_job_locks (
    lock_name TEXT PRIMARY KEY,
    holder TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS proactive_message_audit (
    proactive_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(user_id),
    scheduled_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ,
    message_kind TEXT NOT NULL,
    mood TEXT NOT NULL,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    day_bucket DATE NOT NULL DEFAULT CURRENT_DATE,
    daily_slot SMALLINT,
    details JSONB
);

ALTER TABLE proactive_message_audit
ADD COLUMN IF NOT EXISTS day_bucket DATE NOT NULL DEFAULT CURRENT_DATE;

ALTER TABLE proactive_message_audit
ADD COLUMN IF NOT EXISTS daily_slot SMALLINT;

CREATE UNIQUE INDEX IF NOT EXISTS proactive_daily_slot_unique
ON proactive_message_audit (user_id, day_bucket, daily_slot)
WHERE daily_slot IS NOT NULL;

CREATE TABLE IF NOT EXISTS autonomy_profiles (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id),
    engagement_score DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    initiative_level DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    last_proactive_at TIMESTAMPTZ,
    messages_sent_today INTEGER NOT NULL DEFAULT 0,
    proactive_day DATE,
    error_count_today INTEGER NOT NULL DEFAULT 0,
    last_user_message_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT autonomy_profiles_engagement_bounds CHECK (engagement_score >= 0.1 AND engagement_score <= 1.0),
    CONSTRAINT autonomy_profiles_initiative_bounds CHECK (initiative_level >= 0.1 AND initiative_level <= 1.0)
);

CREATE TABLE IF NOT EXISTS emotional_states (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id),
    current_mood TEXT NOT NULL DEFAULT 'calm',
    mood_intensity DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    shift_date DATE,
    shifts_today INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT emotional_states_intensity_bounds CHECK (mood_intensity >= 0.1 AND mood_intensity <= 1.0)
);

CREATE TABLE IF NOT EXISTS autonomy_reflections (
    reflection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(user_id),
    reflection_date DATE NOT NULL,
    engagement_trend TEXT NOT NULL,
    initiative_adjustment DOUBLE PRECISION NOT NULL,
    notes TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'medium',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, reflection_date)
);

CREATE TABLE IF NOT EXISTS proactive_daily_slots (
    user_id TEXT NOT NULL REFERENCES users(user_id),
    day_bucket DATE NOT NULL,
    slot SMALLINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, day_bucket, slot),
    CONSTRAINT proactive_daily_slot_range CHECK (slot >= 1 AND slot <= 3)
);
