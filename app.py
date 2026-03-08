from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import requests
import re
from google import genai
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
load_dotenv()
print("SECRET:", os.environ.get("SECRET_KEY"))
import sqlite3



app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")

# 🔒 Security settings for session cookies
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = False   # True karo jab HTTPS ho

#Database connection
def init_db():
    conn = sqlite3.connect("health.db")
    cursor = conn.cursor()

    # ── Users table ───────────────────────────────────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        email    TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ── Chat history table ────────────────────────────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        user     TEXT,
        role     TEXT,
        message  TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ── Legacy health_metrics table (kept for backward-compat) ────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS health_metrics (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email     TEXT,
        steps          INTEGER,
        heart_rate     INTEGER,
        sleep_hours    REAL,
        weight         REAL,
        blood_pressure TEXT,
        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ── health_entries — new table linked by user_id (integer FK) ────────────
    # This is the primary store for all health data going forward.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS health_entries (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id        INTEGER NOT NULL,
        heart_rate     INTEGER,
        blood_pressure TEXT,
        weight         REAL,
        steps          INTEGER,
        sleep_hours    REAL,
        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # ── Safe migrations for legacy table ─────────────────────────────────────
    for col_sql in [
        "ALTER TABLE health_metrics ADD COLUMN sleep_hours REAL",
        "ALTER TABLE health_metrics ADD COLUMN weight REAL",
        "ALTER TABLE health_metrics ADD COLUMN blood_pressure TEXT",
        "ALTER TABLE health_metrics ADD COLUMN heart_rate INTEGER",
        "ALTER TABLE health_metrics ADD COLUMN steps INTEGER",
    ]:
        try:
            cursor.execute(col_sql)
        except sqlite3.OperationalError:
            pass  # Column already exists — skip silently

    conn.commit()
    conn.close()

init_db()
# ── Helper: resolve user_id from session email ────────────────────────────────
def get_user_id(cursor, email):
    """Return the integer user.id for the given email, or None."""
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    return row[0] if row else None


# ── Helper: open a connection with row_factory for dict-like access ────────────
def get_db():
    conn = sqlite3.connect("health.db")
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    return conn

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/about")
def about():
    return "<h1>About Page 😎</h1>"


@app.route("/login", methods=["GET", "POST"])
def login():

    # Agar user login form submit karta hai
    if request.method == "POST":

        # Form se data le rahe hain
        email = request.form.get("email")
        password = request.form.get("password")

        # Database connect
        conn = sqlite3.connect("health.db")
        cursor = conn.cursor()

        # Email ke basis pe user fetch kar rahe hain
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

        # Connection close kar diya
        conn.close()

        # Agar user exist karta hai AND password match karta hai
        # check_password_hash compare karta hai plain password ko hashed password se
        if user and check_password_hash(user[2], password):

            # 🔥 YAHI SESSION SET HOTI HAI
            # Ab server ko yaad rahega kaunsa user login hai
            session.clear()   # 🔥 IMPORTANT FIX
            session["user_email"] = user[1]
            # print("USER:", user)
            # print("PASSWORD MATCH:", check_password_hash(user[2], password) if user else "NO USER")
            # Login successful → dashboard pe bhej do
            return redirect(url_for("dashboard"))

        else:
            # Agar credentials galat hain
            return render_template("login.html", error="Invalid credentials")

    # Agar GET request hai
    return render_template("login.html")



@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "user_email" not in session:
        return redirect(url_for("login"))

    user_email = session["user_email"]
    conn = get_db()
    cursor = conn.cursor()

    # Resolve the integer user_id once
    user_id = get_user_id(cursor, user_email)

    # ── Handle form submission (POST) ────────────────────────────────────────
    if request.method == "POST":
        steps          = request.form.get("steps",          type=int)
        heart_rate     = request.form.get("heart_rate",     type=int)
        sleep_hours    = request.form.get("sleep_hours",    type=float)
        weight         = request.form.get("weight",         type=float)
        blood_pressure = request.form.get("blood_pressure", default="")

        # ── Save into new health_entries table (user_id FK) ──────────────────
        cursor.execute("""
            INSERT INTO health_entries
                (user_id, heart_rate, blood_pressure, weight, steps, sleep_hours)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, heart_rate, blood_pressure, weight, steps, sleep_hours))

        conn.commit()
        conn.close()
        flash("Health entry added successfully! ✅", "success")
        return redirect(url_for("dashboard"))

    # ── Fetch last 20 entries for charts (GET) ───────────────────────────────
    # We query health_entries (new table) first; fall back to legacy
    # health_metrics if user has no entries yet in the new table.
    cursor.execute("""
        SELECT steps, heart_rate, sleep_hours, weight, blood_pressure, created_at
        FROM   health_entries
        WHERE  user_id = ?
        ORDER  BY created_at ASC
        LIMIT  20
    """, (user_id,))
    rows = cursor.fetchall()

    # Legacy fallback — users who logged data before the migration
    if not rows:
        cursor.execute("""
            SELECT steps, heart_rate, sleep_hours, weight, blood_pressure, created_at
            FROM   health_metrics
            WHERE  user_email = ?
            ORDER  BY created_at ASC
            LIMIT  20
        """, (user_email,))
        rows = cursor.fetchall()

    conn.close()

    # ── Build chart arrays ───────────────────────────────────────────────────
    def _fmt_ts(raw):
        """Format a raw SQLite timestamp string for chart labels."""
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").strftime("%b %d %H:%M")
        except Exception:
            return str(raw)[-8:-3]

    if rows:
        steps_data      = [r["steps"]       for r in rows]
        heart_rate_data = [r["heart_rate"]   for r in rows]
        sleep_data      = [r["sleep_hours"]  for r in rows]
        weight_data     = [r["weight"]       for r in rows]
        timestamps      = [_fmt_ts(r["created_at"]) for r in rows]

        latest = rows[-1]
        data = {
            "steps":          latest["steps"]       or "--",
            "heart_rate":     latest["heart_rate"]  or "--",
            "sleep_hours":    latest["sleep_hours"] or "--",
            "weight":         latest["weight"]      or "--",
            "blood_pressure": latest["blood_pressure"] or "--/--",
        }
        # Recent entries for the activity feed (newest first, up to 5)
        activities = [
            {
                "activity": f"❤️ {r['heart_rate']} bpm  🚶 {r['steps']} steps  😴 {r['sleep_hours']} h",
                "duration": _fmt_ts(r["created_at"])
            }
            for r in rows[-5:][::-1]
        ]
    else:
        steps_data = heart_rate_data = sleep_data = weight_data = []
        timestamps = []
        data = {
            "steps": "--", "heart_rate": "--",
            "sleep_hours": "--", "weight": "--", "blood_pressure": "--/--"
        }
        activities = []

    return render_template(
        "dashboard.html",
        data=data,
        steps_data=steps_data,
        heart_rate_data=heart_rate_data,
        sleep_data=sleep_data,
        weight_data=weight_data,
        timestamps=timestamps,
        activities=activities,
    )


# ── JSON endpoint: live chart refresh without page reload ────────────────────
@app.route("/api/health-data")
def api_health_data():
    if "user_email" not in session:
        return jsonify({"error": "unauthorized"}), 401

    user_email = session["user_email"]
    conn = get_db()
    cursor = conn.cursor()

    user_id = get_user_id(cursor, user_email)

    # Prefer the new health_entries table
    cursor.execute("""
        SELECT steps, heart_rate, sleep_hours, weight, created_at
        FROM   health_entries
        WHERE  user_id = ?
        ORDER  BY created_at ASC
        LIMIT  20
    """, (user_id,))
    rows = cursor.fetchall()

    # Fallback to legacy table
    if not rows:
        cursor.execute("""
            SELECT steps, heart_rate, sleep_hours, weight, created_at
            FROM   health_metrics
            WHERE  user_email = ?
            ORDER  BY created_at ASC
            LIMIT  20
        """, (user_email,))
        rows = cursor.fetchall()

    conn.close()

    def _fmt(raw):
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").strftime("%b %d %H:%M")
        except Exception:
            return str(raw)[-8:-3]

    return jsonify({
        "labels":     [_fmt(r["created_at"]) for r in rows],
        "steps":      [r["steps"]      for r in rows],
        "heart_rate": [r["heart_rate"] for r in rows],
        "sleep":      [r["sleep_hours"] for r in rows],
        "weight":     [r["weight"]     for r in rows],
    })


# ===== AI FUNCTION =====
def ask_ai(message):
    """
    Calls the Gemini model and returns the raw response text.
    The prompt instructs the model to ALWAYS start its reply with
    one of:  [RISK: LOW]  [RISK: MODERATE]  [RISK: HIGH]
    so that we can parse it out on the Python side.
    """
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    prompt = (
        "You are a medical assistant. "
        "Reply in maximum 5 lines. "
        "Start your reply with one tag: "
        "[RISK: LOW], [RISK: MODERATE], or [RISK: HIGH]. "
        "Then give brief advice.\n"
        f"User: {message}"
    )


    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt
        )

        return response.text

    except Exception as e:
        print("Gemini error:", e)
        return "[RISK: LOW]\nAI service temporarily unavailable."

# ── Helper: extract risk level from AI reply ──────────────────────────────────
_RISK_RE = re.compile(r"\[RISK:\s*(LOW|MODERATE|HIGH)\]", re.IGNORECASE)

def parse_risk(raw_text):
    """
    Returns (risk_level, clean_text).
    risk_level is 'LOW', 'MODERATE', 'HIGH', or None.
    clean_text has the tag stripped out.
    """
    match = _RISK_RE.search(raw_text)
    if match:
        level = match.group(1).upper()
        # Remove the tag (and any leading whitespace/newline after it)
        clean = _RISK_RE.sub("", raw_text, count=1).lstrip("\n ").strip()
        return level, clean
    return None, raw_text.strip()


# ===== ROUTE =====
# Ye route define karta hai ki jab /predict URL hit hoga toh ye function chalega
# methods=["GET", "POST"] ka matlab:
# GET  -> page open karne ke liye
# POST -> form submit hone ke liye

@app.route("/predict", methods=["GET", "POST"])
def predict():

    if "user_email" not in session:
        return redirect(url_for("login"))

    email = session.get("user_email")

    # Handle new message
    if request.method == "POST":
        message = request.form.get("message")

        if message and message.strip():

            # Call AI
            raw_reply = ask_ai(message)
            risk_level, clean_reply = parse_risk(raw_reply)

            try:
                conn = get_db()
                cursor = conn.cursor()

                # Save user message
                cursor.execute(
                    "INSERT INTO chat_history (user, role, message) VALUES (?, ?, ?)",
                    (email, "user", message)
                )

                # Save AI reply
                cursor.execute(
                    "INSERT INTO chat_history (user, role, message) VALUES (?, ?, ?)",
                    (email, "ai", raw_reply)
                )

                conn.commit()
                conn.close()

            except Exception:
                pass

    # Load chat history for this user
    chat = []
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT role, message FROM chat_history WHERE user = ? ORDER BY created_at",
            (email,)
        )

        rows = cursor.fetchall()

        for role, message in rows:

            risk_level, clean_message = parse_risk(message)

            chat.append({
                "role": role,
                "text": clean_message,
                "risk": risk_level
            })

        conn.close()

    except Exception:
        pass

    return render_template("predict.html", chat=chat)



# ── Chat History page ─────────────────────────────────────────────────────────
@app.route("/history")
def history():

    if "user_email" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, role, message, created_at
        FROM   chat_history
        WHERE  user = ?
        ORDER  BY created_at ASC
    """, (session["user_email"],))

    rows = cursor.fetchall()
    conn.close()

    history_data = []
    for r in rows:
        text = r["message"]
        risk = None
        if r["role"] == "ai":
            risk, text = parse_risk(text)
            
        history_data.append({
            "id": r["id"],
            "role": r["role"],
            "text": text,
            "risk": risk,
            "time": r["created_at"]
        })

    return render_template("history.html", history=history_data)



# ── Profile page — full health entry history for current user ─────────────────
@app.route("/profile")
def profile():

    if "user_email" not in session:
        return redirect(url_for("login"))

    user_email = session["user_email"]
    conn = get_db()
    cursor = conn.cursor()

    user_id = get_user_id(cursor, user_email)

    # All entries, newest first
    cursor.execute("""
        SELECT id, heart_rate, blood_pressure, weight, steps, sleep_hours, created_at
        FROM   health_entries
        WHERE  user_id = ?
        ORDER  BY created_at DESC
    """, (user_id,))
    rows = cursor.fetchall()

    # Also pull legacy rows so the table is complete
    cursor.execute("""
        SELECT id, heart_rate, blood_pressure, weight, steps, sleep_hours, created_at
        FROM   health_metrics
        WHERE  user_email = ?
        ORDER  BY created_at DESC
    """, (user_email,))
    legacy_rows = cursor.fetchall()

    conn.close()

    def _fmt_ts(raw):
        try:
            return datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y, %H:%M")
        except Exception:
            return str(raw)

    def _to_dict(r):
        return {
            "id":             r["id"],
            "heart_rate":     r["heart_rate"]     or "--",
            "blood_pressure": r["blood_pressure"] or "--/--",
            "weight":         r["weight"]         or "--",
            "steps":          r["steps"]          or "--",
            "sleep_hours":    r["sleep_hours"]    or "--",
            "created_at":     _fmt_ts(r["created_at"]),
        }

    entries = [_to_dict(r) for r in rows] + [_to_dict(r) for r in legacy_rows]

    # Summary stats (latest entry)
    summary = entries[0] if entries else None

    return render_template(
        "profile.html",
        user_email=user_email,
        entries=entries,
        summary=summary,
        total_entries=len(entries),
    )



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            return render_template("register.html", error="Email and password are required")

        conn = sqlite3.connect("health.db")
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            return render_template("register.html", error="User with this email already exists")

        hashed_password = generate_password_hash(password)

        cursor.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed_password))
        conn.commit()
        conn.close()

        return redirect(url_for("login"))

    return render_template("register.html")


# ── Delete a health entry (profile page) ────────────────────────────────────
@app.route("/delete/health-entry/<int:entry_id>", methods=["POST"])
def delete_health_entry(entry_id):
    if "user_email" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()
    user_id = get_user_id(cursor, session["user_email"])

    # Only delete the row if it actually belongs to this user
    cursor.execute(
        "DELETE FROM health_entries WHERE id = ? AND user_id = ?",
        (entry_id, user_id)
    )
    conn.commit()
    conn.close()

    flash("Health entry deleted. 🗑️", "success")
    return redirect(url_for("profile"))


# ── Delete a single chat message (history page) ──────────────────────────────
@app.route("/delete/chat/<int:chat_id>", methods=["POST"])
def delete_chat(chat_id):
    if "user_email" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    # Only delete rows that belong to this user
    cursor.execute(
        "DELETE FROM chat_history WHERE id = ? AND user = ?",
        (chat_id, session["user_email"])
    )
    conn.commit()
    conn.close()

    flash("Message deleted. 🗑️", "success")
    return redirect(url_for("history"))





@app.route("/logout")
def logout():

    # Session se user remove kar rahe hain
    # None isliye taaki error na aaye agar key missing ho
    session.pop("user_email", None)

    # Logout ke baad login page
    return redirect(url_for("login"))


if __name__ == "__main__":
    
    app.run(debug=True)

    
