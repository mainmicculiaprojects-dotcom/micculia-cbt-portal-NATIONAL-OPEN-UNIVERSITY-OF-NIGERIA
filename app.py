
import os
import random
from datetime import datetime
from functools import wraps

from flask import Flask, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret")
database_url = os.environ.get("DATABASE_URL", "sqlite:///micculia.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(200), nullable=False)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    a = db.Column(db.String(500), nullable=False)
    b = db.Column(db.String(500), nullable=False)
    c = db.Column(db.String(500), nullable=False)
    d = db.Column(db.String(500), nullable=False)
    answer = db.Column(db.String(1), nullable=False)
    explanation = db.Column(db.Text, default="")


class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"))
    score = db.Column(db.Integer)
    total = db.Column(db.Integer)
    exam_type = db.Column(db.String(30))
    date = db.Column(db.DateTime, default=datetime.utcnow)


def page(content):
    return f"""
    <!DOCTYPE html>
    <html><head><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>MICCULIA NOUN CONNECT</title>
    <style>
    body{{font-family:Arial;background:#f2f5fa;margin:0;color:#17233c}}
    header{{background:#071b3a;color:white;padding:22px;text-align:center}}
    main{{max-width:850px;margin:25px auto;padding:20px}}
    .card{{background:white;padding:22px;margin:15px 0;border-radius:12px;
    box-shadow:0 2px 9px #0001}}
    input,select,textarea{{width:100%;padding:12px;margin:8px 0;
    box-sizing:border-box;border:1px solid #ccd2dc;border-radius:6px}}
    button,.btn{{background:#d5a52c;color:#071b3a;border:0;padding:12px 18px;
    border-radius:6px;font-weight:bold;cursor:pointer;text-decoration:none;
    display:inline-block;margin:5px 0}}
    a{{color:#164c8a}} .muted{{color:#667085;font-size:13px}}
    </style></head><body>
    <header><h2>MICCULIA NOUN CONNECT</h2>
    <p>Your smarter NOUN examination preparation platform</p></header>
    <main>{content}</main></body></html>
    """


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = db.session.get(User, session.get("user_id"))
        if not user or not user.is_admin:
            return "Access denied. Admin only.", 403
        return fn(*args, **kwargs)
    return wrapper


@app.route("/")
def home():
    return page("""
    <div class="card">
    <h2>Welcome to MICCULIA NOUN CONNECT</h2>
    <p>Prepare smarter. Practise effectively. Improve your examination performance.</p>
    <a class="btn" href="/register">Create Student Account</a>
    <a class="btn" href="/login">Login</a>
    </div>
    """)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        if not name or not email or len(password) < 6:
            return page("<h3>Enter your details and use a password of at least 6 characters.</h3><a href='/register'>Try again</a>")
        if User.query.filter_by(email=email).first():
            return page("<h3>Email already registered.</h3><a href='/register'>Go back</a>")
        user = User(name=name, email=email,
                    password=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash("Account created. Please log in.")
        return redirect(url_for("login"))
    return page("""
    <div class="card"><h2>Student Registration</h2>
    <form method="post">
    <input name="name" placeholder="Full name" required>
    <input name="email" type="email" placeholder="Email address" required>
    <input name="password" type="password" placeholder="Password (minimum 6 characters)" required>
    <button>Create Account</button></form><a href="/login">Already registered? Login</a></div>
    """)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, request.form["password"]):
            session.clear()
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))
        return page("<h3>Incorrect email or password.</h3><a href='/login'>Try again</a>")
    return page("""
    <div class="card"><h2>Login</h2>
    <form method="post">
    <input name="email" type="email" placeholder="Email address" required>
    <input name="password" type="password" placeholder="Password" required>
    <button>Login</button></form><a href="/register">Create account</a></div>
    """)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = db.session.get(User, session["user_id"])
    courses = Course.query.order_by(Course.code).all()
    attempts = Attempt.query.filter_by(user_id=user.id).order_by(Attempt.date.desc()).limit(10).all()
    course_html = "".join(
        f"<p><b>{c.code}</b> - {c.title} "
        f"<a href='/exam/{c.id}/tma'>TMA Practice</a> | "
        f"<a href='/exam/{c.id}/semester'>Semester Practice</a></p>"
        for c in courses
    ) or "<p>No courses have been added yet.</p>"
    history = "".join(
        f"<p>{a.exam_type} | Score: {a.score}/{a.total} | {a.date.strftime('%d %b %Y')}</p>"
        for a in attempts
    ) or "<p>No examination attempts yet.</p>"
    admin_link = "<p><a href='/admin'>Open Admin Dashboard</a></p>" if user.is_admin else ""
    return page(f"""
    <div class="card"><h2>Hello, {user.name}!</h2>
    <p>Welcome to your student dashboard.</p>
    {admin_link}<a href="/logout">Logout</a></div>
    <div class="card"><h3>Available Courses</h3>{course_html}</div>
    <div class="card"><h3>Your Recent Results</h3>{history}</div>
    """)


@app.route("/exam/<int:course_id>/<exam_type>", methods=["GET", "POST"])
@login_required
def exam(course_id, exam_type):
    course = db.session.get(Course, course_id)
    if not course or exam_type not in ["tma", "semester"]:
        return "Invalid course or examination type.", 404

    limit = 30 if exam_type == "tma" else 70
    questions = Question.query.filter_by(course_id=course_id).all()
    if len(questions) < limit:
        return page(f"""
        <div class="card"><h3>{course.code}: {course.title}</h3>
        <p>There are currently {len(questions)} questions in this course.
        At least {limit} questions are needed for this practice pack.</p>
        <a href="/dashboard">Return to dashboard</a></div>
        """)

    if request.method == "POST":
        selected = session.get("exam_questions", [])
        score = 0
        review = ""
        for qid in selected:
            q = db.session.get(Question, qid)
            if not q:
                continue
            choice = request.form.get(str(qid), "").upper()
            correct = q.answer.upper()
            if choice == correct:
                score += 1
            review += f"<div class='card'><b>{q.question}</b><p>Your answer: {choice or 'Not answered'} | Correct: {correct}</p><p>{q.explanation}</p></div>"

        attempt = Attempt(user_id=session["user_id"], course_id=course_id,
                          score=score, total=len(selected), exam_type=exam_type.upper())
        db.session.add(attempt)
        db.session.commit()
        session.pop("exam_questions", None)
        return page(f"""
        <div class="card"><h2>Examination Result</h2>
        <h1>{score}/{len(selected)}</h1>
        <p>Percentage: {round(score / len(selected) * 100)}%</p>
        <a class="btn" href="/dashboard">Return to Dashboard</a></div>
        <h3>Corrections and Explanations</h3>{review}
        """)

    chosen = random.sample(questions, limit)
    session["exam_questions"] = [q.id for q in chosen]
    fields = ""
    for i, q in enumerate(chosen, 1):
        fields += f"""
        <div class="card"><b>{i}. {q.question}</b>
        """
        for letter, option in [("A", q.a), ("B", q.b), ("C", q.c), ("D", q.d)]:
            fields += f"<p><label><input style='width:auto' type='radio' name='{q.id}' value='{letter}'> {letter}. {option}</label></p>"
        fields += "</div>"
    return page(f"""
    <div class="card"><h2>{course.code} - {exam_type.upper()} Practice</h2>
    <p>Questions: {limit} | Each question carries 1 mark.</p>
    <form method="post">{fields}<button type="submit">Submit Examination</button></form></div>
    """)


@app.route("/admin")
@login_required
@admin_required
def admin():
    courses = Course.query.order_by(Course.code).all()
    course_list = "".join(
        f"<p>{c.code} - {c.title} | {Question.query.filter_by(course_id=c.id).count()} questions</p>"
        for c in courses
    )
    options = "".join(f"<option value='{c.id}'>{c.code} - {c.title}</option>" for c in courses)
    return page(f"""
    <div class="card"><h2>Administrator Dashboard</h2>
    <h3>Add Course</h3>
    <form method="post" action="/admin/course">
    <input name="code" placeholder="Course code e.g. ECO101" required>
    <input name="title" placeholder="Course title" required>
    <button>Add Course</button></form></div>
    <div class="card"><h3>Upload Questions (one at a time)</h3>
    <form method="post" action="/admin/question">
    <select name="course_id" required>{options}</select>
    <textarea name="question" placeholder="Enter question" required></textarea>
    <input name="a" placeholder="Option A" required>
    <input name="b" placeholder="Option B" required>
    <input name="c" placeholder="Option C" required>
    <input name="d" placeholder="Option D" required>
    <select name="answer"><option>A</option><option>B</option><option>C</option><option>D</option></select>
    <textarea name="explanation" placeholder="Explanation (optional)"></textarea>
    <button>Add Question</button></form></div>
    <div class="card"><h3>Courses</h3>{course_list}</div>
    <a href="/dashboard">Back to Dashboard</a>
    """)


@app.route("/admin/course", methods=["POST"])
@login_required
@admin_required
def add_course():
    course = Course(code=request.form["code"].strip().upper(),
                    title=request.form["title"].strip())
    db.session.add(course)
    db.session.commit()
    return redirect(url_for("admin"))


@app.route("/admin/question", methods=["POST"])
@login_required
@admin_required
def add_question():
    q = Question(
        course_id=int(request.form["course_id"]),
        question=request.form["question"],
        a=request.form["a"], b=request.form["b"],
        c=request.form["c"], d=request.form["d"],
        answer=request.form["answer"].upper(),
        explanation=request.form.get("explanation", "")
    )
    db.session.add(q)
    db.session.commit()
    return redirect(url_for("admin"))


with app.app_context():
    db.create_all()
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if admin_email and admin_password:
        existing = User.query.filter_by(email=admin_email.lower()).first()
        if not existing:
            db.session.add(User(
                name="Administrator",
                email=admin_email.lower(),
                password=generate_password_hash(admin_password),
                is_admin=True
            ))
            db.session.commit()


if __name__ == "__main__":
    app.run()
  
