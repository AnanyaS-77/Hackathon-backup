# Event Setup

## 1. Enter Actual Data

Edit [data.json](./data.json).

For each team:
- top-level key = team login code, for example `TEAM001`
- `team_name` = real team name
- `answers.round1` to `answers.round4` = correct answers

Before a fresh event, keep:
- all `attempts` at `0`
- all `completed` values `false`
- `timestamps` as `{}`

Edit [settings.json](./settings.json) for round locks:
- `round1` usually `unlocked`
- later rounds usually `locked`

## 2. Push JSON Into The Live App

Start the app, log in as admin, then choose one of:

### `Sync JSON Changes`

Use when you changed:
- team names
- team codes
- answers
- round locks

This does **not** wipe live progress.

### `Reset Progress From JSON`

Use before the event starts, or when you want a full fresh reset.

This updates:
- team names
- team codes
- answers
- round locks
- attempts
- completion flags
- timestamps

## 3. Reset Live Event Progress Only

Use `Reset Event Progress` in the admin panel only if you want to wipe:
- attempts
- completion flags
- timestamps

It does **not** change:
- team names
- team codes
- answers
- round lock settings

You must type `RESET` to confirm.

## 4. Production Secrets

Do not rely on fallback values in production.

Set these environment variables:
- `FLASK_SECRET_KEY`
- `ADMIN_PASSWORD_HASH` preferred, or `ADMIN_PASSWORD`
- `SESSION_COOKIE_SECURE=1`

Generate a password hash with:

```bash
python3 hash_admin_password.py "your-admin-password"
```

Then put the output into:

```bash
ADMIN_PASSWORD_HASH=...
```

## 5. What To Edit vs What Not To Edit

Edit directly:
- [data.json](./data.json)
- [settings.json](./settings.json)

Do not manually edit:
- `arena.sqlite3`

Treat SQLite as the live runtime database, and JSON as your editable source.
