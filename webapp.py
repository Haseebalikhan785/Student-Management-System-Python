"""Browser-based edition of the Student Management System.

The original Tkinter desktop application remains available through ``python app.py``.
Run this web edition with ``flask --app webapp run`` during development or Gunicorn
in a hosted environment.
"""

from __future__ import annotations

import os
from threading import Lock
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
_schema_ready = False
_schema_lock = Lock()


def db_connection():
    global _schema_ready
    required = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError("Set the database environment variables: " + ", ".join(missing))
    connection = mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        connection_timeout=10,
    )
    if not _schema_ready:
        with _schema_lock:
            if not _schema_ready:
                # The original schema omitted primary keys on these tables.
                # Create only missing tables with replication-friendly keys.
                cursor = connection.cursor()
                cursor.execute("""CREATE TABLE IF NOT EXISTS div_details (
        faculty_id VARCHAR(8) NOT NULL PRIMARY KEY,
        std INT NOT NULL,
        divison CHAR(1) NOT NULL,
        CONSTRAINT fk_div_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS fees (
        id VARCHAR(8) NOT NULL,
        fullyearpaid ENUM('Y','N') NOT NULL DEFAULT 'N',
        year_ YEAR NOT NULL,
        jan ENUM('Y','N') NOT NULL DEFAULT 'N',
        feb ENUM('Y','N') NOT NULL DEFAULT 'N',
        mar ENUM('Y','N') NOT NULL DEFAULT 'N',
        april ENUM('Y','N') NOT NULL DEFAULT 'N',
        may ENUM('Y','N') NOT NULL DEFAULT 'N',
        june ENUM('Y','N') NOT NULL DEFAULT 'N',
        july ENUM('Y','N') NOT NULL DEFAULT 'N',
        aug ENUM('Y','N') NOT NULL DEFAULT 'N',
        sept ENUM('Y','N') NOT NULL DEFAULT 'N',
        oct ENUM('Y','N') NOT NULL DEFAULT 'N',
        nov ENUM('Y','N') NOT NULL DEFAULT 'N',
        dece ENUM('Y','N') NOT NULL DEFAULT 'N',
        PRIMARY KEY (id, year_),
        CONSTRAINT fk_fees_student FOREIGN KEY (id) REFERENCES student(id)
            ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT fk_fees_year FOREIGN KEY (year_) REFERENCES store_fees(year_)
            ON DELETE RESTRICT ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS attendance (
        id VARCHAR(8) NOT NULL,
        attended ENUM('Y','N') NOT NULL,
        date_attend DATE NOT NULL,
        PRIMARY KEY (id, date_attend),
        CONSTRAINT fk_attendance_student FOREIGN KEY (id) REFERENCES student(id)
            ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT fk_attendance_day FOREIGN KEY (date_attend) REFERENCES present(present_date)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                connection.commit()
                cursor.close()
                _schema_ready = True
    return connection


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


def next_id(cursor, prefix, initial):
    """Return the next unused legacy-style identifier (ST10000, FT10000, AD1000)."""
    cursor.execute(
        "SELECT MAX(CAST(SUBSTRING(id, 3) AS UNSIGNED)) AS last_id "
        "FROM login_details WHERE id LIKE %s",
        (prefix + "%",),
    )
    row = cursor.fetchone()
    value = max(initial, int(row[0] or initial - 1) + 1)
    return f"{prefix}{value}"


def clean_form(fields):
    values = {}
    for name, label, kind, required in fields:
        value = request.form.get(name, "").strip()
        if required and not value:
            raise ValueError(f"Please enter {label.lower()}.")
        if value and kind == "number":
            try:
                value = int(value)
            except ValueError as exc:
                raise ValueError(f"{label} must be a number.") from exc
        values[name] = value or None
    return values


RECORD_FIELDS = {
    "students": [
        ("first_name", "First name", "text", True), ("middle_name", "Middle name", "text", False),
        ("last_name", "Last name", "text", True), ("roll_no", "Roll number", "number", True),
        ("division", "Division (A-D)", "text", True), ("std", "Class (1-10)", "number", True),
        ("dob", "Date of birth", "date", True), ("doa", "Date of admission", "date", True),
        ("sex", "Gender", "text", True), ("bloodgroup", "Blood group", "text", False),
        ("phoneno", "Phone number", "number", True), ("address", "Address", "textarea", True),
        ("father_name", "Father's name", "text", True), ("mother_name", "Mother's name", "text", True),
        ("father_occ", "Father's occupation", "text", False), ("mother_occ", "Mother's occupation", "text", False),
    ],
    "faculty": [
        ("first_name", "First name", "text", True), ("middle_name", "Middle name", "text", False),
        ("last_name", "Last name", "text", True), ("experience", "Experience (years)", "number", True),
        ("doj", "Date joined", "date", True), ("dob", "Date of birth", "date", True),
        ("email", "Email", "email", True), ("sub", "Subject", "text", True),
        ("address", "Address", "textarea", True), ("qualification", "Qualification", "text", True),
        ("age", "Age", "number", True), ("sex", "Gender", "text", True),
        ("phoneno", "Phone number", "number", True),
    ],
    "admins": [
        ("name", "Full name", "text", True), ("address", "Address", "textarea", True),
        ("phoneno", "Phone number", "number", True), ("age", "Age", "number", True),
        ("sex", "Gender", "text", True),
    ],
}


def create_record(record_type, values, username, password):
    if not username or (not password):
        raise ValueError("Username and password are required for a new account.")
    if len(password) < 8:
        raise ValueError("Use a password with at least 8 characters.")
    connection = db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM login_details WHERE uname=%s", (username,))
        if cursor.fetchone():
            raise ValueError("That username is already in use.")
        prefix, initial, role = {
            "students": ("ST", 10000, "student"),
            "faculty": ("FT", 10000, "faculty"),
            "admins": ("AD", 1000, "admin"),
        }[record_type]
        user_id = next_id(cursor, prefix, initial)
        if record_type == "students":
            division = (values["division"] or "").upper()
            standard = values["std"]
            if division not in {"A", "B", "C", "D"} or standard not in range(1, 11):
                raise ValueError("Choose a class from 1–10 and division A–D.")
            cursor.execute("SELECT year_ FROM store_fees WHERE year_=%s", (values["doa"][:4],))
            if not cursor.fetchone():
                raise ValueError("Add a fee plan for the admission year before adding this student.")
        columns = [field[0] for field in RECORD_FIELDS[record_type]]
        data = [values[name] for name in columns]
        if "division" in values:
            data[columns.index("division")] = values["division"].upper()
        cursor.execute(
            f"INSERT INTO { {'students':'student','faculty':'faculty','admins':'admin'}[record_type]} "
            f"(id, {', '.join(columns)}) VALUES ({', '.join(['%s'] * (len(data) + 1))})",
            [user_id, *data],
        )
        cursor.execute(
            "INSERT INTO login_details (id, uname, password, typeofuser) VALUES (%s,%s,SHA2(%s,256),%s)",
            (user_id, username, password, role),
        )
        connection.commit()
        return user_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def update_record(record_type, user_id, values, username, password):
    table = {"students": "student", "faculty": "faculty", "admins": "admin"}[record_type]
    columns = [field[0] for field in RECORD_FIELDS[record_type]]
    if "division" in values:
        values["division"] = (values["division"] or "").upper()
        if values["division"] not in {"A", "B", "C", "D"} or values["std"] not in range(1, 11):
            raise ValueError("Choose a class from 1–10 and division A–D.")
    if not username:
        raise ValueError("Please enter a username.")
    if password and len(password) < 8:
        raise ValueError("Use a password with at least 8 characters.")
    connection = db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM login_details WHERE uname=%s AND id<>%s", (username, user_id))
        if cursor.fetchone():
            raise ValueError("That username is already in use.")
        cursor.execute(
            f"UPDATE {table} SET " + ", ".join(f"{name}=%s" for name in columns) + " WHERE id=%s",
            [values[name] for name in columns] + [user_id],
        )
        if password:
            cursor.execute(
                "UPDATE login_details SET uname=%s,password=SHA2(%s,256) WHERE id=%s",
                (username, password, user_id),
            )
        else:
            cursor.execute("UPDATE login_details SET uname=%s WHERE id=%s", (username, user_id))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
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
    searches = {
        "students": ("id", "first_name", "last_name", "std", "division"),
        "faculty": ("id", "first_name", "last_name", "sub", "email"),
        "admins": ("id", "name", "phoneno"),
    }
    search_text = request.args.get("q", "").strip()
    where = ""
    params = []
    if search_text:
        where = " WHERE " + " OR ".join(f"{column} LIKE %s" for column in searches[record_type])
        params = [f"%{search_text}%"] * len(searches[record_type])
    if record_type == "students":
        rows = query(
            "SELECT id, first_name, middle_name, last_name, std, division, roll_no "
            "FROM student" + where + " ORDER BY std, division, roll_no", params
        )
        title = "Students"
    elif record_type == "faculty":
        rows = query(
            "SELECT id, first_name, middle_name, last_name, sub AS subject, email "
            "FROM faculty" + where + " ORDER BY first_name, last_name", params
        )
        title = "Faculty"
    else:
        rows = query("SELECT id, name, age, sex, phoneno FROM admin" + where + " ORDER BY name", params)
        title = "Administrators"
    can_manage = (record_type in {"students", "faculty"} and role in {"admin", "superadmin"}) or (record_type == "admins" and role == "superadmin")
    return render_template("records.html", rows=rows, record_type=record_type, title=title,
                           can_manage=can_manage, search_text=search_text)


@app.route("/manage/<record_type>/new", methods=["GET", "POST"])
@roles_required("admin", "superadmin")
def create_record_page(record_type):
    role = current_user()["typeofuser"]
    if record_type not in RECORD_FIELDS or (record_type == "admins" and role != "superadmin"):
        abort(404)
    fields = RECORD_FIELDS[record_type]
    if request.method == "POST":
        try:
            values = clean_form(fields)
            user_id = create_record(record_type, values,
                                    request.form.get("username", "").strip(),
                                    request.form.get("password", ""))
            flash(f"Record created successfully. New account ID: {user_id}.", "success")
            return redirect(url_for("records", record_type=record_type))
        except ValueError as exc:
            flash(str(exc), "error")
        except mysql.connector.Error:
            app.logger.exception("Could not create %s record", record_type)
            flash("We could not save this record. Check required fields and any existing username, then try again.", "error")
    return render_template("record_form.html", record_type=record_type, fields=fields,
                           record=None, account=None, is_new=True,
                           title={"students":"Add student", "faculty":"Add faculty", "admins":"Add administrator"}[record_type])


@app.route("/manage/<record_type>/<user_id>/edit", methods=["GET", "POST"])
@roles_required("admin", "superadmin")
def edit_record_page(record_type, user_id):
    role = current_user()["typeofuser"]
    if record_type not in RECORD_FIELDS or (record_type == "admins" and role != "superadmin"):
        abort(404)
    table = {"students":"student", "faculty":"faculty", "admins":"admin"}[record_type]
    record = query(f"SELECT * FROM {table} WHERE id=%s", (user_id,), one=True)
    account = query("SELECT uname FROM login_details WHERE id=%s", (user_id,), one=True)
    if not record or not account:
        abort(404)
    fields = RECORD_FIELDS[record_type]
    if request.method == "POST":
        try:
            values = clean_form(fields)
            update_record(record_type, user_id, values,
                          request.form.get("username", "").strip(),
                          request.form.get("password", ""))
            flash("Record updated successfully.", "success")
            return redirect(url_for("records", record_type=record_type))
        except ValueError as exc:
            flash(str(exc), "error")
        except mysql.connector.Error:
            app.logger.exception("Could not update %s record", record_type)
            flash("We could not update this record. Check the values and try again.", "error")
    return render_template("record_form.html", record_type=record_type, fields=fields,
                           record=record, account=account, is_new=False,
                           title={"students":"Edit student", "faculty":"Edit faculty", "admins":"Edit administrator"}[record_type])


@app.post("/manage/<record_type>/<user_id>/delete")
@roles_required("admin", "superadmin")
def delete_record_page(record_type, user_id):
    role = current_user()["typeofuser"]
    if record_type not in RECORD_FIELDS or (record_type == "admins" and role != "superadmin"):
        abort(404)
    table = {"students":"student", "faculty":"faculty", "admins":"admin"}[record_type]
    try:
        execute(f"DELETE FROM {table} WHERE id=%s", (user_id,))
        flash("Record deleted.", "success")
    except mysql.connector.Error:
        app.logger.exception("Could not delete %s record", record_type)
        flash("This record could not be deleted. Check whether another record depends on it.", "error")
    return redirect(url_for("records", record_type=record_type))


@app.route("/fees/manage", methods=["GET", "POST"])
@roles_required("admin", "superadmin")
def fees_manage():
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "plan":
                year = int(request.form.get("year", ""))
                monthly = int(request.form.get("monthly", ""))
                yearly = int(request.form.get("yearly", ""))
                if not 2000 <= year <= 2155 or monthly < 0 or yearly < 0:
                    raise ValueError("Enter a valid year and non-negative fee amounts.")
                connection = db_connection()
                try:
                    cursor = connection.cursor()
                    cursor.execute(
                        "INSERT INTO store_fees (year_, monthly, yearly) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE monthly=VALUES(monthly), yearly=VALUES(yearly)",
                        (year, monthly, yearly),
                    )
                    connection.commit()
                finally:
                    connection.close()
                flash(f"Fee plan for {year} saved.", "success")
            elif action == "payment":
                student_id = request.form.get("student_id", "")
                year = int(request.form.get("year", ""))
                months = ["jan", "feb", "mar", "april", "may", "june", "july", "aug", "sept", "oct", "nov", "dece"]
                full_year = "Y" if request.form.get("fullyearpaid") == "Y" else "N"
                chosen = {month: ("Y" if month in request.form.getlist("months") else "N") for month in months}
                connection = db_connection()
                try:
                    cursor = connection.cursor()
                    cursor.execute("SELECT id FROM student WHERE id=%s", (student_id,))
                    if not cursor.fetchone():
                        raise ValueError("Choose an existing student.")
                    cursor.execute("SELECT year_ FROM store_fees WHERE year_=%s", (year,))
                    if not cursor.fetchone():
                        raise ValueError("Create the fee plan for this year first.")
                    cursor.execute("SELECT id FROM fees WHERE id=%s AND year_=%s", (student_id, year))
                    if cursor.fetchone():
                        cursor.execute(
                            "UPDATE fees SET fullyearpaid=%s," + ",".join(f"{month}=%s" for month in months) + " WHERE id=%s AND year_=%s",
                            [full_year] + [chosen[m] for m in months] + [student_id, year],
                        )
                    else:
                        cursor.execute("INSERT INTO fees (id, fullyearpaid, year_) VALUES (%s,%s,%s)", (student_id, full_year, year))
                        cursor.execute(
                            "UPDATE fees SET " + ",".join(f"{month}=%s" for month in months) + " WHERE id=%s AND year_=%s",
                            [chosen[m] for m in months] + [student_id, year],
                        )
                    connection.commit()
                finally:
                    connection.close()
                flash("Fee payment record saved.", "success")
            else:
                raise ValueError("Choose an action and try again.")
        except ValueError as exc:
            flash(str(exc), "error")
        except mysql.connector.Error:
            app.logger.exception("Could not save fee information")
            flash("Fee information could not be saved. Check that the fee year exists.", "error")
        return redirect(url_for("fees_manage"))
    plans = query("SELECT year_, monthly, yearly FROM store_fees ORDER BY year_ DESC")
    students = query("SELECT id, CONCAT_WS(' ',first_name,middle_name,last_name) AS name FROM student ORDER BY first_name,last_name")
    fee_rows = query(
        "SELECT f.id, CONCAT_WS(' ',s.first_name,s.middle_name,s.last_name) AS student, f.year_, "
        "f.fullyearpaid, f.jan, f.feb, f.mar, f.april, f.may, f.june, f.july, f.aug, f.sept, f.oct, f.nov, f.dece "
        "FROM fees f JOIN student s ON s.id=f.id ORDER BY f.year_ DESC, s.first_name, s.last_name"
    )
    selected_student = request.args.get("student_id", "")
    selected_year = request.args.get("year", "")
    saved_payment = query("SELECT * FROM fees WHERE id=%s AND year_=%s", (selected_student, selected_year), one=True) if selected_student and selected_year else None
    return render_template("fees_manage.html", plans=plans, students=students, fee_rows=fee_rows,
                           selected_student=selected_student, selected_year=selected_year,
                           saved_payment=saved_payment)


@app.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(password) < 8:
            flash("Use a password with at least 8 characters.", "error")
        elif password != confirm:
            flash("The passwords do not match.", "error")
        else:
            execute("UPDATE login_details SET password=SHA2(%s,256) WHERE id=%s", (password, current_user()["id"]))
            flash("Your password has been updated.", "success")
            return redirect(url_for("dashboard"))
    return render_template("change_password.html")


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
