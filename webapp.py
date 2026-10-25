"""Browser-based edition of the Student Management System.

The original Tkinter desktop application remains available through ``python app.py``.
Run this web edition with ``flask --app webapp run`` during development or Gunicorn
in a hosted environment.
"""

from __future__ import annotations

import os
from datetime import date
from functools import wraps

import mysql.connector
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect


app = Flask(__name__)
secret_key = os.environ.get("SECRET_KEY")
if not secret_key and os.environ.get("RENDER"):
    raise RuntimeError("Set a unique SECRET_KEY in the hosting dashboard before deploying.")
app.config.update(
    SECRET_KEY=secret_key or "local-development-only-change-before-hosting",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "true" if os.environ.get("RENDER") else "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)
csrf = CSRFProtect(app)


def db_connection():
    required = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError("Set the database environment variables: " + ", ".join(missing))
    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        connection_timeout=10,
    )


def query(sql, params=(), *, one=False):
    connection = db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(sql, params)
        result = cursor.fetchone() if one else cursor.fetchall()
        cursor.close()
        return result
    finally:
        connection.close()


def execute(sql, params=()):
    connection = db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(sql, params)
        connection.commit()
        cursor.close()
    finally:
        connection.close()


def current_user():
    if not hasattr(g, "user"):
        user_id = session.get("user_id")
        g.user = query(
            "SELECT id, uname, typeofuser FROM login_details WHERE id=%s",
            (user_id,), one=True,
        ) if user_id else None
        if user_id and not g.user:
            session.clear()
    return g.user


@app.before_request
def load_user():
    current_user()


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user()["typeofuser"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.get("/")
def index():
    return redirect(url_for("dashboard" if current_user() else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = query(
            "SELECT id, uname, typeofuser FROM login_details "
            "WHERE uname=%s AND password=SHA2(%s,256)",
            (username, password), one=True,
        )
        if user:
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            destination = request.args.get("next", "")
            if not destination.startswith("/") or destination.startswith("//"):
                destination = url_for("dashboard")
            return redirect(destination)
        flash("The username or password was not recognized.", "error")
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


@app.get("/dashboard")
@login_required
def dashboard():
    user = current_user()
    role = user["typeofuser"]
    if role == "student":
        profile = query(
            "SELECT id, first_name, middle_name, last_name, std, division, roll_no "
            "FROM student WHERE id=%s", (user["id"],), one=True,
        )
        if not profile:
            abort(404)
        return render_template("student_dashboard.html", profile=profile)
    if role == "faculty":
        profile = query(
            "SELECT id, first_name, middle_name, last_name, sub, email "
            "FROM faculty WHERE id=%s", (user["id"],), one=True,
        )
        if not profile:
            abort(404)
        class_assignment = query(
            "SELECT std, divison FROM div_details WHERE faculty_id=%s",
            (user["id"],), one=True,
        )
        return render_template("faculty_dashboard.html", profile=profile, assignment=class_assignment)
    if role in ("admin", "superadmin"):
        totals = {
            "students": query("SELECT COUNT(*) AS total FROM student", one=True)["total"],
            "faculty": query("SELECT COUNT(*) AS total FROM faculty", one=True)["total"],
            "admins": query("SELECT COUNT(*) AS total FROM admin", one=True)["total"],
        }
        return render_template("admin_dashboard.html", totals=totals)
    abort(403)


@app.get("/student/attendance")
@roles_required("student")
def student_attendance():
    rows = query(
        "SELECT YEAR(date_attend) AS year, MONTH(date_attend) AS month, "
        "COUNT(*) AS school_days, SUM(attended='Y') AS attended_days "
        "FROM attendance WHERE id=%s GROUP BY YEAR(date_attend), MONTH(date_attend) "
        "ORDER BY year DESC, month DESC", (current_user()["id"],),
    )
    return render_template("student_attendance.html", rows=rows)


@app.get("/student/fees")
@roles_required("student")
def student_fees():
    rows = query(
        "SELECT f.*, sf.monthly, sf.yearly FROM fees f "
        "LEFT JOIN store_fees sf ON sf.year_=f.year_ WHERE f.id=%s ORDER BY f.year_ DESC",
        (current_user()["id"],),
    )
    return render_template("student_fees.html", rows=rows)


@app.get("/records/<record_type>")
@roles_required("admin", "superadmin", "faculty")
def records(record_type):
    if record_type not in {"students", "faculty", "admins"}:
        abort(404)
    role = current_user()["typeofuser"]
    if role == "faculty" and record_type != "students":
        abort(403)
    if record_type == "admins" and role != "superadmin":
        abort(403)
    if record_type == "students":
        rows = query(
            "SELECT id, first_name, middle_name, last_name, std, division, roll_no "
            "FROM student ORDER BY std, division, roll_no"
        )
        title = "Students"
    elif record_type == "faculty":
        rows = query(
            "SELECT id, first_name, middle_name, last_name, sub AS subject, email "
            "FROM faculty ORDER BY first_name, last_name"
        )
        title = "Faculty"
    else:
        rows = query("SELECT id, name, age, sex, phoneno FROM admin ORDER BY name")
        title = "Administrators"
    return render_template("records.html", rows=rows, record_type=record_type, title=title)


@app.route("/faculty/assignment", methods=["GET", "POST"])
@roles_required("faculty")
def faculty_assignment():
    faculty_id = current_user()["id"]
    if request.method == "POST":
        try:
            standard = int(request.form.get("standard", ""))
        except ValueError:
            abort(400, "Choose a valid class.")
        division = request.form.get("division", "")
        if standard not in range(1, 11) or division not in {"A", "B", "C", "D"}:
            abort(400, "Choose a valid class and division.")
        existing = query("SELECT faculty_id FROM div_details WHERE faculty_id=%s", (faculty_id,), one=True)
        if existing:
            execute("UPDATE div_details SET std=%s, divison=%s WHERE faculty_id=%s", (standard, division, faculty_id))
        else:
            execute("INSERT INTO div_details (std, divison, faculty_id) VALUES (%s,%s,%s)", (standard, division, faculty_id))
        flash("Your class teacher assignment was saved.", "success")
        return redirect(url_for("dashboard"))
    assignment = query("SELECT std, divison FROM div_details WHERE faculty_id=%s", (faculty_id,), one=True)
    return render_template("faculty_assignment.html", assignment=assignment)


@app.route("/attendance/mark", methods=["GET", "POST"])
@roles_required("admin", "superadmin", "faculty")
def mark_attendance():
    user = current_user()
    assignment = None
    if user["typeofuser"] == "faculty":
        assignment = query(
            "SELECT std, divison FROM div_details WHERE faculty_id=%s",
            (user["id"],), one=True,
        )
        if not assignment:
            abort(403, "A class must be assigned to this faculty account first.")
    selected_date = request.values.get("date", date.today().isoformat())
    try:
        date.fromisoformat(selected_date)
    except ValueError:
        abort(400, "Invalid attendance date.")
    if request.method == "POST":
        connection = db_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("INSERT IGNORE INTO present (present_date) VALUES (%s)", (selected_date,))
            for student_id, attended in request.form.items():
                if not student_id.startswith("student_"):
                    continue
                student_id = student_id.removeprefix("student_")
                if attended not in ("Y", "N"):
                    continue
                if assignment:
                    cursor.execute(
                        "SELECT id FROM student WHERE id=%s AND std=%s AND division=%s",
                        (student_id, assignment["std"], assignment["divison"]),
                    )
                else:
                    cursor.execute("SELECT id FROM student WHERE id=%s", (student_id,))
                if not cursor.fetchone():
                    continue
                cursor.execute(
                    "SELECT id FROM attendance WHERE id=%s AND date_attend=%s LIMIT 1",
                    (student_id, selected_date),
                )
                exists = cursor.fetchone()
                if exists:
                    cursor.execute(
                        "UPDATE attendance SET attended=%s WHERE id=%s AND date_attend=%s",
                        (attended, student_id, selected_date),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO attendance (id, attended, date_attend) VALUES (%s,%s,%s)",
                        (student_id, attended, selected_date),
                    )
            connection.commit()
            flash("Attendance saved.", "success")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return redirect(url_for("mark_attendance", date=selected_date))
    if assignment:
        students = query(
            "SELECT id, first_name, middle_name, last_name, roll_no, division, std "
            "FROM student WHERE std=%s AND division=%s ORDER BY roll_no",
            (assignment["std"], assignment["divison"]),
        )
    else:
        students = query(
            "SELECT id, first_name, middle_name, last_name, roll_no, division, std "
            "FROM student ORDER BY std, division, roll_no"
        )
    attendance = query(
        "SELECT id, attended FROM attendance WHERE date_attend=%s", (selected_date,)
    )
    attendance_by_student = {row["id"]: row["attended"] for row in attendance}
    return render_template(
        "mark_attendance.html", students=students,
        attendance_by_student=attendance_by_student, selected_date=selected_date,
        assignment=assignment,
    )


@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", code=403, message="You do not have access to this page."), 403


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="This page or record was not found."), 404


@app.errorhandler(500)
def server_error(error):
    app.logger.exception("Unhandled web application error")
    return render_template(
        "error.html", code=500,
        message="The service encountered an error. Check the deployment logs and database configuration.",
    ), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
