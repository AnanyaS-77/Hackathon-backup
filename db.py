import json
import sqlite3
import time
from pathlib import Path

from flask import current_app, g
from werkzeug.security import check_password_hash, generate_password_hash

ROUNDS = ("round1", "round2", "round3", "round4")
DEFAULT_ROUND_STATUS = {
    "round1": "unlocked",
    "round2": "locked",
    "round3": "locked",
    "round4": "locked",
}
DATA_FILE = "data.json"
SETTINGS_FILE = "settings.json"


def load_seed_data():
    data_path = Path(current_app.root_path) / DATA_FILE
    if not data_path.exists():
        return {}

    with data_path.open() as file:
        return json.load(file)


def load_seed_settings():
    settings_path = Path(current_app.root_path) / SETTINGS_FILE
    if not settings_path.exists():
        return {"round_status": DEFAULT_ROUND_STATUS.copy()}

    with settings_path.open() as file:
        return json.load(file)


def get_db():
    if "db" not in g:
        database_path = current_app.config["DATABASE"]
        g.db = sqlite3.connect(database_path, timeout=30, isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
        g.db.execute("PRAGMA synchronous = NORMAL")

    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_code TEXT NOT NULL UNIQUE,
            team_name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS answers (
            team_id INTEGER NOT NULL,
            round TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            PRIMARY KEY (team_id, round),
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS progress (
            team_id INTEGER NOT NULL,
            round TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            timestamp REAL,
            PRIMARY KEY (team_id, round),
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS round_settings (
            round TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('locked', 'unlocked'))
        );
        """
    )
    bootstrap_database()
    sync_seed_data()


def bootstrap_database():
    db = get_db()
    existing_team = db.execute("SELECT id FROM teams LIMIT 1").fetchone()
    existing_settings = db.execute("SELECT round FROM round_settings LIMIT 1").fetchone()

    if existing_team and existing_settings:
        ensure_round_settings(DEFAULT_ROUND_STATUS)
        return

    db.execute("BEGIN IMMEDIATE")
    try:
        if not existing_team:
            migrate_legacy_team_data(db)

        if not existing_settings:
            migrate_legacy_round_settings(db)

        db.commit()
    except Exception:
        db.rollback()
        raise

    ensure_round_settings(DEFAULT_ROUND_STATUS)


def migrate_legacy_team_data(db):
    legacy_data = load_seed_data()
    if not legacy_data:
        return

    for team_code, team_data in legacy_data.items():
        cursor = db.execute(
            "INSERT INTO teams (team_code, team_name) VALUES (?, ?)",
            (team_code.strip().upper(), team_data["team_name"].strip()),
        )
        team_id = cursor.lastrowid

        answers = team_data.get("answers", {})
        attempts = team_data.get("attempts", {})
        completed = team_data.get("completed", {})
        timestamps = team_data.get("timestamps", {})

        for round_name in ROUNDS:
            raw_answer = str(answers.get(round_name, "")).strip().upper()
            answer_hash = generate_password_hash(raw_answer) if raw_answer else generate_password_hash("INVALID")
            db.execute(
                "INSERT INTO answers (team_id, round, correct_answer) VALUES (?, ?, ?)",
                (team_id, round_name, answer_hash),
            )
            db.execute(
                """
                INSERT INTO progress (team_id, round, attempts, completed, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    team_id,
                    round_name,
                    int(attempts.get(round_name, 0)),
                    1 if completed.get(round_name, False) else 0,
                    timestamps.get(round_name),
                ),
            )


def migrate_legacy_round_settings(db):
    round_status = DEFAULT_ROUND_STATUS.copy()
    legacy_settings = load_seed_settings()

    for round_name in ROUNDS:
        legacy_status = legacy_settings.get("round_status", {}).get(round_name)
        if legacy_status in {"locked", "unlocked"}:
            round_status[round_name] = legacy_status

    ensure_round_settings(round_status, db=db)


def ensure_round_settings(status_map, db=None, overwrite=False):
    connection = db or get_db()
    for round_name in ROUNDS:
        status = status_map.get(round_name, DEFAULT_ROUND_STATUS[round_name])
        if overwrite:
            connection.execute(
                """
                INSERT INTO round_settings (round, status)
                VALUES (?, ?)
                ON CONFLICT(round) DO UPDATE SET status = excluded.status
                """,
                (round_name, status),
            )
        else:
            connection.execute(
                "INSERT OR IGNORE INTO round_settings (round, status) VALUES (?, ?)",
                (round_name, status),
            )


def sync_seed_data(reset_progress=False):
    db = get_db()
    seed_data = load_seed_data()
    seed_settings = load_seed_settings()

    db.execute("BEGIN IMMEDIATE")
    try:
        for raw_team_code, team_data in seed_data.items():
            team_code = raw_team_code.strip().upper()
            team_name = str(team_data.get("team_name", "")).strip() or team_code

            team_row = db.execute(
                "SELECT id FROM teams WHERE team_code = ?",
                (team_code,),
            ).fetchone()

            if team_row is None:
                cursor = db.execute(
                    "INSERT INTO teams (team_code, team_name) VALUES (?, ?)",
                    (team_code, team_name),
                )
                team_id = cursor.lastrowid
            else:
                team_id = team_row["id"]
                db.execute(
                    "UPDATE teams SET team_name = ? WHERE id = ?",
                    (team_name, team_id),
                )

            answers = team_data.get("answers", {})
            attempts = team_data.get("attempts", {})
            completed = team_data.get("completed", {})
            timestamps = team_data.get("timestamps", {})

            for round_name in ROUNDS:
                raw_answer = str(answers.get(round_name, "")).strip().upper()
                answer_hash = generate_password_hash(raw_answer) if raw_answer else generate_password_hash("INVALID")

                db.execute(
                    """
                    INSERT INTO answers (team_id, round, correct_answer)
                    VALUES (?, ?, ?)
                    ON CONFLICT(team_id, round) DO UPDATE SET correct_answer = excluded.correct_answer
                    """,
                    (team_id, round_name, answer_hash),
                )

                if reset_progress:
                    db.execute(
                        """
                        INSERT INTO progress (team_id, round, attempts, completed, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(team_id, round) DO UPDATE SET
                            attempts = excluded.attempts,
                            completed = excluded.completed,
                            timestamp = excluded.timestamp
                        """,
                        (
                            team_id,
                            round_name,
                            int(attempts.get(round_name, 0)),
                            1 if completed.get(round_name, False) else 0,
                            timestamps.get(round_name),
                        ),
                    )
                else:
                    db.execute(
                        """
                        INSERT OR IGNORE INTO progress (team_id, round, attempts, completed, timestamp)
                        VALUES (?, ?, 0, 0, NULL)
                        """,
                        (team_id, round_name),
                    )

        round_status = DEFAULT_ROUND_STATUS.copy()
        for round_name in ROUNDS:
            next_status = seed_settings.get("round_status", {}).get(round_name)
            if next_status in {"locked", "unlocked"}:
                round_status[round_name] = next_status

        ensure_round_settings(round_status, db=db, overwrite=True)
        db.commit()
    except Exception:
        db.rollback()
        raise


def reset_event():
    """
    Reset event progress without deleting teams, answers, or round settings.
    """
    db = get_db()
    db.execute("BEGIN IMMEDIATE")

    try:
        cursor = db.execute(
            """
            UPDATE progress
            SET attempts = 0,
                completed = 0,
                timestamp = NULL
            """
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "reset_progress_rows": cursor.rowcount,
        "teams_deleted": 0,
        "answers_deleted": 0,
    }


def get_team_by_code(team_code):
    return get_team(team_code=team_code)


def get_team(team_id=None, team_code=None):
    if team_id is None and team_code is None:
        raise ValueError("get_team requires team_id or team_code.")

    db = get_db()
    if team_code is not None:
        row = db.execute(
            "SELECT id, team_code, team_name FROM teams WHERE team_code = ?",
            (team_code,),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT id, team_code, team_name FROM teams WHERE id = ?",
            (team_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "team_id": row["id"],
        "team_code": row["team_code"],
        "team_name": row["team_name"],
    }


def get_team_view(team_id):
    return get_team(team_id=team_id)


def get_progress(team_id, round_name=None):
    db = get_db()

    if round_name is not None:
        row = db.execute(
            """
            SELECT
                p.team_id,
                p.round,
                p.attempts,
                p.completed,
                p.timestamp,
                rs.status AS round_status,
                a.correct_answer
            FROM progress p
            JOIN round_settings rs ON rs.round = p.round
            LEFT JOIN answers a ON a.team_id = p.team_id AND a.round = p.round
            WHERE p.team_id = ? AND p.round = ?
            """,
            (team_id, round_name),
        ).fetchone()
        if row is None:
            return None

        return {
            "team_id": row["team_id"],
            "round": row["round"],
            "attempts": int(row["attempts"]),
            "completed": bool(row["completed"]),
            "timestamp": row["timestamp"],
            "round_status": row["round_status"],
            "correct_answer": row["correct_answer"],
        }

    rows = db.execute(
        """
        SELECT
            p.team_id,
            p.round,
            p.attempts,
            p.completed,
            p.timestamp,
            rs.status AS round_status
        FROM progress p
        JOIN round_settings rs ON rs.round = p.round
        WHERE p.team_id = ?
        ORDER BY p.round
        """,
        (team_id,),
    ).fetchall()

    return [
        {
            "team_id": row["team_id"],
            "round": row["round"],
            "attempts": int(row["attempts"]),
            "completed": bool(row["completed"]),
            "timestamp": row["timestamp"],
            "round_status": row["round_status"],
        }
        for row in rows
    ]


def update_progress(team_id, round_name, attempts, completed, timestamp=None):
    get_db().execute(
        """
        UPDATE progress
        SET attempts = ?, completed = ?, timestamp = COALESCE(?, timestamp)
        WHERE team_id = ? AND round = ?
        """,
        (attempts, 1 if completed else 0, timestamp, team_id, round_name),
    )


def get_round_cards_for_team(team_id, arena_urls):
    rows = get_progress(team_id)

    cards = []
    for index, row in enumerate(rows, start=1):
        attempts_used = int(row["attempts"])
        attempts_left = max(0, 2 - attempts_used)
        completed = bool(row["completed"])
        unlocked = row["round_status"] == "unlocked"

        if completed:
            status = "completed"
        elif unlocked:
            status = "unlocked"
        else:
            status = "locked"

        cards.append(
            {
                "id": row["round"],
                "label": f"Round {index}",
                "status": status,
                "completed": completed,
                "unlocked": unlocked,
                "attempts_used": attempts_used,
                "attempts_left": attempts_left,
                "arena_url": arena_urls.get(row["round"]),
            }
        )

    return cards


def submit_round_answer(team_id, round_name, answer):
    db = get_db()
    # BEGIN IMMEDIATE prevents concurrent submissions from racing the same row update.
    db.execute("BEGIN IMMEDIATE")

    try:
        row = get_progress(team_id, round_name)

        if row is None:
            db.rollback()
            return {"ok": False, "message": "Invalid round selected!"}

        if row["round_status"] != "unlocked":
            db.rollback()
            return {"ok": False, "message": "This round is locked by admin!"}

        if bool(row["completed"]):
            db.rollback()
            return {"ok": False, "message": "Already completed!"}

        attempts_used = int(row["attempts"])
        if attempts_used >= 2:
            db.rollback()
            return {"ok": False, "message": "No attempts left!"}

        attempts_used += 1
        is_correct = check_password_hash(row["correct_answer"], answer)
        completion_timestamp = time.time() if is_correct else None

        update_progress(team_id, round_name, attempts_used, is_correct, completion_timestamp)
        db.commit()

        if is_correct:
            return {"ok": True, "message": f"{round_name.upper()} Correct!"}

        return {"ok": False, "message": "Wrong Answer!"}
    except Exception:
        db.rollback()
        raise


def get_admin_round_cards(arena_urls):
    rows = get_db().execute(
        "SELECT round, status FROM round_settings ORDER BY round"
    ).fetchall()

    cards = []
    for index, row in enumerate(rows, start=1):
        cards.append(
            {
                "id": row["round"],
                "label": f"Round {index}",
                "status": row["status"],
                "arena_url": arena_urls.get(row["round"]),
            }
        )

    return cards


def update_round_status(round_name, next_status):
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute(
            "UPDATE round_settings SET status = ? WHERE round = ?",
            (next_status, round_name),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


def build_leaderboard():
    rows = get_db().execute(
        """
        SELECT
            t.team_name,
            SUM(CASE WHEN p.completed = 1 THEN 1 ELSE 0 END) AS rounds_completed,
            SUM(p.attempts) AS total_attempts,
            COALESCE(SUM(CASE WHEN p.completed = 1 THEN p.timestamp ELSE NULL END), 999999999999) AS completion_time
        FROM teams t
        JOIN progress p ON p.team_id = t.id
        GROUP BY t.id, t.team_name
        ORDER BY rounds_completed DESC, completion_time ASC, total_attempts ASC, t.team_name ASC
        """
    ).fetchall()

    board = []
    for row in rows:
        rounds_completed = int(row["rounds_completed"])
        attempts = int(row["total_attempts"])
        board.append(
            {
                "name": row["team_name"],
                "rounds": rounds_completed,
                "attempts": attempts,
                "progress_percent": int((rounds_completed / len(ROUNDS)) * 100),
                "status_text": "Awaiting finish" if rounds_completed < len(ROUNDS) else "Completion locked",
            }
        )

    return board


def count_unlocked_rounds():
    row = get_db().execute(
        "SELECT COUNT(*) AS total FROM round_settings WHERE status = 'unlocked'"
    ).fetchone()
    return int(row["total"])


def count_locked_rounds():
    row = get_db().execute(
        "SELECT COUNT(*) AS total FROM round_settings WHERE status = 'locked'"
    ).fetchone()
    return int(row["total"])
