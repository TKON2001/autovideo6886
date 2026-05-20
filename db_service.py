import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path("bot_data.sqlite3")
TRIAL_CREDITS = 2

PRICING_PACKAGES = {
    "starter": {
        "name": "Starter",
        "amount_vnd": 200_000,
        "credits": 40,
        "label": "Gói Starter - 200.000đ",
    },
    "creator": {
        "name": "Creator",
        "amount_vnd": 500_000,
        "credits": 120,
        "label": "Gói Creator - 500.000đ",
    },
    "pro": {
        "name": "Pro",
        "amount_vnd": 1_000_000,
        "credits": 300,
        "label": "Gói Pro - 1.000.000đ",
    },
    "agency": {
        "name": "Agency",
        "amount_vnd": 2_000_000,
        "credits": 700,
        "label": "Gói Agency - 2.000.000đ",
    },
}

VIDEO_CREDIT_COSTS = {
    "quick": 2,
    "fact": 4,
    "story": 4,
    "deep": 7,
    "premium": 10,
}

VALID_PACKAGES = {"trial", "starter", "creator", "pro", "agency"}


@dataclass(frozen=True)
class UserAccount:
    telegram_user_id: int
    username: str | None
    first_name: str | None
    role: str
    package_name: str
    credit_balance: int
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sqlite_timeout_seconds() -> int:
    try:
        return max(1, int(os.getenv("SQLITE_TIMEOUT_SECONDS", "30")))
    except ValueError:
        return 30


def _connect() -> sqlite3.Connection:
    timeout = _sqlite_timeout_seconds()
    conn = sqlite3.connect(
        DB_PATH,
        timeout=timeout,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={timeout * 1000}")
    return conn


def init_database() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                role TEXT NOT NULL DEFAULT 'free_user',
                package_name TEXT NOT NULL DEFAULT 'trial',
                credit_balance INTEGER NOT NULL DEFAULT 2,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        _migrate_users_table(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                package_name TEXT NOT NULL,
                amount_vnd INTEGER NOT NULL,
                credits_added INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                credits_change INTEGER NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                chat_id INTEGER,
                topic TEXT NOT NULL,
                quality TEXT NOT NULL DEFAULT 'deep',
                required_credits INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'queued',
                sop_state TEXT NOT NULL DEFAULT 'input',
                progress_percent INTEGER NOT NULL DEFAULT 0,
                estimated_total_seconds INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                output_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (telegram_user_id) REFERENCES users(telegram_user_id)
            )
            """
        )
        _migrate_jobs_table(conn)
        _create_indexes(conn)
        conn.commit()


def _migrate_users_table(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }

    migrations = {
        "first_name": "ALTER TABLE users ADD COLUMN first_name TEXT",
        "role": "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'free_user'",
        "package_name": (
            "ALTER TABLE users ADD COLUMN package_name TEXT NOT NULL DEFAULT 'trial'"
        ),
        "updated_at": "ALTER TABLE users ADD COLUMN updated_at TEXT",
    }

    for column, sql in migrations.items():
        if column not in columns:
            conn.execute(sql)

    now = _now()
    conn.execute("UPDATE users SET role = 'free_user' WHERE role IS NULL OR role = ''")
    conn.execute(
        "UPDATE users SET package_name = 'trial' "
        "WHERE package_name IS NULL OR package_name = ''"
    )
    conn.execute(
        "UPDATE users SET updated_at = COALESCE(created_at, ?) "
        "WHERE updated_at IS NULL OR updated_at = ''",
        (now,),
    )


def _migrate_jobs_table(conn: sqlite3.Connection) -> None:
    """Migrate jobs table schema."""
    try:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
    except Exception:
        # Table doesn't exist yet, no migration needed
        return
    
    # Add new columns if they don't exist
    migrations = {
        "chat_id": "ALTER TABLE jobs ADD COLUMN chat_id INTEGER",
        "required_credits": "ALTER TABLE jobs ADD COLUMN required_credits INTEGER NOT NULL DEFAULT 0",
        "quality": "ALTER TABLE jobs ADD COLUMN quality TEXT NOT NULL DEFAULT 'deep'",
        "status": "ALTER TABLE jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'",
        "progress_percent": "ALTER TABLE jobs ADD COLUMN progress_percent INTEGER NOT NULL DEFAULT 0",
        "estimated_total_seconds": "ALTER TABLE jobs ADD COLUMN estimated_total_seconds INTEGER NOT NULL DEFAULT 0",
    }
    
    for column, sql in migrations.items():
        if column not in columns:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # Column might already exist

    conn.execute("UPDATE jobs SET status = 'queued' WHERE status = 'pending'")
    conn.execute(
        "UPDATE jobs SET status = 'processing' "
        "WHERE status IN ('analyzing', 'generating', 'rendering', 'validated')"
    )
    conn.execute(
        "UPDATE jobs SET required_credits = ? "
        "WHERE required_credits IS NULL OR required_credits = 0",
        (VIDEO_CREDIT_COSTS["deep"],),
    )


def _create_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_telegram_user_id "
        "ON users(telegram_user_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_telegram_user_id "
        "ON jobs(telegram_user_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_status "
        "ON jobs(status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_created_at "
        "ON jobs(created_at)"
    )


def _row_to_user(row: sqlite3.Row) -> UserAccount:
    return UserAccount(
        telegram_user_id=row["telegram_user_id"],
        username=row["username"],
        first_name=row["first_name"],
        role=row["role"],
        package_name=row["package_name"],
        credit_balance=row["credit_balance"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def ensure_user(
    telegram_user_id: int,
    username: str | None,
    first_name: str | None = None,
) -> UserAccount:
    now = _now()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()

        if row:
            conn.execute(
                """
                UPDATE users
                SET username = ?, first_name = COALESCE(?, first_name), updated_at = ?
                WHERE telegram_user_id = ?
                """,
                (username, first_name, now, telegram_user_id),
            )
            row = conn.execute(
                "SELECT * FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()
            return _row_to_user(row)

        conn.execute(
            """
            INSERT INTO users (
                telegram_user_id,
                username,
                first_name,
                role,
                package_name,
                credit_balance,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_user_id,
                username,
                first_name,
                "free_user",
                "trial",
                TRIAL_CREDITS,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO credit_logs
                (telegram_user_id, action, credits_change, description, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                telegram_user_id,
                "trial_grant",
                TRIAL_CREDITS,
                "Tặng credit dùng thử khi bắt đầu bot",
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        return _row_to_user(row)


def get_balance(telegram_user_id: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT credit_balance FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        return int(row["credit_balance"]) if row else 0


def get_user(telegram_user_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        return dict(row) if row else None


def get_all_users(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                telegram_user_id,
                username,
                first_name,
                package_name,
                credit_balance,
                created_at,
                updated_at
            FROM users
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def add_credits(
    telegram_user_id: int,
    credits: int,
    action: str = "admin_add",
    description: str = "Admin cộng credit thủ công",
) -> int:
    if credits <= 0:
        raise ValueError("credits must be greater than 0")

    now = _now()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO users
                    (
                        telegram_user_id,
                        username,
                        first_name,
                        role,
                        package_name,
                        credit_balance,
                        created_at,
                        updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (telegram_user_id, None, None, "free_user", "trial", 0, now, now),
            )

        conn.execute(
            """
            UPDATE users
            SET credit_balance = credit_balance + ?, updated_at = ?
            WHERE telegram_user_id = ?
            """,
            (credits, now, telegram_user_id),
        )
        conn.execute(
            """
            INSERT INTO credit_logs
                (telegram_user_id, action, credits_change, description, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (telegram_user_id, action, credits, description, now),
        )
        row = conn.execute(
            "SELECT credit_balance FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        return int(row["credit_balance"])


def set_credits(telegram_user_id: int, credits: int) -> int:
    if credits < 0:
        raise ValueError("credits must be greater than or equal to 0")

    now = _now()
    with _connect() as conn:
        row = conn.execute(
            "SELECT credit_balance FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        if not row:
            raise ValueError("User does not exist")

        credits_change = credits - int(row["credit_balance"])
        conn.execute(
            """
            UPDATE users
            SET credit_balance = ?, updated_at = ?
            WHERE telegram_user_id = ?
            """,
            (credits, now, telegram_user_id),
        )
        conn.execute(
            """
            INSERT INTO credit_logs
                (telegram_user_id, action, credits_change, description, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                telegram_user_id,
                "admin_set",
                credits_change,
                "Admin đặt lại số dư credit",
                now,
            ),
        )
        return credits


def set_package(telegram_user_id: int, package_name: str) -> str:
    if package_name not in VALID_PACKAGES:
        raise ValueError("Invalid package")

    now = _now()
    with _connect() as conn:
        row = conn.execute(
            "SELECT telegram_user_id FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        if not row:
            raise ValueError("User does not exist")

        conn.execute(
            """
            UPDATE users
            SET package_name = ?, updated_at = ?
            WHERE telegram_user_id = ?
            """,
            (package_name, now, telegram_user_id),
        )
        return package_name


def deduct_credits(
    telegram_user_id: int,
    credits: int,
    description: str,
) -> int:
    if credits <= 0:
        raise ValueError("credits must be greater than 0")

    now = _now()
    with _connect() as conn:
        row = conn.execute(
            "SELECT credit_balance FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        if not row:
            raise ValueError("User does not exist")

        balance = int(row["credit_balance"])
        if balance < credits:
            raise ValueError("Insufficient credits")

        conn.execute(
            """
            UPDATE users
            SET credit_balance = credit_balance - ?, updated_at = ?
            WHERE telegram_user_id = ?
            """,
            (credits, now, telegram_user_id),
        )
        conn.execute(
            """
            INSERT INTO credit_logs
                (telegram_user_id, action, credits_change, description, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (telegram_user_id, "video_deduct", -credits, description, now),
        )

        return balance - credits


def create_pending_purchase(telegram_user_id: int, package_key: str) -> int:
    package = PRICING_PACKAGES.get(package_key)
    if not package:
        raise ValueError("Unknown package")

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO purchases
                (telegram_user_id, package_name, amount_vnd, credits_added, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_user_id,
                package["name"],
                package["amount_vnd"],
                package["credits"],
                "pending",
                _now(),
            ),
        )
        return int(cursor.lastrowid)


def get_video_credit_cost(mode: str) -> int:
    return VIDEO_CREDIT_COSTS.get(mode, VIDEO_CREDIT_COSTS["deep"])


# Job state machine functions
@dataclass(frozen=True)
class VideoJob:
    """Video job record."""
    id: int
    job_id: str
    telegram_user_id: int
    chat_id: int | None
    topic: str
    quality: str
    required_credits: int
    status: str
    sop_state: str
    progress_percent: int
    estimated_total_seconds: int
    error_message: str | None
    output_path: str | None
    created_at: str
    updated_at: str


def create_job(
    job_id: str,
    telegram_user_id: int,
    topic: str,
    chat_id: int | None = None,
    quality: str = "deep",
    required_credits: int = 0,
    status: str = "queued",
    estimated_total_seconds: int = 0,
    max_active_jobs_per_user: int | None = None,
) -> VideoJob:
    """Create a new video job in input state."""
    now = _now()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if max_active_jobs_per_user is not None:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM jobs
                WHERE telegram_user_id = ?
                  AND status IN ('queued', 'processing')
                """,
                (telegram_user_id,),
            ).fetchone()
            active_count = int(row["count"]) if row else 0
            if active_count >= max_active_jobs_per_user:
                raise ValueError("active_job_exists")

        conn.execute(
            """
            INSERT INTO jobs
                (job_id, telegram_user_id, chat_id, topic, quality, required_credits,
                 status, sop_state,
                 progress_percent, estimated_total_seconds, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                telegram_user_id,
                chat_id,
                topic,
                quality,
                required_credits,
                status,
                "input",
                0,
                estimated_total_seconds,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return _row_to_job(row) if row else None


def update_job_state(
    job_id: str,
    sop_state: str,
    status: str = None,
    progress_percent: int = None,
) -> VideoJob:
    """Update job state in the SOP workflow.
    
    SOP states: input → processing → output → archive (or failed)
    """
    now = _now()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        
        if not row:
            raise ValueError(f"Job not found: {job_id}")
        
        updates = ["sop_state = ?", "updated_at = ?"]
        params = [sop_state, now]
        
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        
        if progress_percent is not None:
            updates.append("progress_percent = ?")
            params.append(progress_percent)
        
        params.append(job_id)
        
        conn.execute(
            f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?",
            params,
        )
        
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return _row_to_job(row) if row else None


def update_job_status(
    job_id: str,
    status: str,
    progress_percent: int = None,
    error_message: str = None,
    output_path: str = None,
) -> VideoJob | None:
    """Update the high-level job status used by the queue workers."""
    now = _now()
    with _connect() as conn:
        updates = ["status = ?", "updated_at = ?"]
        params = [status, now]

        if progress_percent is not None:
            updates.append("progress_percent = ?")
            params.append(progress_percent)

        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)

        if output_path is not None:
            updates.append("output_path = ?")
            params.append(output_path)

        if status == "processing":
            updates.append("sop_state = ?")
            params.append("processing")
        elif status == "completed":
            updates.append("sop_state = ?")
            params.append("archive")
        elif status == "failed":
            updates.append("sop_state = ?")
            params.append("failed")
        elif status == "queued":
            updates.append("sop_state = ?")
            params.append("input")

        params.append(job_id)
        conn.execute(
            f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?",
            params,
        )

        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return _row_to_job(row) if row else None


def mark_job_failed(job_id: str, error_message: str) -> VideoJob:
    """Mark job as failed with error message."""
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, sop_state = ?, error_message = ?, updated_at = ?
            WHERE job_id = ?
            """,
            ("failed", "failed", error_message, now, job_id),
        )
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return _row_to_job(row) if row else None


def mark_job_completed(job_id: str, output_path: str) -> VideoJob:
    """Mark job as completed with output path.
    
    Transitions to 'archive' state when video is successfully sent to user.
    """
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, sop_state = ?, output_path = ?, progress_percent = ?, updated_at = ?
            WHERE job_id = ?
            """,
            ("completed", "archive", output_path, 100, now, job_id),
        )
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return _row_to_job(row) if row else None


def get_job(job_id: str) -> VideoJob | None:
    """Get job by job_id."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return _row_to_job(row) if row else None


def get_user_jobs(telegram_user_id: int, limit: int = 20) -> list[VideoJob]:
    """Get recent jobs for a user."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE telegram_user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (telegram_user_id, limit),
        ).fetchall()
        return [_row_to_job(row) for row in rows]


def get_active_job_by_user(telegram_user_id: int) -> VideoJob | None:
    """Return the oldest queued/processing job for a user, if any."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM jobs
            WHERE telegram_user_id = ?
              AND status IN ('queued', 'processing')
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (telegram_user_id,),
        ).fetchone()
        return _row_to_job(row) if row else None


def count_active_jobs_by_user(telegram_user_id: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count FROM jobs
            WHERE telegram_user_id = ?
              AND status IN ('queued', 'processing')
            """,
            (telegram_user_id,),
        ).fetchone()
        return int(row["count"]) if row else 0


def count_user_jobs_today(telegram_user_id: int) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count FROM jobs
            WHERE telegram_user_id = ?
              AND date(created_at) = ?
            """,
            (telegram_user_id, today),
        ).fetchone()
        return int(row["count"]) if row else 0


def get_queued_jobs(limit: int = 100) -> list[VideoJob]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_job(row) for row in rows]


def recover_processing_jobs() -> int:
    """Move jobs left in processing during a previous shutdown back to queued."""
    now = _now()
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE jobs
            SET status = 'queued',
                sop_state = 'input',
                error_message = COALESCE(error_message || ' | ', '') || ?,
                updated_at = ?
            WHERE status = 'processing'
            """,
            ("Recovered after restart", now),
        )
        return int(cursor.rowcount)


def _row_to_job(row: sqlite3.Row) -> VideoJob:
    """Convert database row to VideoJob."""
    return VideoJob(
        id=row["id"],
        job_id=row["job_id"],
        telegram_user_id=row["telegram_user_id"],
        chat_id=row["chat_id"],
        topic=row["topic"],
        quality=row["quality"],
        required_credits=row["required_credits"],
        status=row["status"],
        sop_state=row["sop_state"],
        progress_percent=row["progress_percent"],
        estimated_total_seconds=row["estimated_total_seconds"],
        error_message=row["error_message"],
        output_path=row["output_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# Operational management functions for founder/operator
def get_jobs_recent(limit: int = 20) -> list[dict]:
    """Get recent video jobs for monitoring."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT 
                job_id, telegram_user_id, chat_id, topic, quality, required_credits,
                status, sop_state, progress_percent, created_at, updated_at
            FROM jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_recent_jobs(limit: int = 20) -> list[dict]:
    return get_jobs_recent(limit)


def get_job_stats() -> dict:
    """Get statistics about all video jobs."""
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) as count FROM jobs").fetchone()
        successful = conn.execute(
            "SELECT COUNT(*) as count FROM jobs WHERE sop_state = ?",
            ("archive",),
        ).fetchone()
        failed = conn.execute(
            "SELECT COUNT(*) as count FROM jobs WHERE status = ?",
            ("failed",),
        ).fetchone()
        processing = conn.execute(
            "SELECT COUNT(*) as count FROM jobs WHERE status = ?",
            ("processing",),
        ).fetchone()
        queued = conn.execute(
            "SELECT COUNT(*) as count FROM jobs WHERE status = ?",
            ("queued",),
        ).fetchone()
        
        return {
            "total_jobs": int(total["count"]) if total else 0,
            "successful_jobs": int(successful["count"]) if successful else 0,
            "failed_jobs": int(failed["count"]) if failed else 0,
            "processing_jobs": int(processing["count"]) if processing else 0,
            "queued_jobs": int(queued["count"]) if queued else 0,
        }


def get_system_stats() -> dict:
    """Get comprehensive system statistics."""
    with _connect() as conn:
        # User stats
        total_users = conn.execute(
            "SELECT COUNT(*) as count FROM users"
        ).fetchone()
        total_users = int(total_users["count"]) if total_users else 0
        
        # Credit stats
        total_credits = conn.execute(
            "SELECT SUM(credit_balance) as total FROM users"
        ).fetchone()
        total_credits = int(total_credits["total"]) if total_credits["total"] else 0
        
        # Job stats
        job_stats = get_job_stats()
        
        # Users with low/no credit
        low_credit = conn.execute(
            "SELECT COUNT(*) as count FROM users WHERE credit_balance <= 5"
        ).fetchone()
        low_credit_count = int(low_credit["count"]) if low_credit else 0
        
        # Users who made purchases
        paid_users = conn.execute(
            "SELECT COUNT(DISTINCT telegram_user_id) as count FROM purchases WHERE status = ?",
            ("pending",),
        ).fetchone()
        paid_users_count = int(paid_users["count"]) if paid_users else 0
        
        # Today's jobs
        from datetime import datetime, timedelta, timezone
        today = datetime.now(timezone.utc).date()
        today_jobs = conn.execute(
            """
            SELECT COUNT(*) as count FROM jobs 
            WHERE date(created_at) = ?
            """,
            (today.isoformat(),),
        ).fetchone()
        today_jobs_count = int(today_jobs["count"]) if today_jobs else 0
        
        return {
            "total_users": total_users,
            "total_credits": total_credits,
            "users_low_credit": low_credit_count,
            "pending_payments": paid_users_count,
            "today_jobs": today_jobs_count,
            **job_stats,
        }


def get_users_low_credit(threshold: int = 5) -> list[dict]:
    """Get users with credit balance at or below threshold."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT 
                telegram_user_id, username, first_name, package_name, 
                credit_balance, created_at
            FROM users
            WHERE credit_balance <= ?
            ORDER BY credit_balance ASC
            """,
            (threshold,),
        ).fetchall()
        return [dict(row) for row in rows]


def count_total_users() -> int:
    """Count total registered users."""
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
        return int(row["count"]) if row else 0
