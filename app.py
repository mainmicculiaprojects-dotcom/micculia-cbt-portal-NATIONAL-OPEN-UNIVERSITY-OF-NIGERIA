import os
import uuid
import random
from pathlib import Path
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, redirect, url_for, session,
    flash, send_file, abort
)

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from markupsafe import escape

from pypdf import PdfReader
from docx import Document
from pptx import Presentation

from google import genai


# ==========================================
# APPLICATION CONFIGURATION
# ==========================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "change-this-secret-key"
)

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///micculia.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://", "postgresql://", 1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx"}


# ==========================================
# GEMINI AI CONFIGURATION
# ==========================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL", "gemini-2.5-flash"
)

gemini_client = None

if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# ==========================================
# DATABASE MODELS
# ==========================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False)

    email = db.Column(
        db.String(150), unique=True, nullable=False
    )

    password = db.Column(db.String(255), nullable=False)

    is_admin = db.Column(
        db.Boolean, default=False
    )

    created_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    code = db.Column(
        db.String(30), nullable=False
    )

    title = db.Column(
        db.String(200), nullable=False
    )


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    course_id = db.Column(
        db.Integer, db.ForeignKey("course.id"),
        nullable=False
    )

    question_text = db.Column(
        db.Text, nullable=False
    )

    option_a = db.Column(db.Text)
    option_b = db.Column(db.Text)
    option_c = db.Column(db.Text)
    option_d = db.Column(db.Text)

    correct_answer = db.Column(
        db.String(1), nullable=False
    )

    explanation = db.Column(db.Text)


class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"),
        nullable=False
    )

    course_id = db.Column(
        db.Integer, db.ForeignKey("course.id"),
        nullable=False
    )

    score = db.Column(db.Integer, default=0)

    total_questions = db.Column(
        db.Integer, default=0
    )

    exam_type = db.Column(
        db.String(50), default="CBT"
    )

    created_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )


class StudyMaterial(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"),
        nullable=False
    )

    course_id = db.Column(
        db.Integer, db.ForeignKey("course.id"),
        nullable=True
    )

    filename = db.Column(
        db.String(255), nullable=False
    )

    extracted_text = db.Column(db.Text)

    uploaded_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )


class GeneratedQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"),
        nullable=False
    )

    course_id = db.Column(
        db.Integer, db.ForeignKey("course.id"),
        nullable=True
    )

    material_id = db.Column(
        db.Integer, db.ForeignKey("study_material.id"),
        nullable=True
    )

    question_text = db.Column(db.Text, nullable=False)

    option_a = db.Column(db.Text)
    option_b = db.Column(db.Text)
    option_c = db.Column(db.Text)
    option_d = db.Column(db.Text)

    correct_answer = db.Column(db.String(1))

    explanation = db.Column(db.Text)

    created_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )


# ==========================================
# GENERAL HELPER FUNCTIONS
# ==========================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    return db.session.get(User, user_id)


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.")
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        user = current_user()

        if not user or not user.is_admin:
            abort(403)

        return function(*args, **kwargs)

    return wrapper


def page(content):
    user = current_user()

    navigation = ""

    if user:
        navigation = """
        <nav>
            <a href="/">Dashboard</a>
            <a href="/logout">Logout</a>
        </nav>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>MICCULIA NOUN CONNECT</title>

        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #f3f5fa;
                margin: 0;
                color: #17233d;
            }}

            header {{
                background: #10264d;
                color: white;
                padding: 20px;
                text-align: center;
            }}

            nav {{
                background: #17396d;
                padding: 12px;
                text-align: center;
            }}

            nav a {{
                color: white;
                margin: 10px;
                text-decoration: none;
            }}

            main {{
                max-width: 950px;
                margin: 20px auto;
                padding: 15px;
            }}

            .card {{
                background: white;
                padding: 20px;
                margin-bottom: 18px;
                border-radius: 10px;
                box-shadow: 0 2px 8px #00000012;
            }}

            input, select, textarea {{
                width: 100%;
                padding: 12px;
                margin: 8px 0;
                box-sizing: border-box;
                border: 1px solid #ccd3df;
                border-radius: 6px;
            }}

            button, .btn {{
                background: #17396d;
                color: white;
                padding: 12px 18px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                margin: 5px 0;
            }}

            .gold {{
                background: #c89b35;
            }}

            .question {{
                padding: 15px;
                border-bottom: 1px solid #ddd;
            }}

            .flash {{
                background: #fff0c2;
                padding: 12px;
                margin: 10px 0;
                border-radius: 6px;
            }}

            footer {{
                text-align: center;
                padding: 20px;
                color: #666;
            }}
        </style>
    </head>

    <body>

        <header>
            <h1>MICCULIA NOUN CONNECT</h1>
            <p>Your smarter NOUN examination preparation platform</p>
        </header>

        {navigation}

        <main>

            {''.join(
                '<div class="flash">' + str(escape(message)) + '</div>'
                for message in []
            )}

            {content}

        </main>

        <footer>
            MICCULIA INTERNATIONAL
        </footer>

    </body>
    </html>
    """


def extract_text(filepath):
    extension = filepath.suffix.lower()

    if extension == ".pdf":
        reader = PdfReader(str(filepath))
        return "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )

    if extension == ".docx":
        document = Document(str(filepath))
        return "\n".join(
            paragraph.text
            for paragraph in document.paragraphs
        )

    if extension == ".pptx":
        presentation = Presentation(str(filepath))
        texts = []

        for slide in presentation.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    texts.append(shape.text)

        return "\n".join(texts)

    return ""


# ==========================================
# GEMINI QUESTION GENERATION
# ==========================================

def generate_ai_questions(material_text, course_code, number=30):

    if not gemini_client:
        raise ValueError(
            "Gemini API key is not configured."
        )

    material_text = material_text[:30000]

    prompt = f"""
You are an expert National Open University of Nigeria
(NOUN) examination question setter.

Generate exactly {number} high-quality objective
multiple-choice examination questions.

Course: {course_code}

Use ONLY the study material supplied below.

Each question must have:
- A clear examination-standard question.
- Four options labelled A, B, C and D.
- One correct answer.
- A concise explanation.

Return ONLY valid JSON in this format:

[
 {{
  "question": "Question text",
  "A": "Option A",
  "B": "Option B",
  "C": "Option C",
  "D": "Option D",
  "answer": "A",
  "explanation": "Explanation"
 }}
]

STUDY MATERIAL:

{material_text}
"""

    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    return response.text


# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").lower().strip()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Complete all fields.")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("This email is already registered.")
            return redirect(url_for("register"))

        user = User(
            name=name,
            email=email,
            password=generate_password_hash(password)
        )

        db.session.add(user)
        db.session.commit()

        flash("Registration successful. Please log in.")

        return redirect(url_for("login"))

    return page("""
    <div class="card">
        <h2>Create Student Account</h2>

        <form method="POST">

            <label>Full Name</label>
            <input name="name" required>

            <label>Email Address</label>
            <input name="email" type="email" required>

            <label>Password</label>
            <input name="password" type="password" required>

            <button type="submit">Register</button>

        </form>

        <p>Already registered?
        <a href="/login">Login here</a></p>
    </div>
    """)


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").lower().strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(
            user.password, password
        ):

            session["user_id"] = user.id

            flash("Welcome back!")

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return page("""
    <div class="card">
        <h2>Student Login</h2>

        <form method="POST">

            <label>Email Address</label>
            <input name="email" type="email" required>

            <label>Password</label>
            <input name="password" type="password" required>

            <button type="submit">Login</button>

        </form>

        <p>New student?
        <a href="/register">Create account</a></p>
    </div>
    """)


@app.route("/logout")
def logout():

    session.clear()

    flash("You have logged out.")

    return redirect(url_for("login"))


# ==========================================
# STUDENT DASHBOARD
# ==========================================

@app.route("/")
@login_required
def dashboard():

    user = current_user()

    materials = StudyMaterial.query.filter_by(
        user_id=user.id
    ).order_by(
        StudyMaterial.uploaded_at.desc()
    ).all()

    courses = Course.query.order_by(
        Course.code
    ).all()

    attempts = Attempt.query.filter_by(
        user_id=user.id
    ).order_by(
        Attempt.created_at.desc()
    ).limit(10).all()

    material_html = ""

    for material in materials:
        material_html += f"""
        <div class="question">
            <strong>{escape(material.filename)}</strong>
            <p>Uploaded: {material.uploaded_at}</p>
            <a href="/material/{material.id}">View extracted text</a>
        </div>
        """

    course_html = ""

    for course in courses:
        course_html += f"""
        <div class="question">
            <strong>{escape(course.code)}</strong>
            — {escape(course.title)}
            <br>
            <a href="/exam/{course.id}">Start CBT</a>
        </div>
        """

    result_html = ""

    for attempt in attempts:
        result_html += f"""
        <div class="question">
            Course ID: {attempt.course_id}
            <br>
            Score: {attempt.score}/{attempt.total_questions}
            <br>
            Date: {attempt.created_at}
        </div>
        """

    return page(f"""
    <div class="card">
        <h2>Hello, {escape(user.name)}!</h2>
        <p>Welcome to your independent student dashboard.</p>

        {('<a class="btn gold" href="/admin">Open Admin Dashboard</a>' if user.is_admin else '')}
    </div>

    <div class="card">
        <h2>Upload Your NOUN Study Material</h2>

        <form action="/upload" method="POST"
              enctype="multipart/form-data">

            <label>Select Course</label>

            <select name="course_id">
                <option value="">Select course</option>
                {''.join(
                    f'<option value="{c.id}">{escape(c.code)} - {escape(c.title)}</option>'
                    for c in courses
                )}
            </select>

            <label>Select PDF, DOCX or PPTX file</label>

            <input type="file" name="file"
                   accept=".pdf,.docx,.pptx" required>

            <button type="submit">Upload Material</button>

        </form>
    </div>

    <div class="card">
        <h2>My Uploaded Materials</h2>
        {material_html or '<p>No materials uploaded yet.</p>'}
    </div>

    <div class="card">
        <h2>Generate 30 AI Questions</h2>

        <p>Generate practice questions from your uploaded
        study material using Gemini AI.</p>

        <form action="/generate-questions" method="POST">

            <label>Select uploaded material</label>

            <select name="material_id" required>
                {''.join(
                    f'<option value="{m.id}">{escape(m.filename)}</option>'
                    for m in materials
                )}
            </select>

            <button type="submit" class="gold">
                Generate 30 AI Questions
            </button>

        </form>
    </div>

    <div class="card">
        <h2>Available Courses</h2>
        {course_html or '<p>No courses have been added yet.</p>'}
    </div>

    <div class="card">
        <h2>Your Recent Results</h2>
        {result_html or '<p>No examination attempts yet.</p>'}
    </div>
    """)


# ==========================================
# STUDY MATERIAL UPLOAD
# ==========================================

@app.route("/upload", methods=["POST"])
@login_required
def upload_material():

    file = request.files.get("file")

    if not file or not file.filename:
        flash("Please select a file.")
        return redirect(url_for("dashboard"))

    if not allowed_file(file.filename):
        flash("Only PDF, DOCX and PPTX files are allowed.")
        return redirect(url_for("dashboard"))

    filename = secure_filename(file.filename)

    unique_name = str(uuid.uuid4()) + "_" + filename

    filepath = UPLOAD_FOLDER / unique_name

    file.save(filepath)

    try:
        text_content = extract_text(filepath)
    except Exception:
        filepath.unlink(missing_ok=True)
        flash("Could not read this document.")
        return redirect(url_for("dashboard"))

    if not text_content.strip():
        filepath.unlink(missing_ok=True)
        flash("No readable text was found in the document.")
        return redirect(url_for("dashboard"))

    course_id = request.form.get("course_id")

    material = StudyMaterial(
        user_id=session["user_id"],
        course_id=int(course_id) if course_id else None,
        filename=filename,
        extracted_text=text_content
    )

    db.session.add(material)
    db.session.commit()

    flash("Study material uploaded successfully.")

    return redirect(url_for("dashboard"))


@app.route("/material/<int:material_id>")
@login_required
def view_material(material_id):

    material = StudyMaterial.query.filter_by(
        id=material_id,
        user_id=session["user_id"]
    ).first_or_404()

    return page(f"""
    <div class="card">
        <h2>{escape(material.filename)}</h2>

        <pre style="white-space:pre-wrap;">{escape(material.extracted_text[:15000])}</pre>

        <a href="/">Back to Dashboard</a>
    </div>
    """)
    # ==========================================
# AI QUESTION GENERATION
# ==========================================

import json


@app.route("/generate-questions", methods=["POST"])
@login_required
def generate_questions():

    material_id = request.form.get("material_id")

    material = StudyMaterial.query.filter_by(
        id=material_id,
        user_id=session["user_id"]
    ).first_or_404()

    try:
        raw_response = generate_ai_questions(
            material.extracted_text,
            material.filename,
            30
        )

        cleaned = raw_response.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "")
            cleaned = cleaned.replace("```", "").strip()

        questions = json.loads(cleaned)

        if not isinstance(questions, list) or not questions:
            raise ValueError("AI returned no questions.")

        saved_count = 0

        for item in questions:

            answer = str(item.get("answer", "")).upper().strip()

            if answer not in ["A", "B", "C", "D"]:
                continue

            question = GeneratedQuestion(
                user_id=session["user_id"],
                course_id=material.course_id,
                material_id=material.id,
                question_text=str(item.get("question", "")),
                option_a=str(item.get("A", "")),
                option_b=str(item.get("B", "")),
                option_c=str(item.get("C", "")),
                option_d=str(item.get("D", "")),
                correct_answer=answer,
                explanation=str(item.get("explanation", ""))
            )

            if question.question_text.strip():
                db.session.add(question)
                saved_count += 1

        db.session.commit()

        if saved_count == 0:
            raise ValueError("No valid questions were generated.")

        flash(
            f"{saved_count} AI questions generated successfully."
        )

        return redirect(
            url_for("ai_practice", material_id=material.id)
        )

    except Exception as error:

        db.session.rollback()

        flash(
            "AI question generation failed. "
            "Check your Gemini API key and study material."
        )

        return redirect(url_for("dashboard"))


# ==========================================
# AI PRACTICE EXAMINATION
# ==========================================

@app.route(
    "/ai-practice/<int:material_id>",
    methods=["GET", "POST"]
)
@login_required
def ai_practice(material_id):

    material = StudyMaterial.query.filter_by(
        id=material_id,
        user_id=session["user_id"]
    ).first_or_404()

    questions = GeneratedQuestion.query.filter_by(
        user_id=session["user_id"],
        material_id=material.id
    ).order_by(
        GeneratedQuestion.id
    ).all()

    if not questions:
        flash("No AI questions are available for this material.")
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        score = 0
        review_html = ""

        for question in questions:

            selected = request.form.get(
                f"answer_{question.id}", ""
            ).upper()

            correct = question.correct_answer.upper()

            is_correct = selected == correct

            if is_correct:
                score += 1

            review_html += f"""
            <div class="question">
                <h3>{escape(question.question_text)}</h3>

                <p>Your answer:
                <strong>{escape(selected or "Not answered")}</strong>
                </p>

                <p>Correct answer:
                <strong>{escape(correct)}</strong>
                </p>

                <p>
                {"<strong style='color:green'>Correct</strong>" if is_correct else "<strong style='color:red'>Incorrect</strong>"}
                </p>

                <p>Explanation:
                {escape(question.explanation or "No explanation provided.")}
                </p>
            </div>
            """

        if material.course_id:
            attempt = Attempt(
                user_id=session["user_id"],
                course_id=material.course_id,
                score=score,
                total_questions=len(questions),
                exam_type="AI Practice"
            )

            db.session.add(attempt)
            db.session.commit()

        percentage = round(
            (score / len(questions)) * 100, 1
        )

        return page(f"""
        <div class="card">
            <h2>AI Practice Result</h2>

            <h1>{score}/{len(questions)}</h1>

            <h2>{percentage}%</h2>

            <p>You have completed your AI practice examination.</p>

            <a class="btn" href="/">Back to Dashboard</a>
        </div>

        <div class="card">
            <h2>Corrections and Explanations</h2>
            {review_html}
        </div>
        """)

    questions_html = ""

    for number, question in enumerate(questions, 1):

        questions_html += f"""
        <div class="question">

            <h3>{number}. {escape(question.question_text)}</h3>

            <label>
                <input type="radio"
                       name="answer_{question.id}"
                       value="A" required>
                A. {escape(question.option_a)}
            </label>

            <br>

            <label>
                <input type="radio"
                       name="answer_{question.id}"
                       value="B">
                B. {escape(question.option_b)}
            </label>

            <br>

            <label>
                <input type="radio"
                       name="answer_{question.id}"
                       value="C">
                C. {escape(question.option_c)}
            </label>

            <br>

            <label>
                <input type="radio"
                       name="answer_{question.id}"
                       value="D">
                D. {escape(question.option_d)}
            </label>

        </div>
        """

    return page(f"""
    <div class="card">
        <h2>AI Practice Examination</h2>

        <p>Material: {escape(material.filename)}</p>

        <p>Total Questions: {len(questions)}</p>

        <form method="POST">

            {questions_html}

            <button type="submit" class="gold">
                Submit Examination
            </button>

        </form>
    </div>
    """)


# ==========================================
# STANDARD CBT EXAMINATION
# ==========================================

@app.route("/exam/<int:course_id>", methods=["GET"])
@login_required
def start_exam(course_id):

    course = db.session.get(Course, course_id)

    if not course:
        abort(404)

    questions = Question.query.filter_by(
        course_id=course.id
    ).all()

    if not questions:
        flash("No examination questions have been added for this course.")
        return redirect(url_for("dashboard"))

    selected_questions = random.sample(
        questions,
        min(30, len(questions))
    )

    session["exam_question_ids"] = [
        question.id for question in selected_questions
    ]

    session["exam_course_id"] = course.id

    question_html = ""

    for number, question in enumerate(selected_questions, 1):

        question_html += f"""
        <div class="question">

            <h3>{number}. {escape(question.question_text)}</h3>

            <label>
                <input type="radio"
                       name="answer_{question.id}"
                       value="A" required>
                A. {escape(question.option_a or "")}
            </label>

            <br>

            <label>
                <input type="radio"
                       name="answer_{question.id}"
                       value="B">
                B. {escape(question.option_b or "")}
            </label>

            <br>

            <label>
                <input type="radio"
                       name="answer_{question.id}"
                       value="C">
                C. {escape(question.option_c or "")}
            </label>

            <br>

            <label>
                <input type="radio"
                       name="answer_{question.id}"
                       value="D">
                D. {escape(question.option_d or "")}
            </label>

        </div>
        """

    return page(f"""
    <div class="card">
        <h2>{escape(course.code)} Examination</h2>

        <p>{escape(course.title)}</p>

        <p>Total Questions: {len(selected_questions)}</p>

        <form method="POST" action="/submit-exam/{course.id}">

            {question_html}

            <button type="submit" class="gold">
                Submit Examination
            </button>

        </form>
    </div>
    """)


@app.route(
    "/submit-exam/<int:course_id>",
    methods=["POST"]
)
@login_required
def submit_exam(course_id):

    if session.get("exam_course_id") != course_id:
        flash("Your examination session has expired.")
        return redirect(url_for("dashboard"))

    question_ids = session.get("exam_question_ids", [])

    if not question_ids:
        flash("No active examination was found.")
        return redirect(url_for("dashboard"))

    questions = Question.query.filter(
        Question.id.in_(question_ids),
        Question.course_id == course_id
    ).all()

    score = 0
    review_html = ""

    for question in questions:

        selected = request.form.get(
            f"answer_{question.id}", ""
        ).upper()

        correct = question.correct_answer.upper()

        is_correct = selected == correct

        if is_correct:
            score += 1

        review_html += f"""
        <div class="question">

            <h3>{escape(question.question_text)}</h3>

            <p>Your answer:
            {escape(selected or "Not answered")}</p>

            <p>Correct answer:
            <strong>{escape(correct)}</strong></p>

            <p>
            {"<strong style='color:green'>Correct</strong>" if is_correct else "<strong style='color:red'>Incorrect</strong>"}
            </p>

            <p>{escape(question.explanation or "")}</p>

        </div>
        """

    attempt = Attempt(
        user_id=session["user_id"],
        course_id=course_id,
        score=score,
        total_questions=len(questions),
        exam_type="CBT"
    )

    db.session.add(attempt)
    db.session.commit()

    session.pop("exam_question_ids", None)
    session.pop("exam_course_id", None)

    percentage = round(
        (score / len(questions)) * 100, 1
    ) if questions else 0

    return page(f"""
    <div class="card">
        <h2>Examination Result</h2>

        <h1>{score}/{len(questions)}</h1>

        <h2>{percentage}%</h2>

        <a class="btn" href="/">Back to Dashboard</a>
    </div>

    <div class="card">
        <h2>Corrections and Explanations</h2>

        {review_html}
    </div>
    """)


# ==========================================
# ADMIN DASHBOARD
# ==========================================

@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():

    users = User.query.order_by(
        User.created_at.desc()
    ).all()

    courses = Course.query.order_by(
        Course.code
    ).all()

    questions = Question.query.order_by(
        Question.id.desc()
    ).limit(30).all()

    user_html = ""

    for user in users:
        user_html += f"""
        <div class="question">
            <strong>{escape(user.name)}</strong>
            <br>
            {escape(user.email)}
            <br>
            {"Administrator" if user.is_admin else "Student"}
        </div>
        """

    course_html = ""

    for course in courses:
        course_html += f"""
        <div class="question">
            <strong>{escape(course.code)}</strong>
            — {escape(course.title)}
        </div>
        """

    question_html = ""

    for question in questions:
        question_html += f"""
        <div class="question">
            {escape(question.question_text)}
            <br>
            Correct Answer:
            <strong>{escape(question.correct_answer)}</strong>
        </div>
        """

    return page(f"""
    <div class="card">
        <h2>Administrator Dashboard</h2>

        <p>Manage students, courses and examination questions.</p>

        <a class="btn" href="/">Student Dashboard</a>
    </div>

    <div class="card">
        <h2>Add New Course</h2>

        <form method="POST" action="/admin/course">

            <label>Course Code</label>
            <input name="code" required>

            <label>Course Title</label>
            <input name="title" required>

            <button type="submit">Add Course</button>

        </form>
    </div>

    <div class="card">
        <h2>Add Examination Question</h2>

        <form method="POST" action="/admin/question">

            <label>Select Course</label>

            <select name="course_id" required>
                {''.join(
                    f'<option value="{c.id}">{escape(c.code)} - {escape(c.title)}</option>'
                    for c in courses
                )}
            </select>

            <label>Question</label>
            <textarea name="question_text" required></textarea>

            <label>Option A</label>
            <input name="option_a" required>

            <label>Option B</label>
            <input name="option_b" required>

            <label>Option C</label>
            <input name="option_c" required>

            <label>Option D</label>
            <input name="option_d" required>

            <label>Correct Answer</label>

            <select name="correct_answer" required>
                <option value="A">A</option>
                <option value="B">B</option>
                <option value="C">C</option>
                <option value="D">D</option>
            </select>

            <label>Explanation</label>
            <textarea name="explanation"></textarea>

            <button type="submit">Save Question</button>

        </form>
    </div>

    <div class="card">
        <h2>Registered Users ({len(users)})</h2>
        {user_html or "<p>No users yet.</p>"}
    </div>

    <div class="card">
        <h2>Available Courses ({len(courses)})</h2>
        {course_html or "<p>No courses have been added.</p>"}
    </div>

    <div class="card">
        <h2>Recently Added Questions</h2>
        {question_html or "<p>No questions have been added.</p>"}
    </div>
    """)


# ==========================================
# ADMIN COURSE MANAGEMENT
# ==========================================

@app.route("/admin/course", methods=["POST"])
@login_required
@admin_required
def add_course():

    code = request.form.get("code", "").strip().upper()

    title = request.form.get("title", "").strip()

    if not code or not title:
        flash("Enter both course code and title.")
        return redirect(url_for("admin_dashboard"))

    existing = Course.query.filter_by(code=code).first()

    if existing:
        flash("This course code already exists.")
        return redirect(url_for("admin_dashboard"))

    course = Course(
        code=code,
        title=title
    )

    db.session.add(course)
    db.session.commit()

    flash("Course added successfully.")

    return redirect(url_for("admin_dashboard"))


# ==========================================
# ADMIN QUESTION MANAGEMENT
# ==========================================

@app.route("/admin/question", methods=["POST"])
@login_required
@admin_required
def add_question():

    course_id = request.form.get("course_id")

    question_text = request.form.get(
        "question_text", ""
    ).strip()

    option_a = request.form.get("option_a", "").strip()
    option_b = request.form.get("option_b", "").strip()
    option_c = request.form.get("option_c", "").strip()
    option_d = request.form.get("option_d", "").strip()

    correct_answer = request.form.get(
        "correct_answer", ""
    ).upper().strip()

    explanation = request.form.get(
        "explanation", ""
    ).strip()

    if not course_id or not question_text:
        flash("Complete the required question fields.")
        return redirect(url_for("admin_dashboard"))

    if correct_answer not in ["A", "B", "C", "D"]:
        flash("Select a valid correct answer.")
        return redirect(url_for("admin_dashboard"))

    course = db.session.get(Course, int(course_id))

    if not course:
        flash("Selected course does not exist.")
        return redirect(url_for("admin_dashboard"))

    question = Question(
        course_id=course.id,
        question_text=question_text,
        option_a=option_a,
        option_b=option_b,
        option_c=option_c,
        option_d=option_d,
        correct_answer=correct_answer,
        explanation=explanation
    )

    db.session.add(question)
    db.session.commit()

    flash("Examination question added successfully.")

    return redirect(url_for("admin_dashboard"))


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

with app.app_context():

    db.create_all()

    admin_email = os.environ.get("ADMIN_EMAIL", "").lower().strip()

    admin_password = os.environ.get("ADMIN_PASSWORD", "")

    if admin_email and admin_password:

        existing = User.query.filter_by(
            email=admin_email
        ).first()

        if not existing:

            db.session.add(User(
                name="Administrator",
                email=admin_email,
                password=generate_password_hash(admin_password),
                is_admin=True
            ))

            db.session.commit()


# ==========================================
# APPLICATION START
# ==========================================

if __name__ == "__main__":
    app.run()
