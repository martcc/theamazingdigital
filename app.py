"""
app.py — Railway hosted version.
Only reads from Firebase. No ollama, no memory module needed.
Your PC runs the simulation and pushes to Firebase.
This just displays it.
"""

from flask import Flask, render_template, request, jsonify, session
import os
import json
import urllib.request
import urllib.error

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "theamazingdigital2024")

FIREBASE_URL = os.environ.get("FIREBASE_URL", "https://theamazingdigital-2355e-default-rtdb.firebaseio.com")

AGENT_PASSWORDS = {
    "joseph": "joe123",
    "evie":   "evie123",
    "martin": "martin123"
}

DIRECTOR_PASSWORD = "director123"

# ── Firebase ──────────────────────────────────────────────────────────────────

def firebase_get(path):
    url = f"{FIREBASE_URL}/{path}.json"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    except:
        return None

def firebase_put(path, data):
    url = f"{FIREBASE_URL}/{path}.json"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="PUT",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except:
        return None

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    ua = request.headers.get("User-Agent","").lower()
    is_mobile = any(x in ua for x in ["mobile","android","iphone","ipad","ipod"])
    if is_mobile:
        return render_template("mobile.html")
    return render_template("index.html")

@app.route("/api/status")
def api_status():
    data = firebase_get("")
    if not data:
        return jsonify({"agents": {}, "conversations": {}, "events": {}, "simulation": {}})
    return jsonify(data)

@app.route("/login", methods=["POST"])
def login():
    data      = request.json
    agent     = data.get("agent", "").lower()
    password  = data.get("password", "")

    if agent not in AGENT_PASSWORDS:
        return jsonify({"success": False, "error": "Character not found."})
    if AGENT_PASSWORDS[agent] != password:
        return jsonify({"success": False, "error": "Wrong password."})

    session["agent"] = agent

    # Check if onboarded via Firebase
    onboarded = firebase_get(f"agents/{agent}/onboarded") or False

    return jsonify({"success": True, "agent": agent, "onboarded": onboarded})

@app.route("/onboard/start")
def onboard_start():
    agent = session.get("agent")
    if not agent:
        return jsonify({"error": "Not logged in"}), 401

    session["onboarding_history"] = []
    session["question_index"] = 0

    questions = [
        "How would your closest friends describe you in 3 words?",
        "What are you most proud of that most people don't know about?",
        "What genuinely irritates you that most people find normal?",
        "How do you act when you're stressed — go quiet, get snappy, make jokes?",
        "What kind of people do you naturally click with?",
        "What do you secretly care about more than you let on?",
        "How do you feel about conflict — avoid it, lean into it, or something else?",
        "What does a perfect day look like for you?",
        "What's a fear or insecurity you'd admit to?",
        "Is there anything about yourself you're still figuring out?"
    ]
    session["questions"] = questions

    opening = f"""Hey. I'm your digital version — {agent.capitalize()} inside the simulation.

I need to ask you some questions so I actually know how to be you. Not a fake version. The real one.

This isn't a test. Just be honest. Ready?"""

    return jsonify({
        "message": opening,
        "question": questions[0],
        "question_index": 0,
        "total_questions": len(questions)
    })

@app.route("/onboard/answer", methods=["POST"])
def onboard_answer():
    agent   = session.get("agent")
    if not agent:
        return jsonify({"error": "Not logged in"}), 401

    data     = request.json
    answer   = data.get("answer", "")
    q_index  = session.get("question_index", 0)
    questions = session.get("questions", [])
    history  = session.get("onboarding_history", [])

    history.append({"question": questions[q_index], "answer": answer})
    session["onboarding_history"] = history

    # Save answer to Firebase
    firebase_put(f"onboarding/{agent}/{q_index}", {
        "question": questions[q_index],
        "answer": answer
    })

    # Simple reactions based on index
    reactions = [
        "Interesting. I'll remember that.",
        "That tells me a lot, actually.",
        "Good to know. Most people wouldn't admit that.",
        "That tracks.",
        "Got it.",
        "I'll keep that in mind.",
        "That's useful.",
        "Okay. That makes sense.",
        "Noted.",
        "That's everything I needed."
    ]
    reaction = reactions[q_index] if q_index < len(reactions) else "Got it."

    next_index = q_index + 1
    session["question_index"] = next_index

    if next_index >= len(questions):
        # Save completion to Firebase
        firebase_put(f"agents/{agent}/onboarded", True)
        firebase_put(f"onboarding/{agent}/complete", True)

        closing = f"""{reaction}

That's everything I needed. I think I've got a pretty good picture of you now.

You can come back and update me anytime. People change."""

        return jsonify({
            "reaction": closing,
            "done": True,
            "new_prompt_preview": f"Onboarding complete for {agent.capitalize()}. Your PC will process this on the next simulation tick."
        })

    return jsonify({
        "reaction": reaction,
        "question": questions[next_index],
        "question_index": next_index,
        "total_questions": len(questions),
        "done": False
    })

@app.route("/director", methods=["POST"])
def director():
    data        = request.json
    instruction = data.get("instruction", "")
    password    = data.get("password", "")

    if password != DIRECTOR_PASSWORD:
        return jsonify({"error": "Wrong password"}), 403

    from datetime import datetime
    firebase_put("director/latest", {
        "instruction": instruction,
        "active": True,
        "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    })

    return jsonify({"success": True, "instruction": instruction})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
