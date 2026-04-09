import os
import re
import secrets
import time
from functools import wraps

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, session
from werkzeug.security import check_password_hash

from db import (
    ROUNDS,
    build_leaderboard,
    count_locked_rounds,
    count_unlocked_rounds,
    get_admin_round_cards,
    get_team,
    get_round_cards_for_team,
    reset_event,
    submit_round_answer,
    sync_seed_data,
    update_round_status,
)

bp = Blueprint("arena", __name__)

ROUND_ARENA_URLS = {
    "round1": "",
    "round2": "https://digit-manipulation.replit.app/",
    "round3": "https://code-arena.replit.app/",
    "round4": "",
}
TEAM_CODE_RE = re.compile(r"^[A-Z0-9]{3,32}$")
MAX_ANSWER_LENGTH = 64
SUBMISSION_COOLDOWN_SECONDS = 2
SUBMISSION_WINDOW_SECONDS = 30
MAX_SUBMISSIONS_PER_WINDOW = 8
SENSITIVE_PATHS = {
    "/data.json",
    "/settings.json",
    "/arena.sqlite3",
    "/seed_db.py",
    "/db.py",
    "/routes.py",
    "/app.py",
}


def get_admin_password():
    return os.environ.get("ADMIN_PASSWORD", "SystemAdmin123")


def verify_admin_password(raw_password):
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH")
    if password_hash:
        return check_password_hash(password_hash, raw_password)

    if os.environ.get("FLASK_ENV") == "production" and "ADMIN_PASSWORD" not in os.environ:
        raise RuntimeError("ADMIN_PASSWORD or ADMIN_PASSWORD_HASH must be set in production.")

    return raw_password == get_admin_password()


def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
        session.modified = True
    return token


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("team_id"):
            return redirect("/")
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect("/admin/login")
        return view(*args, **kwargs)

    return wrapped


def auth_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("team_id") or session.get("is_admin"):
            return view(*args, **kwargs)
        return redirect("/")

    return wrapped


def normalize_team_code(raw_value):
    team_code = (raw_value or "").strip().upper()
    if TEAM_CODE_RE.fullmatch(team_code):
        return team_code
    return ""


def normalize_answer(raw_value):
    answer = (raw_value or "").strip().upper()
    if not answer or len(answer) > MAX_ANSWER_LENGTH:
        return ""
    return answer


def rate_limit_submission():
    now = time.time()
    recent_attempts = [
        stamp for stamp in session.get("submission_attempts", [])
        if now - stamp < SUBMISSION_WINDOW_SECONDS
    ]

    if recent_attempts and now - recent_attempts[-1] < SUBMISSION_COOLDOWN_SECONDS:
        session["submission_attempts"] = recent_attempts
        session.modified = True
        return "Please wait a moment before trying again."

    if len(recent_attempts) >= MAX_SUBMISSIONS_PER_WINDOW:
        session["submission_attempts"] = recent_attempts
        session.modified = True
        return "Too many submissions. Please wait before trying again."

    recent_attempts.append(now)
    session["submission_attempts"] = recent_attempts
    session.modified = True
    return ""


@bp.before_app_request
def refresh_active_session():
    if request.path in SENSITIVE_PATHS:
        abort(404)

    # Refresh only authenticated sessions so idle sessions expire automatically.
    if session.get("team_id") or session.get("is_admin"):
        session.permanent = True
        session.modified = True

    if request.method == "POST":
        form_token = request.form.get("csrf_token", "")
        if not form_token or form_token != get_csrf_token():
            abort(400)


@bp.app_context_processor
def inject_template_helpers():
    return {"csrf_token": get_csrf_token()}


@bp.app_errorhandler(400)
def bad_request(_error):
    return render_template("login.html", error="Invalid request."), 400


@bp.app_errorhandler(429)
def too_many_requests(_error):
    return render_template("login.html", error="Too many requests. Please wait and try again."), 429


@bp.app_errorhandler(500)
def internal_error(_error):
    current_app.logger.exception("Unhandled application error")
    if request.path.startswith("/api/"):
        return jsonify({"error": "Something went wrong. Please try again."}), 500
    return render_template("login.html", error="Something went wrong. Please try again."), 500


@bp.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        team_code = normalize_team_code(request.form.get("team_code"))
        if not team_code:
            return render_template("login.html", error="Invalid Team Code !!")

        team = get_team(team_code=team_code)
        if team is None:
            return render_template("login.html", error="Invalid Team Code !!")

        session.clear()
        session.permanent = True
        session["csrf_token"] = secrets.token_urlsafe(32)
        session["team_id"] = int(team["team_id"])
        return redirect("/dashboard")

    return render_template("login.html")


@bp.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    team = get_team(team_id=session["team_id"])
    if team is None:
        session.clear()
        return redirect("/")

    message = ""

    if request.method == "POST":
        round_name = request.form.get("round", "").strip().lower()
        answer = normalize_answer(request.form.get("answer"))

        if round_name not in ROUNDS:
            message = "Invalid round selected!"
        elif not answer:
            message = "Enter a codeword first!"
        else:
            throttle_message = rate_limit_submission()
            if throttle_message:
                message = throttle_message
            else:
                result = submit_round_answer(team["team_id"], round_name, answer)
                message = result["message"]

    round_cards = get_round_cards_for_team(team["team_id"], ROUND_ARENA_URLS)
    total_attempts = sum(card["attempts_used"] for card in round_cards)

    return render_template(
        "dashboard.html",
        team_name=team["team_name"],
        total_attempts=total_attempts,
        message=message,
        round_cards=round_cards,
    )


@bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = ""

    if session.get("is_admin"):
        return redirect("/admin")

    if request.method == "POST":
        password = (request.form.get("password") or "").strip()
        if verify_admin_password(password):
            session.clear()
            session.permanent = True
            session["csrf_token"] = secrets.token_urlsafe(32)
            session["is_admin"] = True
            return redirect("/admin")
        error = "Invalid admin password!"

    return render_template("admin_login.html", error=error)


@bp.route("/admin", methods=["GET", "POST"])
@admin_required
def admin_dashboard():
    message = ""

    if request.method == "POST":
        action = request.form.get("action", "").strip().lower()
        round_name = request.form.get("round", "").strip().lower()
        next_status = request.form.get("status", "").strip().lower()

        if action == "sync_seed":
            sync_seed_data(reset_progress=False)
            message = "Synced team names, login codes, answers, and round locks from JSON."
        elif action == "reset_from_seed":
            sync_seed_data(reset_progress=True)
            message = "Rebuilt team progress from data.json and lock settings from settings.json."
        elif action == "reset_event":
            confirmation = request.form.get("confirmation", "").strip().upper()
            if confirmation != "RESET":
                message = "Type RESET to confirm the event reset."
            else:
                result = reset_event()
                message = f"Event progress reset for {result['reset_progress_rows']} round records."
        elif round_name not in ROUNDS or next_status not in {"locked", "unlocked"}:
            message = "Invalid admin action!"
        else:
            update_round_status(round_name, next_status)
            message = f"{round_name.upper()} is now {next_status}."

    round_cards = get_admin_round_cards(ROUND_ARENA_URLS)

    return render_template(
        "admin.html",
        round_cards=round_cards,
        message=message,
        unlocked_count=count_unlocked_rounds(),
        locked_count=count_locked_rounds(),
        admin_password_hint=(
            "ADMIN_PASSWORD" not in os.environ and "ADMIN_PASSWORD_HASH" not in os.environ
        ),
    )


@bp.route("/leaderboard")
@auth_required
def leaderboard():
    return render_template("leaderboard.html", leaderboard=build_leaderboard())


@bp.route("/api/leaderboard")
@auth_required
def leaderboard_api():
    return jsonify({"leaderboard": build_leaderboard()})


@bp.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@bp.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin/login")
