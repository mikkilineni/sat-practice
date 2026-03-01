import os
import random
from flask import Flask, jsonify, render_template, request, session
from questions import QUESTIONS

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "sat-practice-secret-2024")

TIMERS = {"easy": 35 * 60, "moderate": 44 * 60, "hard": 44 * 60}  # seconds


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
