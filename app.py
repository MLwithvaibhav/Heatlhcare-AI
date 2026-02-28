from flask import Flask, render_template, request, redirect, url_for, session
import requests
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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        role TEXT,
        message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

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
            session["user_email"] = user[1]
            print("USER:", user)
            print("PASSWORD MATCH:", check_password_hash(user[2], password) if user else "NO USER")
            # Login successful → dashboard pe bhej do
            return redirect(url_for("dashboard"))

        else:
            # Agar credentials galat hain
            return render_template("login.html", error="Invalid credentials")

    # Agar GET request hai
    return render_template("login.html")



@app.route("/dashboard")
def dashboard():

    # Correct session check
    if "user_email" not in session:
        return redirect(url_for("login"))

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

    return render_template(
        "dashboard.html",
        data=health_data,
        activities=recent_activities
    )

# ===== AI FUNCTION (ROUTE KE BAHAR) =====
def ask_ai(message):

    client = genai.Client(api_key="API KEY")

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=f"You are a medical assistant. Answer briefly.\nUser: {message}",
    )

    return response.text



# ===== ROUTE =====
# Ye route define karta hai ki jab /predict URL hit hoga toh ye function chalega
# methods=["GET", "POST"] ka matlab:
# GET  -> page open karne ke liye
# POST -> form submit hone ke liye

@app.route("/predict", methods=["GET", "POST"])
def predict():

    # Agar session me "chat" exist nahi karta
    # toh ek empty list bana do
    # Session temporary storage hota hai jo user ke browser ke liye hota hai
    if "chat" not in session:
        session["chat"] = []

    # Agar request POST method se aayi hai (form submit hua hai)
    if request.method == "POST":

        # Form se message nikaal rahe hain
        # request.form me HTML form ke data hote hain
        message = request.form.get("message")

        # Check kar rahe hain ki message empty na ho
        # message.strip() extra spaces remove karta hai
        if message and message.strip():

            # User ka message session chat me add kar rahe hain
            # Ye frontend me chat history show karne ke kaam aata hai
            session["chat"].append({
                "role": "user",
                "text": message
            })

            # AI ko message bhej rahe hain
            # ask_ai() tumhara custom function hoga jo AI response return karta hai
            reply = ask_ai(message)

            # AI ka reply bhi session me add kar diya
            session["chat"].append({
                "role": "ai",
                "text": reply
            })

            # ---------------- DATABASE PART ----------------

            # SQLite database se connect ho rahe hain
            conn = sqlite3.connect("health.db")

            # Cursor object banate hain query execute karne ke liye
            cursor = conn.cursor()

            # User ka message database me save kar rahe hain
            # ? placeholders SQL injection se bachate hain
            cursor.execute("""
            INSERT INTO chat_history (user, role, message)
            VALUES (?, ?, ?)
            """, (session["user"], "user", message))

            # AI ka reply bhi database me save kar rahe hain
            cursor.execute("""
            INSERT INTO chat_history (user, role, message)
            VALUES (?, ?, ?)
            """, (session["user"], "ai", reply))

            # Changes database me permanently save karne ke liye
            conn.commit()

            # Connection close karna important hai memory free karne ke liye
            conn.close()

    # Finally predict.html render ho raha hai
    # aur chat history template ko pass kar rahe hain
    return render_template("predict.html", chat=session["chat"])

#History page
@app.route("/history")
def history():

    if "user_email" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("health.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT role, message, created_at
    FROM chat_history
    WHERE user = ?
    ORDER BY created_at ASC
    """, (session["user_email"],))
    
    rows = cursor.fetchall()
    conn.close()

    history_data = []
    for row in rows:
        history_data.append({
            "role": row[0],
            "text": row[1],
            "time": row[2]
        })

    return render_template("history.html", history=history_data)



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



@app.route("/logout")
def logout():

    # Session se user remove kar rahe hain
    # None isliye taaki error na aaye agar key missing ho
    session.pop("user_email", None)

    # Logout ke baad login page
    return redirect(url_for("login"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)

    
