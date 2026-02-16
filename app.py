from flask import Flask, render_template, request, redirect, url_for, session
import requests
from google import genai
from datetime import datetime

import sqlite3

app = Flask(__name__)
app.secret_key = "supersecretkey"   # session ke liye mandatory

#Database connection
def init_db():
    conn = sqlite3.connect("health.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        symptoms TEXT,
        condition TEXT,
        risk TEXT,
        advice TEXT,
        created_at TEXT 
    ) 
    """)# created_at column added for timestamp

    conn.commit()
    conn.close()


@app.route("/")
def home():
    return render_template("home.html")

@app.route("/about")
def about():
    return "<h1>About Page 😎</h1>"


@app.route("/login", methods=["GET", "POST"])
def login():

    # agar form submit hua
    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")
        print(request.form)


         # fake validation
        if  email == "admin@gmail.com" and password == "123":
            session["user"] = email   # 🧠 NOTE LIKH DIYA
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Invalid credentials")

        return redirect(url_for("dashboard"))

    # agar sirf page open hua
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():

    # 🧠 ENTRY CHECK
    if "user" not in session:
        return redirect(url_for("login"))

    # TODO: Fetch real data from database
    # For now, using mock data
    health_data = {
        "heart_rate": 72,
        "blood_pressure": "120/80",
        "weight": 70,
        "steps": 5400,
        "sleep": "7h 30m"
    }

    recent_activities = [
        {"activity": "Morning Jog", "time": "07:00 AM", "duration": "30 mins"},
        {"activity": "Yoga", "time": "06:00 PM", "duration": "45 mins"},
        {"activity": "Walking", "time": "08:00 PM", "duration": "20 mins"}
    ]

    return render_template("dashboard.html", data=health_data, activities=recent_activities)


# ===== AI FUNCTION (ROUTE KE BAHAR) =====
def ask_ai(message):

    client = genai.Client(api_key="API KEY")

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=f"You are a medical assistant. Answer briefly.\nUser: {message}",
    )

    return response.text



# ===== ROUTE =====
@app.route("/predict", methods=["GET", "POST"])
def predict():

    if "chat" not in session:
        session["chat"] = []

    if request.method == "POST":
        message = request.form.get("message")

        if message and message.strip():

            session["chat"].append({
                "role": "user",
                "text": message
            })

            reply = ask_ai(message)

            session["chat"].append({
                "role": "ai",
                "text": reply
            })

    return render_template("predict.html", chat=session["chat"])


#History page
@app.route("/history")
def history():

    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("health.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, symptoms, condition, risk, advice, created_at FROM history WHERE user = ?", (session["user"],))
    rows = cursor.fetchall()

    conn.close()

    history_data = []
    for row in rows:
        history_data.append({
            "id" : row[0],
            "symptoms": row[1],
            "condition": row[2],
            "risk": row[3],
            "advice": row[4],
            "time": row[5]

        })

    return render_template("history.html", history=history_data)


@app.route("/delete/<int:id>")
def delete(id):

    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("health.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM history WHERE id = ? AND user = ?", (id, session["user"]))

    conn.commit()
    conn.close()

    return redirect(url_for("history"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)

    
