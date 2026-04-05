from flask import Flask, render_template, request, redirect, session
import json
import time

app = Flask(__name__)
app.secret_key = "hackathon_secret"

DATA_FILE = "data.json"
ROUNDS = ["round1", "round2", "round3", "round4"]

def load_data():
    with open(DATA_FILE) as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


def build_round_cards(team):
    cards = []

    for index, round_name in enumerate(ROUNDS, start=1):
        completed = team["completed"][round_name]
        attempts_used = team["attempts"][round_name]
        attempts_left = max(0, 2 - attempts_used)
        unlocked = index == 1 or team["completed"][ROUNDS[index - 2]]

        if completed:
            status = "completed"
        elif unlocked:
            status = "unlocked"
        else:
            status = "locked"

        cards.append({
            "id": round_name,
            "label": f"Round {index}",
            "status": status,
            "completed": completed,
            "unlocked": unlocked,
            "attempts_used": attempts_used,
            "attempts_left": attempts_left,
        })

    return cards

# LOGIN
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        team_code = request.form.get("team_code").strip().upper()
        data = load_data()

        if team_code in data:
            session["team"] = team_code
            return redirect("/dashboard")
        else:
            return render_template("login.html", error="Invalid Team Code !!")

    return render_template("login.html")


# DASHBOARD
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "team" not in session:
        return redirect("/")

    data = load_data()
    team_code = session["team"]
    team = data[team_code]
    round_cards = build_round_cards(team)

    message = ""

    if request.method == "POST":
        round_name = request.form.get("round")
        answer = request.form.get("answer", "").strip().upper()
        allowed_rounds = {card["id"] for card in round_cards if card["unlocked"]}

        if round_name not in ROUNDS:
            message = "Invalid round selected!"
        elif round_name not in allowed_rounds:
            message = " This round is still locked!"
        elif team["completed"][round_name]:
            message = "Already completed!"
        elif team["attempts"][round_name] >= 2:
            message = " No attempts left!"
        elif not answer:
            message = " Enter a codeword first!"
        else:
            team["attempts"][round_name] += 1

            if answer == team["answers"][round_name]:
                team["completed"][round_name] = True
                team["timestamps"][round_name] = time.time()
                message = f" {round_name.upper()} Correct!"
            else:
                message = " Wrong Answer!"

        save_data(data)
        round_cards = build_round_cards(team)

    return render_template(
        "dashboard.html",
        team=team,
        message=message,
        round_cards=round_cards,
    )


# LEADERBOARD
@app.route("/leaderboard")
def leaderboard():
    data = load_data()
    board = []

    for code, team in data.items():
        rounds_completed = sum(team["completed"].values())
        total_time = sum(team["timestamps"].values()) if team["timestamps"] else float('inf')
        total_attempts = sum(team["attempts"].values())

        board.append({
            "name": team["team_name"],
            "rounds": rounds_completed,
            "time": total_time,
            "attempts": total_attempts
        })

    board.sort(key=lambda x: (-x["rounds"], x["time"], x["attempts"]))

    return render_template("leaderboard.html", leaderboard=board)


# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=True)
