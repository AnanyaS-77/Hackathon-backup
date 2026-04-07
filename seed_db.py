"""
Seed the SQLite database with initial team and answer data.

This script is intentionally separate from the Flask routes so setup can be
run explicitly during development or deployment.

Example usage:
    python3 seed_db.py
    python3 seed_db.py --reset-event --confirm

    from seed_db import seed_data

    seed_data(
        [
            {
                "team_code": "TEAM001",
                "team_name": "Debuggers",
                "answers": {
                    "round1": "ALPHA1",
                    "round2": "BINARY1",
                    "round3": "LOOP1",
                    "round4": "VECTOR1",
                },
            }
        ]
    )

    from seed_db import reset_event

    reset_event()
"""

import argparse
import json
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import create_app
from db import ROUNDS, get_db, init_db, reset_event as reset_event_db


def load_seed_payload(path="data.json"):
    seed_path = Path(path)
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_path}")

    raw_data = json.loads(seed_path.read_text())
    payload = []

    for team_code, team_data in raw_data.items():
        payload.append(
            {
                "team_code": str(team_code).strip().upper(),
                "team_name": str(team_data.get("team_name", "")).strip() or str(team_code).strip().upper(),
                "answers": {
                    round_name: str(team_data.get("answers", {}).get(round_name, "")).strip().upper()
                    for round_name in ROUNDS
                },
            }
        )

    return payload


def seed_data(team_payload):
    """
    Insert initial teams and round answers without overwriting existing teams.

    Returns a summary dictionary with inserted and skipped team codes.
    """
    app = create_app()

    with app.app_context():
        init_db()
        db = get_db()
        inserted = []
        skipped = []

        db.execute("BEGIN IMMEDIATE")
        try:
            for team in team_payload:
                team_code = str(team.get("team_code", "")).strip().upper()
                team_name = str(team.get("team_name", "")).strip()
                answers = team.get("answers", {})

                if not team_code or not team_name:
                    raise ValueError("Each team requires a non-empty team_code and team_name.")

                existing_team = db.execute(
                    "SELECT id FROM teams WHERE team_code = ?",
                    (team_code,),
                ).fetchone()

                if existing_team is not None:
                    skipped.append(team_code)
                    continue

                cursor = db.execute(
                    "INSERT INTO teams (team_code, team_name) VALUES (?, ?)",
                    (team_code, team_name),
                )
                team_id = cursor.lastrowid

                for round_name in ROUNDS:
                    raw_answer = str(answers.get(round_name, "")).strip().upper()
                    if not raw_answer:
                        raise ValueError(f"Missing answer for {team_code} {round_name}.")

                    db.execute(
                        "INSERT INTO answers (team_id, round, correct_answer) VALUES (?, ?, ?)",
                        (team_id, round_name, generate_password_hash(raw_answer)),
                    )
                    db.execute(
                        """
                        INSERT INTO progress (team_id, round, attempts, completed, timestamp)
                        VALUES (?, ?, 0, 0, NULL)
                        """,
                        (team_id, round_name),
                    )

                inserted.append(team_code)

            db.commit()
        except Exception:
            db.rollback()
            raise

        return {
            "inserted_count": len(inserted),
            "skipped_count": len(skipped),
            "inserted_team_codes": inserted,
            "skipped_team_codes": skipped,
        }


def seed_from_json(path="data.json"):
    return seed_data(load_seed_payload(path))


def reset_event():
    app = create_app()

    with app.app_context():
        init_db()
        return reset_event_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed or reset the event database.")
    parser.add_argument(
        "--reset-event",
        action="store_true",
        help="Reset all attempts/completion/timestamps while preserving teams and answers.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required with --reset-event to avoid accidental resets.",
    )
    parser.add_argument(
        "--seed-file",
        default="data.json",
        help="Seed file to use when inserting initial team data.",
    )
    args = parser.parse_args()

    if args.reset_event:
        if not args.confirm:
            parser.error("--reset-event requires --confirm")
        result = reset_event()
    else:
        result = seed_from_json(args.seed_file)

    print(json.dumps(result, indent=2))
