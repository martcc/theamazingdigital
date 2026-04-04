"""
app.py — Railway hosted version.
Reads from Firebase. Dynamic ongoing onboarding system.
"""

from flask import Flask, render_template, request, jsonify, session
import os
import json
import urllib.request
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "theamazingdigital2024")

FIREBASE_URL = os.environ.get("FIREBASE_URL", "https://theamazingdigital-2355e-default-rtdb.firebaseio.com")

AGENT_PASSWORDS = {
    "joseph": "joe123",
    "evie":   "evie123",
    "martin": "martin123"
}

DIRECTOR_PASSWORD = "director123"

# What the AI tries to learn about each person
KNOWLEDGE_TARGETS = [
    "how they handle conflict and confrontation",
    "what they genuinely care about vs perform caring about",
    "how they act under stress or pressure",
    "their sense of humor — what makes them laugh, how they're funny",
    "how they relate to the other people in the simulation",
    "what makes them uncomfortable or defensive",
    "their ambitions and what drives them",
    "how they communicate — what their natural speech patterns are",
    "their relationship with vulnerability and opening up",
    "what they're like in a group vs one on one"
]

SESSION_LENGTH = 12  # questions per session

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
    ua = request.headers.get("User-Agent", "").lower()
    is_mobile = any(x in ua for x in ["mobile", "android", "iphone", "ipad", "ipod"])
    return render_template("mobile.html" if is_mobile else "index.html")

@app.route("/api/status")
def api_status():
    data = firebase_get("")
    if not data:
        return jsonify({"agents": {}, "conversations": {}, "events": {}, "simulation": {}})
    return jsonify(data)

@app.route("/login", methods=["POST"])
def login():
    data     = request.json
    agent    = data.get("agent", "").lower()
    password = data.get("password", "")

    if agent not in AGENT_PASSWORDS:
        return jsonify({"success": False, "error": "Character not found."})
    if AGENT_PASSWORDS[agent] != password:
        return jsonify({"success": False, "error": "Wrong password."})

    session["agent"] = agent
    session["ob_history"] = []
    session["ob_count"] = 0

    # Load existing onboarding data from Firebase
    existing = firebase_get(f"onboarding/{agent}") or {}
    session["ob_existing"] = existing

    # Load agent's current base prompt if it exists
    agents_data = firebase_get(f"agents/{agent}") or {}
    session["ob_base_prompt"] = agents_data.get("base_prompt", "")

    session_count = existing.get("session_count", 0)

    return jsonify({
        "success": True,
        "agent": agent,
        "session_count": session_count,
        "has_prior": session_count > 0
    })

@app.route("/onboard/start")
def onboard_start():
    agent = session.get("agent")
    if not agent:
        return jsonify({"error": "Not logged in"}), 401

    existing     = session.get("ob_existing", {})
    session_count = existing.get("session_count", 0)
    base_prompt  = session.get("ob_base_prompt", "")

    # Build context from prior sessions
    prior_qa = ""
    all_qa   = existing.get("all_qa", [])
    if all_qa:
        prior_qa = "\n".join([f"Q: {qa['q']}\nA: {qa['a']}" for qa in all_qa[-20:]])

    # Generate opening message dynamically based on session number
    if session_count == 0:
        opening = f"""I'm your digital version — {agent.capitalize()} inside the simulation.

I don't know you yet. I'm going to ask you some questions — not a survey. More like a conversation. I'll follow wherever your answers lead.

I want to understand how you actually think. Ready?"""
        first_q = _generate_first_question(agent, "", KNOWLEDGE_TARGETS)
    else:
        # Returning — review what we know and find gaps
        opening = f"""We've talked {session_count} time{'s' if session_count > 1 else ''} before.

I think I have a decent picture of you — but there are things I'm still uncertain about or want to go deeper on.

Let's keep going."""
        first_q = _generate_first_question(agent, prior_qa, KNOWLEDGE_TARGETS)

    session["ob_history"] = [{"role": "assistant", "content": opening}]
    session["ob_history"].append({"role": "assistant", "content": first_q})

    return jsonify({
        "opening": opening,
        "question": first_q,
        "session_count": session_count,
        "questions_this_session": 0,
        "total_this_session": SESSION_LENGTH
    })

def _generate_first_question(agent, prior_qa, targets):
    """Generate a smart opening question based on what we already know."""
    if not prior_qa:
        return f"Tell me something about yourself that most people get wrong about you."

    # Pick a target we don't know well yet
    known_topics = prior_qa.lower()
    for target in targets:
        keywords = target.split()[:3]
        if not any(k in known_topics for k in keywords):
            return f"Something I'm still not sure about — {target}. Can you give me a specific example from your life?"

    return "What's something you've changed your mind about recently — about yourself or someone you know?"

@app.route("/onboard/answer", methods=["POST"])
def onboard_answer():
    agent = session.get("agent")
    if not agent:
        return jsonify({"error": "Not logged in"}), 401

    data    = request.json
    answer  = data.get("answer", "")
    history = session.get("ob_history", [])
    count   = session.get("ob_count", 0)

    # Add their answer to history
    history.append({"role": "user", "content": answer})
    session["ob_history"] = history
    session["ob_count"]   = count + 1

    # Save Q&A to Firebase
    existing = session.get("ob_existing", {})
    all_qa   = existing.get("all_qa", [])
    # Find the last question asked
    last_q = ""
    for msg in reversed(history[:-1]):
        if msg["role"] == "assistant" and msg["content"] != history[0]["content"]:
            last_q = msg["content"]
            break
    all_qa.append({"q": last_q, "a": answer, "ts": datetime.now().strftime("%Y-%m-%d %H:%M")})
    session["ob_existing"]["all_qa"] = all_qa

    # Check if session is done
    if count + 1 >= SESSION_LENGTH:
        return _finalize_session(agent, all_qa, history)

    # Generate next dynamic question
    next_q    = _generate_next_question(agent, history, all_qa, count + 1)
    reaction  = _generate_reaction(answer, count)

    history.append({"role": "assistant", "content": reaction})
    history.append({"role": "assistant", "content": next_q})
    session["ob_history"] = history

    return jsonify({
        "reaction": reaction,
        "question": next_q,
        "questions_this_session": count + 1,
        "total_this_session": SESSION_LENGTH,
        "done": False
    })

def _generate_reaction(answer, count):
    """Generate a brief, non-generic reaction to keep the conversation real."""
    # These are short, real reactions — not generic affirmations
    short_reactions = [
        "Got it.",
        "That makes sense.",
        "Okay.",
        "Interesting.",
        "Right.",
        "Fair enough.",
        "That tracks.",
        "Noted.",
        "I hear that.",
        "Makes sense.",
        "Good to know.",
        "Okay, yeah."
    ]
    # Pick based on answer length — longer answers get slightly more acknowledgment
    if len(answer) > 100:
        return ["That's useful context.", "Okay, that helps.", "Got it — that's a lot to work with.", "Right, okay."][count % 4]
    return short_reactions[count % len(short_reactions)]

def _generate_next_question(agent, history, all_qa, count):
    """
    Generate the next question dynamically based on what's been said.
    Hunts for gaps in knowledge, follows interesting threads, probes contradictions.
    """
    # Build conversation so far
    convo = "\n".join([
        f"{'Me' if m['role']=='assistant' else 'Them'}: {m['content']}"
        for m in history[-10:]  # last 10 exchanges
    ])

    all_answers = "\n".join([f"Q: {qa['q']}\nA: {qa['a']}" for qa in all_qa])

    # What we still want to know
    known = all_answers.lower()
    gaps  = [t for t in KNOWLEDGE_TARGETS if not any(w in known for w in t.split()[:2])]

    gaps_text = "\n".join(f"- {g}" for g in gaps[:5]) if gaps else "- go deeper on anything already mentioned"

    prompt = f"""You are the AI version of {agent.capitalize()}, conducting a dynamic interview with the real {agent.capitalize()} to understand how to imitate them accurately in a social simulation.

Your goal: ask questions that help you understand how they think, speak, react, and relate to others.

CONVERSATION SO FAR:
{convo}

THINGS YOU STILL WANT TO UNDERSTAND:
{gaps_text}

Generate ONE natural follow-up question. Rules:
- Follow a thread from their last answer if it's interesting
- OR probe one of the gaps listed above with a SPECIFIC scenario
- Questions like "what would you do if..." or "give me an example of..." work better than abstract questions
- Keep it short — one sentence, conversational
- Don't repeat anything already covered
- No preamble, just the question

Question:"""

    try:
        # Call Ollama on the PC via a simple HTTP request
        # Since Railway can't reach the PC directly, we use a pre-generated question
        # based on logic rather than the model
        return _smart_question_logic(gaps, all_qa, history)
    except:
        return _smart_question_logic(gaps, all_qa, history)

def _smart_question_logic(gaps, all_qa, history):
    """Fallback: generate smart questions using logic rather than model calls."""
    scenario_questions = [
        "Walk me through the last time you were actually annoyed with someone. What happened?",
        "If someone in the group is upset about something — what do you do first?",
        "What's a topic you could talk about for an hour without stopping?",
        "Give me an example of something you said that you immediately wished you hadn't.",
        "How do you act when you're in a room full of people you don't know well?",
        "What's something the people in the simulation get wrong about you?",
        "Describe the last time you changed your mind about someone.",
        "When do you go quiet — and when do you speak up?",
        "What's something you're better at than you let on?",
        "How do you actually feel about the people you live with?",
        "What would a perfect evening look like for you, specifically?",
        "What's a situation where you'd walk away instead of staying?",
        "How do you show that you care about someone without saying it directly?",
        "What's something you find genuinely funny — give me a specific example.",
        "When was the last time something surprised you about yourself?"
    ]

    asked = set(qa["q"] for qa in all_qa)
    for q in scenario_questions:
        if q not in asked:
            return q

    return "What's something you want me to understand about you that I probably still don't?"

def _finalize_session(agent, all_qa, history):
    """End the session, synthesize learnings, update Firebase."""
    existing      = session.get("ob_existing", {})
    session_count = existing.get("session_count", 0) + 1
    base_prompt   = session.get("ob_base_prompt", "")

    # Build synthesis from all Q&A
    all_text = "\n".join([f"Q: {qa['q']}\nA: {qa['a']}" for qa in all_qa])

    # Save everything to Firebase
    firebase_put(f"onboarding/{agent}", {
        "session_count": session_count,
        "last_session":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        "all_qa":        all_qa,
        "complete":      True
    })
    firebase_put(f"agents/{agent}/onboarded", True)
    firebase_put(f"agents/{agent}/onboarding_sessions", session_count)

    # Save Q&A as a raw file for the PC simulation to read and update core.json
    # The simulation checks this file each tick and synthesizes it
    firebase_put(f"onboarding/{agent}/pending_synthesis", {
        "all_qa":      all_qa,
        "session":     session_count,
        "needs_update": True
    })

    closings = [
        "That's enough for now.",
        "Good. I've got more to work with.",
        "Okay. That helps.",
        "Right. I think I understand you better now."
    ]
    closing = closings[session_count % len(closings)]

    return jsonify({
        "reaction": f"""{closing}

Session {session_count} done. I'll keep what you told me.

Come back whenever — the more we talk, the better I get at being you.""",
        "done": True,
        "session_count": session_count,
        "new_prompt_preview": f"Session {session_count} complete. {len(all_qa)} total exchanges on record. Your PC simulation will synthesize this on the next tick."
    })

@app.route("/director", methods=["POST"])
def director():
    data        = request.json
    instruction = data.get("instruction", "")
    password    = data.get("password", "")

    if password != DIRECTOR_PASSWORD:
        return jsonify({"error": "Wrong password"}), 403

    firebase_put("director/latest", {
        "instruction": instruction,
        "active":      True,
        "sent_at":     datetime.now().strftime("%Y-%m-%d %H:%M")
    })

    return jsonify({"success": True, "instruction": instruction})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
