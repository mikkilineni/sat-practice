import os
import random
import secrets
from collections import deque
from datetime import datetime
from flask import Flask, jsonify, render_template, request, session, redirect, url_for
from questions import QUESTIONS

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "sat-practice-secret-2024")

TIMERS = {"easy": 35 * 60, "moderate": 44 * 60, "hard": 44 * 60}  # seconds
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

visit_log = deque(maxlen=500)  # last 500 visits, survives restarts within a process


@app.before_request
def log_visit():
    # Skip admin routes and static files
    if request.path.startswith("/admin") or request.path.startswith("/static"):
        return
    forwarded = request.headers.get("X-Forwarded-For", "")
    real_ip = forwarded.split(",")[0].strip() if forwarded else request.remote_addr
    visit_log.appendleft({
        "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "ip": real_ip,
        "raw_ip": request.remote_addr,
        "path": request.path,
        "ua": request.headers.get("User-Agent", "")[:120],
    })


# ── Admin routes ──────────────────────────────────────────────────────

@app.get("/admin/login")
def admin_login():
    return render_template("admin_login.html", error=None)


@app.post("/admin/login")
def admin_login_post():
    pw = request.form.get("password", "")
    if secrets.compare_digest(pw, ADMIN_PASSWORD):
        session["admin"] = True
        return redirect(url_for("admin"))
    return render_template("admin_login.html", error="Wrong password.")


@app.get("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/")


@app.post("/admin/clear")
def admin_clear():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    visit_log.clear()
    return redirect(url_for("admin"))


@app.get("/admin")
def admin():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    return render_template("admin.html", visits=list(visit_log), total=len(visit_log))


# ── Public routes ─────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/test")
def test():
    difficulty = request.args.get("difficulty", "easy").lower()
    if difficulty not in QUESTIONS:
        difficulty = "easy"
    return render_template("test.html", difficulty=difficulty, timer=TIMERS[difficulty])


@app.get("/api/questions/<difficulty>")
def get_questions(difficulty):
    if difficulty not in QUESTIONS:
        return jsonify({"error": "Invalid difficulty"}), 400
    pool = QUESTIONS[difficulty]
    # Return up to 22 questions (one full SAT math module) in random order
    selected = random.sample(pool, min(22, len(pool)))
    # Strip the answer/explanation from what we send to the client
    safe = [
        {k: v for k, v in q.items() if k not in ("answer", "explanation")}
        for q in selected
    ]
    # Store the full questions server-side so we can grade them
    session["questions"] = selected
    session["difficulty"] = difficulty
    return jsonify(safe)


@app.post("/api/grade")
def grade():
    answers = request.json  # {"E01": "B", "E02": "5", ...}
    questions = session.get("questions", [])
    if not questions:
        return jsonify({"error": "No active test session"}), 400

    results = []
    score = 0
    for q in questions:
        user_ans = answers.get(q["id"], "").strip()
        correct = q["answer"].strip()

        # Normalize grid answers (allow trailing zeros etc.)
        if q["type"] == "grid":
            try:
                is_correct = float(user_ans) == float(correct)
            except ValueError:
                is_correct = False
        else:
            is_correct = user_ans.upper() == correct.upper()

        if is_correct:
            score += 1

        results.append({
            "id": q["id"],
            "domain": q["domain"],
            "prompt": q["prompt"],
            "type": q["type"],
            "choices": q.get("choices"),
            "user_answer": user_ans,
            "correct_answer": correct,
            "is_correct": is_correct,
            "explanation": q["explanation"],
        })

    total = len(questions)
    # SAT Math scaled score approximation (200–800 scale)
    raw_pct = score / total if total else 0
    scaled = round(200 + raw_pct * 600)

    return jsonify({
        "score": score,
        "total": total,
        "scaled": scaled,
        "difficulty": session.get("difficulty", ""),
        "results": results,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)
