"""Emotion database — connects to the `emotion` database on PostgreSQL."""

import os
import logging
import re
import psycopg2
import psycopg2.extras
from psycopg2 import pool

logger = logging.getLogger("emoji-chat")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "postgres"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "emotion"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(1, 5, **DB_CONFIG)
    return _pool


def _conn():
    c = _get_pool().getconn()
    c.autocommit = True
    return c


def _pg(sql):
    return re.sub(r'\$\d+', '%s', sql)


def q(sql, params=None, fetch="all"):
    sql = _pg(sql)
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            if fetch == "one":
                row = cur.fetchone()
                return dict(row) if row is not None else None
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        logger.warning("Operation failed", exc_info=True)
        return [] if fetch == "all" else None
    finally:
        _get_pool().putconn(conn)


def execute(sql, params=None):
    sql = _pg(sql)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return True
    except Exception:
        logger.warning("Operation failed", exc_info=True)
        return False
    finally:
        _get_pool().putconn(conn)


_init_done = False


def init_db():
    global _init_done
    if _init_done:
        return
    execute("CREATE EXTENSION IF NOT EXISTS vector")

    execute("""
        CREATE TABLE IF NOT EXISTS emotion_cache (
            id SERIAL PRIMARY KEY,
            label VARCHAR(100) UNIQUE NOT NULL,
            eye_curve REAL NOT NULL DEFAULT 0,
            eye_open REAL NOT NULL DEFAULT 0.5,
            eye_pupil REAL NOT NULL DEFAULT 0,
            mouth_curve REAL NOT NULL DEFAULT 0,
            mouth_open REAL NOT NULL DEFAULT 0,
            mouth_width REAL NOT NULL DEFAULT 0.8,
            sparkle REAL NOT NULL DEFAULT 0.5,
            brow_angle REAL NOT NULL DEFAULT 0,
            brow_height REAL NOT NULL DEFAULT 0.5,
            brow_asym REAL NOT NULL DEFAULT 0,
            reply TEXT NOT NULL DEFAULT '',
            sequence_data JSONB,
            use_count INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    # Migration for missing columns
    for col, typ in [
        ("eye_pupil", "REAL NOT NULL DEFAULT 0"),
        ("brow_angle", "REAL NOT NULL DEFAULT 0"),
        ("brow_height", "REAL NOT NULL DEFAULT 0.5"),
        ("brow_asym", "REAL NOT NULL DEFAULT 0"),
        ("sequence_data", "JSONB"),
        ("blush", "REAL NOT NULL DEFAULT 0"),
        ("head_tilt", "REAL NOT NULL DEFAULT 0"),
        ("tear", "REAL NOT NULL DEFAULT 0"),
        ("mouth_asym", "REAL NOT NULL DEFAULT 0"),
        ("eye_wink", "REAL NOT NULL DEFAULT 0"),
        ("eye_tension", "REAL NOT NULL DEFAULT 0"),
        ("iris_size", "REAL NOT NULL DEFAULT 0.5"),
        ("lip_pout", "REAL NOT NULL DEFAULT 0"),
        ("lip_stretch", "REAL NOT NULL DEFAULT 0"),
        ("lip_bite", "REAL NOT NULL DEFAULT 0"),
        ("jaw_drop", "REAL NOT NULL DEFAULT 0"),
        ("tongue_out", "REAL NOT NULL DEFAULT 0"),
        ("nose_wrinkle", "REAL NOT NULL DEFAULT 0"),
        ("cheek_raise", "REAL NOT NULL DEFAULT 0"),
        ("cheek_puff", "REAL NOT NULL DEFAULT 0"),
        ("sweat_drop", "REAL NOT NULL DEFAULT 0"),
        ("vein_pop", "REAL NOT NULL DEFAULT 0"),
        ("color_fields", "TEXT"),
    ]:
        try:
            execute(f"ALTER TABLE emotion_cache ADD COLUMN IF NOT EXISTS {col} {typ}")
        except Exception:
            logger.warning("Operation failed", exc_info=True)

    # Chat history
    execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            user_msg TEXT NOT NULL,
            avatar_reply TEXT NOT NULL DEFAULT '',
            emotion_label VARCHAR(100) NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Semantic memory vectors for similarity search
    execute("""
        CREATE TABLE IF NOT EXISTS memory_vectors (
            id SERIAL PRIMARY KEY,
            chat_id INTEGER NOT NULL REFERENCES chat_history(id),
            embedding halfvec(256),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    execute("""
        CREATE INDEX IF NOT EXISTS idx_memory_vectors_embedding
        ON memory_vectors USING hnsw (embedding halfvec_cosine_ops)
    """)

    # Diary entries
    execute("""
        CREATE TABLE IF NOT EXISTS diary_entries (
            id SERIAL PRIMARY KEY,
            date DATE UNIQUE NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            chat_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Diary entries — dual-perspective columns
    for col, typ in [
        ("user_content", "TEXT DEFAULT ''"),
        ("mood_emoji", "VARCHAR(10) DEFAULT '✨'"),
        ("user_mood_emoji", "VARCHAR(10) DEFAULT ''"),
        ("has_user_diary", "BOOLEAN DEFAULT FALSE"),
    ]:
        try:
            execute(f"ALTER TABLE diary_entries ADD COLUMN IF NOT EXISTS {col} {typ}")
        except Exception:
            pass

    # News items
    execute("""
        CREATE TABLE IF NOT EXISTS news_items (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            source VARCHAR(50) NOT NULL DEFAULT '',
            rank INTEGER NOT NULL DEFAULT 0,
            fetched_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Panksepp affect state (6 primary emotional dimensions)
    execute("""
        CREATE TABLE IF NOT EXISTS affect_state (
            id SERIAL PRIMARY KEY,
            dimension VARCHAR(20) UNIQUE NOT NULL,
            value REAL NOT NULL DEFAULT 0.0,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Performance indexes
    execute("CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON chat_history (created_at)")
    execute("CREATE INDEX IF NOT EXISTS idx_memory_vectors_chat_id ON memory_vectors (chat_id)")
    execute("CREATE INDEX IF NOT EXISTS idx_emotion_cache_use_count ON emotion_cache (use_count DESC)")

    # ── Drift detection tables (Mahalanobis + multi-level) ────────────

    execute("""
        CREATE TABLE IF NOT EXISTS drift_baseline (
            id SERIAL PRIMARY KEY,
            mean_embedding halfvec(256),
            covariance_diag halfvec(256),
            built_at TIMESTAMP DEFAULT NOW(),
            sample_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS drift_coreset (
            id SERIAL PRIMARY KEY,
            reply_text TEXT NOT NULL,
            embedding halfvec(256),
            weight REAL NOT NULL DEFAULT 1.0,
            distance REAL NOT NULL DEFAULT 0.0,
            recorded_at TIMESTAMP DEFAULT NOW()
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS drift_log (
            id SERIAL PRIMARY KEY,
            level VARCHAR(10) NOT NULL,
            mahalanobis_distance REAL NOT NULL,
            predicted_distance REAL,
            turns_until_threshold REAL,
            intervention TEXT,
            details JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── Knowledge graph tables ───────────────────────────────────────

    execute("""
        CREATE TABLE IF NOT EXISTS kg_entities (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            type VARCHAR(50) NOT NULL DEFAULT 'unknown',
            first_seen TIMESTAMP DEFAULT NOW(),
            last_seen TIMESTAMP DEFAULT NOW(),
            metadata JSONB DEFAULT '{}',
            UNIQUE(name, type)
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS kg_relationships (
            id SERIAL PRIMARY KEY,
            source_id INTEGER NOT NULL REFERENCES kg_entities(id),
            target_id INTEGER NOT NULL REFERENCES kg_entities(id),
            relation VARCHAR(100) NOT NULL,
            valid_at TIMESTAMP DEFAULT NOW(),
            invalid_at TIMESTAMP DEFAULT NULL,
            strength REAL NOT NULL DEFAULT 0.5,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    execute("CREATE INDEX IF NOT EXISTS idx_kg_entities_name ON kg_entities(name)")
    execute("CREATE INDEX IF NOT EXISTS idx_kg_entities_last_seen ON kg_entities(last_seen)")

    # ── Predictive agent table ───────────────────────────────────────

    execute("""
        CREATE TABLE IF NOT EXISTS prediction_history (
            id SERIAL PRIMARY KEY,
            predicted_need VARCHAR(50),
            predicted_emotion VARCHAR(50),
            predicted_topic VARCHAR(200),
            actual_need VARCHAR(50),
            actual_emotion VARCHAR(50),
            actual_topic VARCHAR(200),
            prediction_error REAL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── Dual-system insights table ────────────────────────────────────

    execute("""
        CREATE TABLE IF NOT EXISTS system2_insights (
            id SERIAL PRIMARY KEY,
            insight TEXT NOT NULL,
            source_message TEXT,
            category VARCHAR(50),
            applied_to_system1 BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    _init_done = True
