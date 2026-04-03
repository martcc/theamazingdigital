"""
app.py — Flask website that reads from Firebase.
This can be hosted anywhere — Railway, Render, etc.
It doesn't need Ollama or your PC to be reachable.
"""

from flask import Flask, render_template, request, jsonify, session
import urllib.request
import urllib.error
import json
import os
import urllib.request

try:
    import ollama
    OLLAMA_AVAILABLE = True
except:
    OLLAMA_AVAILABLE = False

try:
    import memory
    MEMORY_AVAILABLE = True
except:
    MEMORY_AVAILABLE = False

app = Flask(__name__)
app.secret_key = "simulation_secret_key_change_this"

# ── CONFIG ────────────────────────────────────────────────────────────────────
FIREBASE_URL = "https://theamazingdigital-2355e-default-rtdb.firebaseio.com"
MODEL = "hf.co/DavidAU/Qwen3-The-Xiaolong-Josiefied-Omega-Directive-22B-uncensored-abliterated-GGUF:Q4_K_M"

AGENT_PASSWORDS = {
    "joseph": "joe123",
    "evie":   "evie123",
    "martin": "martin123"
}

ONBOARDING_QUESTIONS = [
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

# ── Firebase Helper ───────────────────────────────────────────────────────────

def firebase_get(path):
    if FIREBASE_URL == "YOUR_FIREBASE_URL_HERE":
        return None
    url = f"{FIREBASE_URL}/{path}.json"
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read())
    except:
        return None

def firebase_put(path, data):
    if FIREBASE_URL == "YOUR_FIREBASE_URL_HERE":
        return None
    url = f"{FIREBASE_URL}/{path}.json"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="PUT",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except:
        return None

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    agent_name = data.get("agent", "").lower()
    password   = data.get("password", "")

    if agent_name not in AGENT_PASSWORDS:
        return jsonify({"success": False, "error": "Character not found."})
    if AGENT_PASSWORDS[agent_name] != password:
        return jsonify({"success": False, "error": "Wrong password."})

    session["agent"] = agent_name
    session["onboarding_history"] = []
    session["question_index"] = 0

    core = memory.get_core(agent_name)
    return jsonify({
        "success": True,
        "agent": agent_name,
        "onboarded": core.get("onboarded", False)
    })

@app.route("/onboard/start")
def onboard_start():
    agent_name = session.get("agent")
    if not agent_name:
        return jsonify({"error": "Not logged in"}), 401

    opening = f"""Hey. I'm your digital version — {agent_name.capitalize()} inside the simulation.

I need to ask you some questions so I actually know how to be you. Not a fake version. The real one.

This isn't a test. Just be honest. Ready?"""

    return jsonify({
        "message": opening,
        "question": ONBOARDING_QUESTIONS[0],
        "question_index": 0,
        "total_questions": len(ONBOARDING_QUESTIONS)
    })

@app.route("/onboard/answer", methods=["POST"])
def onboard_answer():
    agent_name = session.get("agent")
    if not agent_name:
        return jsonify({"error": "Not logged in"}), 401

    data    = request.json
    answer  = data.get("answer", "")
    q_index = session.get("question_index", 0)

    history = session.get("onboarding_history", [])
    history.append({"question": ONBOARDING_QUESTIONS[q_index], "answer": answer})
    session["onboarding_history"] = history

    core = memory.get_core(agent_name)
    core["onboarding_answers"][ONBOARDING_QUESTIONS[q_index]] = answer
    memory.save_core(agent_name, core)

    history_text = "\n".join([f"Q: {h['question']}\nA: {h['answer']}" for h in history])

    reaction_prompt = f"""You are the AI version of {agent_name.capitalize()} inside a simulation interviewing your real human counterpart.

Interview so far:
{history_text}

React briefly to their last answer (1-2 sentences). Be real, not robotic.
No think tags. Just your reaction."""

    try:
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": reaction_prompt}]
        )
        reaction = response["message"]["content"].strip()
        if "<think>" in reaction:
            reaction = reaction.split("</think>")[-1].strip()
    except:
        reaction = "Got it."

    next_index = q_index + 1
    session["question_index"] = next_index

    if next_index >= len(ONBOARDING_QUESTIONS):
        return finalize_onboarding(agent_name, history, reaction)

    return jsonify({
        "reaction": reaction,
        "question": ONBOARDING_QUESTIONS[next_index],
        "question_index": next_index,
        "total_questions": len(ONBOARDING_QUESTIONS),
        "done": False
    })

def finalize_onboarding(agent_name, history, last_reaction):
    history_text = "\n".join([f"Q: {h['question']}\nA: {h['answer']}" for h in history])

    synthesis_prompt = f"""Based on this interview with a real person, write a personality description for their AI simulation character named {agent_name.capitalize()}.

Interview:
{history_text}

Write 150-200 words in second person ("You are {agent_name.capitalize()}...").
Be specific. Capture how they talk, what they care about, their quirks.
No think tags. Just the personality description."""

    try:
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": synthesis_prompt}]
        )
        new_prompt = response["message"]["content"].strip()
        if "<think>" in new_prompt:
            new_prompt = new_prompt.split("</think>")[-1].strip()
    except:
        new_prompt = f"You are {agent_name.capitalize()}."

    core = memory.get_core(agent_name)
    core["core_traits"]["base_prompt"] = new_prompt
    core["onboarded"] = True
    memory.save_core(agent_name, core)

    closing = f"""{last_reaction}

That's everything I needed. I think I've got a pretty good picture of you now.

You can come back and update me anytime. People change."""

    return jsonify({
        "reaction": closing,
        "done": True,
        "new_prompt_preview": new_prompt[:200] + "..."
    })

@app.route("/api/status")
def api_status():
    """Read live simulation state from Firebase."""
    data = firebase_get("")
    if not data:
        # Fall back to local files if Firebase not configured
        agents = memory.list_agents()
        result = {"agents": {}, "conversations": [], "meta": {}}
        for agent in agents:
            try:
                core = memory.get_core(agent)
                st   = memory.get_short_term(agent)
                lt   = memory.get_long_term(agent)
                result["agents"][agent] = {
                    "mood": st.get("current_mood", "unknown"),
                    "location": st.get("current_location", "home"),
                    "conversations_today": len(st.get("conversations", [])),
                    "relationships": lt.get("relationships", {})
                }
            except:
                pass
        return jsonify(result)

    return jsonify(data)

@app.route("/director", methods=["POST"])
def director():
    data        = request.json
    instruction = data.get("instruction", "")
    password    = data.get("password", "")

    if password != "director123":
        return jsonify({"error": "Wrong password"}), 403

    directive_path = os.path.join(os.path.dirname(__file__), "..", "director_instruction.json")
    with open(directive_path, "w") as f:
        json.dump({"active": True, "instruction": instruction}, f)

    firebase_put("director/latest", {
        "instruction": instruction,
        "sent_at": "now"
    })

    return jsonify({"success": True, "instruction": instruction})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
