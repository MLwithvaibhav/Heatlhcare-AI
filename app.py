from flask import Flask, render_template, request, redirect, url_for, session
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
        advice TEXT
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


@app.route("/predict", methods=["GET", "POST"])
def predict():

    if "user" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        symptoms = request.form.get("symptoms")

        print("User said:", symptoms)

        if symptoms:
            condition = "Flu 🤒"
            risk = "Medium"
            advice = "Take rest and drink plenty of fluids."
        else:
            condition = "Unknown"
            risk = "-"
            advice = "Please describe your symptoms."

        # Database connection (save the prediction to database)
        conn = sqlite3.connect("health.db")
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO history (user, symptoms, condition, risk, advice) VALUES (?, ?, ?, ?, ?)",
            (session["user"], symptoms, condition, risk, advice)
        )

        conn.commit()
        conn.close()

        return render_template(
            "predict.html",
            condition=condition,
            risk=risk,
            advice=advice
        )


    # GET request
    return render_template("predict.html")

#History page
@app.route("/history")
def history():

    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("health.db")
    cursor = conn.cursor()

    cursor.execute("SELECT symptoms, condition, risk, advice FROM history WHERE user = ?", (session["user"],))
    rows = cursor.fetchall()

    conn.close()

    history_data = []
    for row in rows:
        history_data.append({
            "symptoms": row[0],
            "condition": row[1],
            "risk": row[2],
            "advice": row[3]
        })

    return render_template("history.html", history=history_data)




if __name__ == "__main__":
    init_db()
    app.run(debug=True)

    
