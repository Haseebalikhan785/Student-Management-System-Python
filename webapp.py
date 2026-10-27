"""Browser-based edition of the University Management System.

The original Tkinter desktop application remains available through ``python app.py``.
Run this web edition with ``flask --app webapp run`` during development or Gunicorn
in a hosted environment.
"""

from __future__ import annotations

import os
import hashlib
import hmac
from threading import Lock
from datetime import date, datetime, timedelta
from functools import wraps

import mysql.connector
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for, send_from_directory
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename


app = Flask(__name__)
secret_key = os.environ.get("SECRET_KEY")
if not secret_key and os.environ.get("RENDER"):
    raise RuntimeError("Set a unique SECRET_KEY in the hosting dashboard before deploying.")
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads", "assignments")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config.update(
    SECRET_KEY=secret_key or "local-development-only-change-before-hosting",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "true" if os.environ.get("RENDER") else "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    UPLOAD_FOLDER=UPLOAD_FOLDER,
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
                cursor.execute("""CREATE TABLE IF NOT EXISTS departments (
        department_id VARCHAR(12) NOT NULL PRIMARY KEY,
        name VARCHAR(100) NOT NULL UNIQUE,
        description TEXT,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS courses (
        course_code VARCHAR(20) NOT NULL PRIMARY KEY,
        department_id VARCHAR(12) NOT NULL,
        title VARCHAR(120) NOT NULL,
        credits DECIMAL(3,1) NOT NULL DEFAULT 3.0,
        semester TINYINT UNSIGNED NOT NULL,
        description TEXT,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_courses_department FOREIGN KEY (department_id) REFERENCES departments(department_id)
            ON DELETE RESTRICT ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS faculty_courses (
        faculty_id VARCHAR(8) NOT NULL,
        course_code VARCHAR(20) NOT NULL,
        academic_year VARCHAR(9) NOT NULL,
        semester TINYINT UNSIGNED NOT NULL,
        assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (faculty_id, course_code, academic_year, semester),
        CONSTRAINT fk_faculty_courses_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(id)
            ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT fk_faculty_courses_course FOREIGN KEY (course_code) REFERENCES courses(course_code)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS course_enrollments (
        enrollment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        student_id VARCHAR(8) NOT NULL,
        course_code VARCHAR(20) NOT NULL,
        academic_year VARCHAR(9) NOT NULL,
        semester TINYINT UNSIGNED NOT NULL,
        status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
        requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        reviewed_at TIMESTAMP NULL DEFAULT NULL,
        UNIQUE KEY uq_student_course_term (student_id, course_code, academic_year, semester),
        KEY ix_enrollment_status (status, academic_year, semester),
        CONSTRAINT fk_enrollment_student FOREIGN KEY (student_id) REFERENCES student(id)
            ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT fk_enrollment_course FOREIGN KEY (course_code) REFERENCES courses(course_code)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS course_attendance (
        course_code VARCHAR(20) NOT NULL,
        student_id VARCHAR(8) NOT NULL,
        academic_year VARCHAR(9) NOT NULL,
        semester TINYINT UNSIGNED NOT NULL,
        attendance_date DATE NOT NULL,
        attended ENUM('Y','N') NOT NULL,
        marked_by VARCHAR(8) NOT NULL,
        PRIMARY KEY (course_code, student_id, academic_year, semester, attendance_date),
        KEY ix_course_attendance_date (attendance_date, course_code),
        CONSTRAINT fk_course_attendance_course FOREIGN KEY (course_code) REFERENCES courses(course_code)
            ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT fk_course_attendance_student FOREIGN KEY (student_id) REFERENCES student(id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS course_grades (
        enrollment_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        marks DECIMAL(6,2) NOT NULL DEFAULT 0,
        maximum_marks DECIMAL(6,2) NOT NULL DEFAULT 100,
        letter_grade VARCHAR(4) NOT NULL DEFAULT 'IP',
        feedback TEXT,
        updated_by VARCHAR(8) NOT NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_course_grade_enrollment FOREIGN KEY (enrollment_id) REFERENCES course_enrollments(enrollment_id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS course_schedule (
        schedule_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        faculty_id VARCHAR(8) NOT NULL,
        course_code VARCHAR(20) NOT NULL,
        academic_year VARCHAR(9) NOT NULL,
        semester TINYINT UNSIGNED NOT NULL,
        weekday TINYINT UNSIGNED NOT NULL,
        starts_at TIME NOT NULL,
        ends_at TIME NOT NULL,
        room VARCHAR(32) NOT NULL,
        KEY ix_schedule_term (academic_year, semester, weekday, starts_at),
        CONSTRAINT fk_schedule_assignment FOREIGN KEY (faculty_id, course_code, academic_year, semester)
            REFERENCES faculty_courses(faculty_id, course_code, academic_year, semester)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS announcements (
        announcement_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(160) NOT NULL,
        body TEXT NOT NULL,
        audience ENUM('all','student','faculty','staff') NOT NULL DEFAULT 'all',
        created_by VARCHAR(12) NOT NULL,
        published BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY ix_announcement_audience (published, audience, created_at)
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS assignments (
        assignment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        course_code VARCHAR(10) NOT NULL,
        faculty_id VARCHAR(8) NOT NULL,
        title VARCHAR(180) NOT NULL,
        description TEXT NOT NULL,
        due_date DATETIME NOT NULL,
        max_marks DECIMAL(5,2) NOT NULL DEFAULT 100.00,
        allowed_extensions VARCHAR(100) NOT NULL DEFAULT 'pdf,docx,zip,txt,py',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_assign_course FOREIGN KEY (course_code) REFERENCES courses(course_code)
            ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT fk_assign_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS assignment_submissions (
        submission_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        assignment_id BIGINT UNSIGNED NOT NULL,
        student_id VARCHAR(8) NOT NULL,
        file_path VARCHAR(255) NOT NULL,
        original_filename VARCHAR(255) NOT NULL,
        student_notes TEXT,
        submitted_at DATETIME NOT NULL,
        status ENUM('on_time', 'late') NOT NULL DEFAULT 'on_time',
        marks_awarded DECIMAL(5,2) DEFAULT NULL,
        feedback TEXT DEFAULT NULL,
        graded_by VARCHAR(8) DEFAULT NULL,
        graded_at DATETIME DEFAULT NULL,
        UNIQUE KEY uq_assign_student (assignment_id, student_id),
        CONSTRAINT fk_sub_assign FOREIGN KEY (assignment_id) REFERENCES assignments(assignment_id)
            ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT fk_sub_student FOREIGN KEY (student_id) REFERENCES student(id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS quizzes (
        quiz_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        course_code VARCHAR(10) NOT NULL,
        faculty_id VARCHAR(8) NOT NULL,
        title VARCHAR(180) NOT NULL,
        description TEXT NOT NULL,
        duration_minutes INT NOT NULL DEFAULT 30,
        passing_marks DECIMAL(5,2) NOT NULL DEFAULT 50.00,
        due_date DATETIME NOT NULL,
        published BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_quiz_course FOREIGN KEY (course_code) REFERENCES courses(course_code)
            ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT fk_quiz_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS quiz_questions (
        question_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        quiz_id BIGINT UNSIGNED NOT NULL,
        question_text TEXT NOT NULL,
        option_a VARCHAR(255) NOT NULL,
        option_b VARCHAR(255) NOT NULL,
        option_c VARCHAR(255) NOT NULL,
        option_d VARCHAR(255) NOT NULL,
        correct_option CHAR(1) NOT NULL,
        marks DECIMAL(4,2) NOT NULL DEFAULT 1.00,
        explanation TEXT DEFAULT NULL,
        order_num INT NOT NULL DEFAULT 1,
        CONSTRAINT fk_q_quiz FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS quiz_attempts (
        attempt_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        quiz_id BIGINT UNSIGNED NOT NULL,
        student_id VARCHAR(8) NOT NULL,
        started_at DATETIME NOT NULL,
        submitted_at DATETIME DEFAULT NULL,
        total_score DECIMAL(5,2) DEFAULT 0.00,
        max_possible_score DECIMAL(5,2) DEFAULT 0.00,
        status ENUM('in_progress', 'completed') NOT NULL DEFAULT 'in_progress',
        UNIQUE KEY uq_quiz_attempt (quiz_id, student_id),
        CONSTRAINT fk_att_quiz FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id)
            ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT fk_att_student FOREIGN KEY (student_id) REFERENCES student(id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS quiz_answers (
        answer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        attempt_id BIGINT UNSIGNED NOT NULL,
        question_id BIGINT UNSIGNED NOT NULL,
        selected_option CHAR(1) DEFAULT NULL,
        is_correct BOOLEAN NOT NULL DEFAULT FALSE,
        marks_awarded DECIMAL(4,2) NOT NULL DEFAULT 0.00,
        CONSTRAINT fk_ans_attempt FOREIGN KEY (attempt_id) REFERENCES quiz_attempts(attempt_id)
            ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT fk_ans_question FOREIGN KEY (question_id) REFERENCES quiz_questions(question_id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB""")
                cursor.executemany(
                    "INSERT IGNORE INTO departments (department_id, name, description) VALUES (%s,%s,%s)",
                    [
                        ("SCI", "School of Science and Computing", "Computing, data, mathematics, and applied science."),
                        ("BUS", "School of Business", "Management, accounting, economics, and entrepreneurship."),
                        ("HUM", "School of Humanities", "Communication, languages, social inquiry, and writing."),
                        ("ENG", "School of Engineering", "Engineering fundamentals and technology practice."),
                    ],
                )
                cursor.executemany(
                    "INSERT IGNORE INTO courses (course_code, department_id, title, credits, semester, description) VALUES (%s,%s,%s,%s,%s,%s)",
                    [
                        ("CSE101", "SCI", "Programming Fundamentals", 4.0, 1, "Problem solving, programming concepts, and practical software development."),
                        ("CSE102", "SCI", "Discrete Mathematics", 4.0, 1, "Logic, sets, relations, graphs, and foundations of computing."),
                        ("CSE201", "SCI", "Data Structures", 4.0, 2, "Core data structures, algorithm analysis, and implementation."),
                        ("CSE202", "SCI", "Database Systems", 4.0, 2, "Relational data modelling, SQL, transactions, and database design."),
                        ("CSE301", "SCI", "Web Application Development", 3.0, 3, "Server-side applications, accessible interfaces, and web architecture."),
                        ("CSE302", "SCI", "Computer Networks", 3.0, 3, "Network architecture, protocols, security fundamentals, and diagnostics."),
                        ("MAT101", "SCI", "Calculus and Linear Algebra", 4.0, 1, "Differential and integral calculus with introductory linear algebra."),
                        ("MAT202", "SCI", "Probability and Statistics", 3.0, 2, "Probability, descriptive statistics, sampling, and inference."),
                        ("ENG101", "ENG", "Engineering Design Studio", 3.0, 1, "A project-based introduction to design methods and technical communication."),
                        ("BUS101", "BUS", "Principles of Management", 3.0, 1, "Organisations, leadership, planning, and responsible management."),
                        ("BUS201", "BUS", "Financial Accounting", 3.0, 2, "Financial statements, accounting cycles, and interpretation of business data."),
                        ("HUM101", "HUM", "Academic Writing and Research", 2.0, 1, "Evidence-based writing, source evaluation, and research communication."),
                    ],
                )

                # Seed sample faculty assignments and timetable if available
                cursor.execute("SELECT id FROM faculty WHERE id='FT10000'")
                if cursor.fetchone():
                    cursor.executemany(
                        "INSERT IGNORE INTO faculty_courses (faculty_id, course_code, academic_year, semester) VALUES (%s,%s,%s,%s)",
                        [
                            ("FT10000", "CSE101", "2026-27", 1),
                            ("FT10000", "HUM101", "2026-27", 1),
                            ("FT10001", "MAT101", "2026-27", 1),
                            ("FT10001", "CSE102", "2026-27", 1),
                            ("FT10007", "CSE301", "2026-27", 1),
                            ("FT10007", "CSE302", "2026-27", 1),
                            ("FT10003", "BUS101", "2026-27", 1),
                        ],
                    )
                    cursor.executemany(
                        "INSERT IGNORE INTO course_schedule (faculty_id, course_code, academic_year, semester, weekday, starts_at, ends_at, room) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        [
                            ("FT10000", "CSE101", "2026-27", 1, 0, "09:00:00", "10:30:00", "Turing Hall 101"),
                            ("FT10001", "MAT101", "2026-27", 1, 0, "11:00:00", "12:30:00", "Ramanujan 204"),
                            ("FT10000", "HUM101", "2026-27", 1, 1, "10:00:00", "11:30:00", "Aristotle 102"),
                            ("FT10000", "CSE101", "2026-27", 1, 2, "09:00:00", "10:30:00", "Lab Computing 3"),
                            ("FT10001", "CSE102", "2026-27", 1, 3, "14:00:00", "15:30:00", "Lovelace 105"),
                            ("FT10001", "MAT101", "2026-27", 1, 4, "10:00:00", "11:30:00", "Ramanujan 204"),
                        ],
                    )

                # Seed sample student enrollments, grades, and course attendance
                cursor.execute("SELECT id FROM student WHERE id='ST10000'")
                if cursor.fetchone():
                    cursor.executemany(
                        "INSERT IGNORE INTO course_enrollments (student_id, course_code, academic_year, semester, status) VALUES (%s,%s,%s,%s,%s)",
                        [
                            ("ST10000", "CSE101", "2026-27", 1, "approved"),
                            ("ST10000", "MAT101", "2026-27", 1, "approved"),
                            ("ST10000", "HUM101", "2026-27", 1, "approved"),
                            ("ST10001", "CSE101", "2026-27", 1, "approved"),
                            ("ST10001", "MAT101", "2026-27", 1, "approved"),
                            ("ST10002", "CSE101", "2026-27", 1, "pending"),
                            ("ST10003", "MAT101", "2026-27", 1, "pending"),
                        ],
                    )
                    cursor.execute(
                        "SELECT enrollment_id, student_id, course_code FROM course_enrollments WHERE status='approved'"
                    )
                    approved_rows = cursor.fetchall()
                    grade_data = {
                        ("ST10000", "CSE101"): (88.5, 100.0, "A", "Strong problem solving and structured coding skills.", "FT10000"),
                        ("ST10000", "MAT101"): (93.0, 100.0, "A", "Outstanding analytical and mathematical reasoning.", "FT10001"),
                        ("ST10000", "HUM101"): (85.0, 100.0, "B", "Clear academic writing and thoughtful research contributions.", "FT10000"),
                        ("ST10001", "CSE101"): (91.0, 100.0, "A", "Consistently high scores in laboratory programming projects.", "FT10000"),
                        ("ST10001", "MAT101"): (86.0, 100.0, "B", "Solid comprehension of linear algebra proofs.", "FT10001"),
                    }
                    for enr_id, sid, code in approved_rows:
                        if (sid, code) in grade_data:
                            m, mm, lg, fb, ub = grade_data[(sid, code)]
                            cursor.execute(
                                "INSERT IGNORE INTO course_grades (enrollment_id, marks, maximum_marks, letter_grade, feedback, updated_by) "
                                "VALUES (%s,%s,%s,%s,%s,%s)",
                                (enr_id, m, mm, lg, fb, ub),
                            )

                    for course, sids, dates in [
                        ("CSE101", ["ST10000", "ST10001"], ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]),
                        ("MAT101", ["ST10000", "ST10001"], ["2026-10-06", "2026-10-13", "2026-10-20"]),
                        ("HUM101", ["ST10000"], ["2026-10-07", "2026-10-14", "2026-10-21"]),
                    ]:
                        for d in dates:
                            for sid in sids:
                                cursor.execute(
                                    "INSERT IGNORE INTO course_attendance (course_code, student_id, academic_year, semester, attendance_date, attended, marked_by) "
                                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                    (course, sid, "2026-27", 1, d, "Y", "FT10000"),
                                )

                # Seed sample university announcements
                cursor.execute("SELECT COUNT(*) FROM announcements")
                if cursor.fetchone()[0] == 0:
                    cursor.executemany(
                        "INSERT INTO announcements (title, body, audience, created_by) VALUES (%s,%s,%s,%s)",
                        [
                            (
                                "Welcome to Autumn Semester 2026–27 Academic Session",
                                "The Office of Academic Affairs welcomes all students and faculty members to the Autumn 2026–27 session. Course enrolment confirmation, semester schedules, and academic guidelines are now available in your respective portals.",
                                "all",
                                "SA100",
                            ),
                            (
                                "Mid-Term Continuous Assessment Schedule Published",
                                "Continuous internal evaluations and mid-term assessments for undergraduate and graduate courses will begin from November 16, 2026. Hall tickets and test seat allocations will be issued online.",
                                "student",
                                "SA100",
                            ),
                            (
                                "Faculty Senate: Submission of Internal Grades & Course Plans",
                                "All department faculty are requested to update continuous assessment marks and attendance records in the gradebook portal by the end of each academic cycle.",
                                "faculty",
                                "SA100",
                            ),
                            (
                                "Annual University Innovation & Research Symposium 2026",
                                "Submissions are invited for the upcoming University Innovation Symposium. Students and faculty can register papers and projects through department research coordinators.",
                                "all",
                                "SA100",
                            ),
                        ],
                    )

                # Ensure an admin account exists
                cursor.execute("SELECT COUNT(*) FROM login_details WHERE typeofuser IN ('admin', 'superadmin')")
                if cursor.fetchone()[0] == 0:
                    cursor.execute(
                        "INSERT IGNORE INTO login_details (id, uname, password, typeofuser) VALUES (%s, %s, SHA2(%s, 256), %s)",
                        ("SA100", "superadmin", "SuperAdmin@2026", "superadmin"),
                    )
                    cursor.execute(
                        "INSERT IGNORE INTO admin (id, name, address, phoneno, age, sex) VALUES (%s,%s,%s,%s,%s,%s)",
                        ("AD1000", "Academic Registrar Office", "Central Administration Building, Campus", 9876509999, 42, "Other"),
                    )
                    cursor.execute(
                        "INSERT IGNORE INTO login_details (id, uname, password, typeofuser) VALUES (%s, %s, SHA2(%s, 256), %s)",
                        ("AD1000", "admin.office", "Admin@Office2026", "admin"),
                    )

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


def password_matches(user, password):
    stored = user["password"]
    if stored.startswith(("scrypt:", "pbkdf2:")):
        if not check_password_hash(stored, password):
            return False
        # A brief deployment may have upgraded the browser account hash. Put it
        # back into the shared desktop/web format after a successful sign-in.
        execute("UPDATE login_details SET password=SHA2(%s,256) WHERE id=%s",
                (password, user["id"]))
        return True
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(stored, digest)


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
        ("division", "Section (A-D)", "text", True), ("std", "Year of study (1-10)", "number", True),
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
    if "middle_name" in values and values["middle_name"] is None:
        values["middle_name"] = ""
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
                raise ValueError("Choose a year of study from 1–10 and a section from A–D.")
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
            raise ValueError("Choose a year of study from 1–10 and a section from A–D.")
    if "middle_name" in values and values["middle_name"] is None:
        values["middle_name"] = ""
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


def academic_period(today=None):
    """Return the current June-to-May academic year and its odd/even semester."""
    today = today or date.today()
    start_year = today.year if today.month >= 6 else today.year - 1
    academic_year = f"{start_year}-{(start_year + 1) % 100:02d}"
    semester = 1 if 6 <= today.month <= 11 else 2
    return academic_year, semester


def clean_academic_code(value, field_name, max_length):
    value = value.strip().upper()
    if not value or len(value) > max_length or not value.replace("-", "").isalnum():
        raise ValueError(f"Enter a valid {field_name} using letters, numbers, or hyphens.")
    return value


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
            "SELECT id, uname, typeofuser, password FROM login_details WHERE uname=%s",
            (username,), one=True,
        )
        if user and password_matches(user, password):
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
    academic_year, semester = academic_period()
    if role == "student":
        profile = query(
            "SELECT id, first_name, middle_name, last_name, std, division, roll_no, dob, doa, "
            "bloodgroup, sex, phoneno, address, father_name, mother_name, father_occ, mother_occ "
            "FROM student WHERE id=%s", (user["id"],), one=True,
        )
        if not profile:
            abort(404)
        course_summary = query(
            "SELECT COUNT(*) AS total, SUM(status='pending') AS pending "
            "FROM course_enrollments WHERE student_id=%s AND academic_year=%s AND semester=%s",
            (user["id"], academic_year, semester), one=True,
        )
        announcements = announcements_for_role(role, limit=3)
        return render_template("student_dashboard.html", profile=profile,
                               course_summary=course_summary, announcements=announcements,
                               academic_year=academic_year, semester=semester)
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
        course_summary = query(
            "SELECT COUNT(*) AS total FROM faculty_courses "
            "WHERE faculty_id=%s AND academic_year=%s AND semester=%s",
            (user["id"], academic_year, semester), one=True,
        )
        announcements = announcements_for_role(role, limit=3)
        return render_template("faculty_dashboard.html", profile=profile, assignment=class_assignment,
                               course_summary=course_summary, announcements=announcements,
                               academic_year=academic_year, semester=semester)
    if role in ("admin", "superadmin"):
        totals = query(
            "SELECT (SELECT COUNT(*) FROM student) AS students, "
            "(SELECT COUNT(*) FROM faculty) AS faculty, "
            "(SELECT COUNT(*) FROM admin) AS admins, "
            "(SELECT COUNT(*) FROM courses WHERE active=1) AS courses, "
            "(SELECT COUNT(*) FROM course_enrollments WHERE status='pending') AS pending_enrollments",
            one=True,
        )
        announcements = announcements_for_role(role, limit=3)
        return render_template("admin_dashboard.html", totals=totals, announcements=announcements,
                               academic_year=academic_year, semester=semester)
    abort(403)


def announcements_for_role(role, limit=20):
    if role in {"admin", "superadmin"}:
        return query(
            "SELECT a.announcement_id,a.title,a.body,a.audience,a.created_at,l.uname AS author "
            "FROM announcements a LEFT JOIN login_details l ON l.id=a.created_by "
            "WHERE a.published=1 ORDER BY a.created_at DESC LIMIT %s", (limit,),
        )
    audience = "student" if role == "student" else "faculty" if role == "faculty" else "staff"
    return query(
        "SELECT a.announcement_id, a.title, a.body, a.audience, a.created_at, "
        "l.uname AS author FROM announcements a "
        "LEFT JOIN login_details l ON l.id=a.created_by "
        "WHERE a.published=1 AND a.audience IN ('all',%s) "
        "ORDER BY a.created_at DESC LIMIT %s", (audience, limit),
    )


@app.route("/academics", methods=["GET", "POST"])
@roles_required("admin", "superadmin")
def academics():
    academic_year, semester = academic_period()
    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            if action == "department":
                department_id = clean_academic_code(request.form.get("department_id", ""), "department code", 12)
                name = request.form.get("name", "").strip()
                description = request.form.get("description", "").strip()
                if not name or len(name) > 100:
                    raise ValueError("Enter a department name of 1 to 100 characters.")
                execute("INSERT INTO departments (department_id,name,description) VALUES (%s,%s,%s)",
                        (department_id, name, description or None))
                flash("Department added.", "success")
            elif action == "toggle_department":
                execute("UPDATE departments SET active=NOT active WHERE department_id=%s",
                        (request.form.get("department_id", ""),))
                flash("Department availability updated.", "success")
            elif action == "course":
                course_code = clean_academic_code(request.form.get("course_code", ""), "course code", 20)
                department_id = request.form.get("department_id", "").strip().upper()
                title = request.form.get("title", "").strip()
                description = request.form.get("description", "").strip()
                credits = float(request.form.get("credits", "3"))
                course_semester = int(request.form.get("semester", "1"))
                if not title or len(title) > 120 or not 0 < credits <= 99 or not 1 <= course_semester <= 12:
                    raise ValueError("Enter a course title, positive credit value, and semester from 1 to 12.")
                execute(
                    "INSERT INTO courses (course_code,department_id,title,credits,semester,description) "
                    "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE department_id=VALUES(department_id), "
                    "title=VALUES(title),credits=VALUES(credits),semester=VALUES(semester),description=VALUES(description)",
                    (course_code, department_id, title, credits, course_semester, description or None),
                )
                flash(f"Course {course_code} saved.", "success")
            elif action == "assign":
                faculty_id = request.form.get("faculty_id", "").strip()
                course_code = request.form.get("course_code", "").strip().upper()
                year = request.form.get("academic_year", academic_year).strip()
                term = int(request.form.get("semester", semester))
                if len(year) != 7 or not year[:4].isdigit() or year[4] != "-" or not year[5:].isdigit() or not 1 <= term <= 12:
                    raise ValueError("Enter a valid academic year and semester.")
                execute(
                    "INSERT IGNORE INTO faculty_courses (faculty_id,course_code,academic_year,semester) VALUES (%s,%s,%s,%s)",
                    (faculty_id, course_code, year, term),
                )
                flash("Faculty course assignment saved.", "success")
            elif action == "unassign":
                execute(
                    "DELETE FROM faculty_courses WHERE faculty_id=%s AND course_code=%s AND academic_year=%s AND semester=%s",
                    (request.form.get("faculty_id", ""), request.form.get("course_code", ""),
                     request.form.get("academic_year", ""), int(request.form.get("semester", "1"))),
                )
                flash("Faculty assignment removed. Its timetable entries were removed as well.", "success")
            elif action == "toggle_course":
                execute("UPDATE courses SET active=NOT active WHERE course_code=%s",
                        (request.form.get("course_code", ""),))
                flash("Course availability updated.", "success")
            elif action == "schedule":
                faculty_id, course_code, year, term = request.form.get("assignment", "").split("|", 3)
                weekday = int(request.form.get("weekday", "0"))
                starts_at = request.form.get("starts_at", "")
                ends_at = request.form.get("ends_at", "")
                room = request.form.get("room", "").strip()
                if not 0 <= weekday <= 6 or not room or len(room) > 32 or not starts_at or not ends_at or starts_at >= ends_at:
                    raise ValueError("Enter a valid day, time range, and room.")
                conflict = query(
                    "SELECT schedule_id FROM course_schedule WHERE academic_year=%s AND semester=%s AND weekday=%s "
                    "AND starts_at < %s AND ends_at > %s AND (faculty_id=%s OR room=%s) LIMIT 1",
                    (year, term, weekday, ends_at, starts_at, faculty_id, room), one=True,
                )
                if conflict:
                    raise ValueError("That room or faculty member already has a class during this time.")
                execute(
                    "INSERT INTO course_schedule (faculty_id,course_code,academic_year,semester,weekday,starts_at,ends_at,room) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (faculty_id, course_code, year, term, weekday, starts_at, ends_at, room),
                )
                flash("Timetable entry added.", "success")
            elif action == "remove_schedule":
                execute("DELETE FROM course_schedule WHERE schedule_id=%s",
                        (request.form.get("schedule_id", ""),))
                flash("Timetable entry removed.", "success")
            else:
                raise ValueError("Choose an academic action and try again.")
        except (ValueError, TypeError) as exc:
            flash(str(exc) or "Check the values and try again.", "error")
        except mysql.connector.Error:
            app.logger.exception("Could not update academic records")
            flash("The academic record could not be saved. Check that the department, course, and faculty exist.", "error")
        return redirect(url_for("academics"))

    departments = query("SELECT department_id,name,description,active FROM departments ORDER BY name")
    courses = query(
        "SELECT c.course_code,c.title,c.credits,c.semester,c.description,c.active,d.name AS department "
        "FROM courses c JOIN departments d ON d.department_id=c.department_id ORDER BY d.name,c.course_code"
    )
    faculty = query("SELECT id,first_name,middle_name,last_name,sub FROM faculty ORDER BY first_name,last_name")
    assignments = query(
        "SELECT fc.faculty_id,fc.course_code,fc.academic_year,fc.semester,c.title,c.credits, "
        "CONCAT_WS(' ',f.first_name,f.middle_name,f.last_name) AS faculty_name, "
        "(SELECT COUNT(*) FROM course_enrollments ce WHERE ce.course_code=fc.course_code "
        "AND ce.academic_year=fc.academic_year AND ce.semester=fc.semester AND ce.status='approved') AS enrolled "
        "FROM faculty_courses fc JOIN courses c ON c.course_code=fc.course_code "
        "JOIN faculty f ON f.id=fc.faculty_id "
        "WHERE fc.academic_year=%s AND fc.semester=%s ORDER BY c.course_code,f.first_name",
        (academic_year, semester),
    )
    assignment_options = [
        {**row, "value": f"{row['faculty_id']}|{row['course_code']}|{row['academic_year']}|{row['semester']}"}
        for row in assignments
    ]
    schedules = query(
        "SELECT s.schedule_id,s.weekday,s.starts_at,s.ends_at,s.room,c.course_code,c.title, "
        "CONCAT_WS(' ',f.first_name,f.last_name) AS faculty_name "
        "FROM course_schedule s JOIN courses c ON c.course_code=s.course_code "
        "JOIN faculty f ON f.id=s.faculty_id WHERE s.academic_year=%s AND s.semester=%s "
        "ORDER BY s.weekday,s.starts_at", (academic_year, semester),
    )
    return render_template("academics.html", departments=departments, courses=courses, faculty=faculty,
                           assignments=assignments, assignment_options=assignment_options,
                           schedules=schedules, academic_year=academic_year, semester=semester)


@app.route("/student/courses", methods=["GET", "POST"])
@roles_required("student")
def student_courses():
    user = current_user()
    academic_year, semester = academic_period()
    if request.method == "POST":
        course_code = request.form.get("course_code", "").strip().upper()
        available = query(
            "SELECT c.course_code FROM courses c JOIN faculty_courses fc ON fc.course_code=c.course_code "
            "WHERE c.course_code=%s AND c.active=1 AND fc.academic_year=%s AND fc.semester=%s LIMIT 1",
            (course_code, academic_year, semester), one=True,
        )
        if not available:
            flash("This course is not currently open for registration.", "error")
        else:
            existing = query(
                "SELECT enrollment_id,status FROM course_enrollments WHERE student_id=%s AND course_code=%s "
                "AND academic_year=%s AND semester=%s", (user["id"], course_code, academic_year, semester), one=True,
            )
            if existing and existing["status"] != "rejected":
                flash("You already have a registration request for this course.", "error")
            elif existing:
                execute("UPDATE course_enrollments SET status='pending',requested_at=CURRENT_TIMESTAMP,reviewed_at=NULL WHERE enrollment_id=%s",
                        (existing["enrollment_id"],))
                flash("Your registration request has been sent for review.", "success")
            else:
                execute(
                    "INSERT INTO course_enrollments (student_id,course_code,academic_year,semester,status) VALUES (%s,%s,%s,%s,'pending')",
                    (user["id"], course_code, academic_year, semester),
                )
                flash("Your registration request has been sent for review.", "success")
        return redirect(url_for("student_courses"))
    courses = query(
        "SELECT c.course_code,c.title,c.credits,c.semester,c.description,d.name AS department, "
        "GROUP_CONCAT(DISTINCT CONCAT_WS(' ',f.first_name,f.middle_name,f.last_name) ORDER BY f.last_name SEPARATOR ', ') AS faculty_names, "
        "ce.status AS enrollment_status "
        "FROM courses c JOIN departments d ON d.department_id=c.department_id "
        "JOIN faculty_courses fc ON fc.course_code=c.course_code "
        "JOIN faculty f ON f.id=fc.faculty_id "
        "LEFT JOIN course_enrollments ce ON ce.course_code=c.course_code AND ce.student_id=%s "
        "AND ce.academic_year=fc.academic_year AND ce.semester=fc.semester "
        "WHERE c.active=1 AND fc.academic_year=%s AND fc.semester=%s "
        "GROUP BY c.course_code,c.title,c.credits,c.semester,c.description,d.name,ce.status ORDER BY d.name,c.course_code",
        (user["id"], academic_year, semester),
    )
    my_courses = query(
        "SELECT c.course_code,c.title,c.credits,ce.status,ce.enrollment_id, "
        "GROUP_CONCAT(DISTINCT CONCAT_WS(' ',f.first_name,f.last_name) ORDER BY f.last_name SEPARATOR ', ') AS faculty_names, "
        "cg.marks,cg.maximum_marks,cg.letter_grade "
        "FROM course_enrollments ce JOIN courses c ON c.course_code=ce.course_code "
        "LEFT JOIN faculty_courses fc ON fc.course_code=ce.course_code AND fc.academic_year=ce.academic_year AND fc.semester=ce.semester "
        "LEFT JOIN faculty f ON f.id=fc.faculty_id LEFT JOIN course_grades cg ON cg.enrollment_id=ce.enrollment_id "
        "WHERE ce.student_id=%s AND ce.academic_year=%s AND ce.semester=%s "
        "GROUP BY c.course_code,c.title,c.credits,ce.status,ce.enrollment_id,cg.marks,cg.maximum_marks,cg.letter_grade "
        "ORDER BY c.course_code", (user["id"], academic_year, semester),
    )
    return render_template("student_courses.html", courses=courses, my_courses=my_courses,
                           academic_year=academic_year, semester=semester)


@app.get("/faculty/courses")
@roles_required("faculty")
def faculty_courses():
    user = current_user()
    academic_year, semester = academic_period()
    courses = query(
        "SELECT c.course_code,c.title,c.credits,c.semester,c.description,fc.academic_year,fc.semester AS term, "
        "(SELECT COUNT(*) FROM course_enrollments ce WHERE ce.course_code=c.course_code "
        "AND ce.academic_year=fc.academic_year AND ce.semester=fc.semester AND ce.status='approved') AS enrolled "
        "FROM faculty_courses fc JOIN courses c ON c.course_code=fc.course_code "
        "WHERE fc.faculty_id=%s AND fc.academic_year=%s AND fc.semester=%s ORDER BY c.course_code",
        (user["id"], academic_year, semester),
    )
    return render_template("faculty_courses.html", courses=courses, academic_year=academic_year, semester=semester)


@app.route("/enrolments", methods=["GET", "POST"])
@roles_required("admin", "superadmin")
def enrolments():
    if request.method == "POST":
        enrollment_id = request.form.get("enrollment_id", "")
        status = request.form.get("status", "")
        if status not in {"approved", "rejected", "pending"}:
            flash("Choose a valid registration status.", "error")
        else:
            enrollment = query(
                "SELECT student_id,course_code,academic_year,semester FROM course_enrollments WHERE enrollment_id=%s",
                (enrollment_id,), one=True,
            )
            if not enrollment:
                flash("That registration could not be found.", "error")
            else:
                conflict = None
                if status == "approved":
                    conflict = query(
                        "SELECT target.schedule_id FROM course_schedule target "
                        "JOIN course_schedule other ON other.academic_year=target.academic_year "
                        "AND other.semester=target.semester AND other.weekday=target.weekday "
                        "AND other.course_code<>target.course_code AND other.starts_at<target.ends_at "
                        "AND other.ends_at>target.starts_at "
                        "JOIN course_enrollments enrolled ON enrolled.course_code=other.course_code "
                        "AND enrolled.student_id=%s AND enrolled.academic_year=other.academic_year "
                        "AND enrolled.semester=other.semester AND enrolled.status='approved' "
                        "WHERE target.course_code=%s AND target.academic_year=%s AND target.semester=%s LIMIT 1",
                        (enrollment["student_id"], enrollment["course_code"],
                         enrollment["academic_year"], enrollment["semester"]), one=True,
                    )
                if conflict:
                    flash("This student already has an approved course scheduled at the same time.", "error")
                else:
                    execute("UPDATE course_enrollments SET status=%s,reviewed_at=CURRENT_TIMESTAMP WHERE enrollment_id=%s",
                            (status, enrollment_id))
                    flash("Registration status updated.", "success")
        return redirect(url_for("enrolments", status=request.args.get("status", "pending")))
    selected_status = request.args.get("status", "pending")
    if selected_status not in {"pending", "approved", "rejected", "all"}:
        selected_status = "pending"
    filter_sql = "" if selected_status == "all" else "WHERE ce.status=%s"
    params = () if selected_status == "all" else (selected_status,)
    rows = query(
        "SELECT ce.enrollment_id,ce.student_id,ce.course_code,ce.academic_year,ce.semester,ce.status,ce.requested_at, "
        "CONCAT_WS(' ',s.first_name,s.middle_name,s.last_name) AS student_name, "
        "c.title,c.credits,CONCAT_WS(' ',f.first_name,f.last_name) AS faculty_name "
        "FROM course_enrollments ce JOIN student s ON s.id=ce.student_id JOIN courses c ON c.course_code=ce.course_code "
        "LEFT JOIN faculty_courses fc ON fc.course_code=ce.course_code AND fc.academic_year=ce.academic_year AND fc.semester=ce.semester "
        "LEFT JOIN faculty f ON f.id=fc.faculty_id " + filter_sql +
        " ORDER BY FIELD(ce.status,'pending','approved','rejected'),ce.requested_at DESC",
        params,
    )
    return render_template("enrolments.html", rows=rows, selected_status=selected_status)


def faculty_course_assignment(faculty_id, course_code):
    academic_year, semester = academic_period()
    assignment = query(
        "SELECT fc.faculty_id,fc.course_code,fc.academic_year,fc.semester,c.title "
        "FROM faculty_courses fc JOIN courses c ON c.course_code=fc.course_code "
        "WHERE fc.faculty_id=%s AND fc.course_code=%s AND fc.academic_year=%s AND fc.semester=%s",
        (faculty_id, course_code, academic_year, semester), one=True,
    )
    if not assignment:
        abort(403)
    return assignment


def letter_grade(marks, maximum):
    percentage = marks / maximum * 100
    if percentage >= 90:
        return "A"
    if percentage >= 80:
        return "B"
    if percentage >= 70:
        return "C"
    if percentage >= 60:
        return "D"
    return "F"


@app.route("/faculty/courses/<course_code>/attendance", methods=["GET", "POST"])
@roles_required("faculty")
def faculty_course_attendance(course_code):
    assignment = faculty_course_assignment(current_user()["id"], course_code.upper())
    selected_date = request.values.get("date", date.today().isoformat())
    try:
        date.fromisoformat(selected_date)
    except ValueError:
        abort(400, "Invalid attendance date.")
    if request.method == "POST":
        roster = query(
            "SELECT student_id FROM course_enrollments WHERE course_code=%s AND academic_year=%s "
            "AND semester=%s AND status='approved'",
            (assignment["course_code"], assignment["academic_year"], assignment["semester"]),
        )
        valid_ids = {row["student_id"] for row in roster}
        connection = db_connection()
        try:
            cursor = connection.cursor()
            for key, attended in request.form.items():
                if not key.startswith("student_") or attended not in {"Y", "N"}:
                    continue
                student_id = key.removeprefix("student_")
                if student_id not in valid_ids:
                    continue
                cursor.execute(
                    "INSERT INTO course_attendance (course_code,student_id,academic_year,semester,attendance_date,attended,marked_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE attended=VALUES(attended),marked_by=VALUES(marked_by)",
                    (assignment["course_code"], student_id, assignment["academic_year"], assignment["semester"],
                     selected_date, attended, current_user()["id"]),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        flash("Course attendance saved.", "success")
        return redirect(url_for("faculty_course_attendance", course_code=course_code, date=selected_date))
    students = query(
        "SELECT ce.student_id,CONCAT_WS(' ',s.first_name,s.middle_name,s.last_name) AS name,s.roll_no,s.division "
        "FROM course_enrollments ce JOIN student s ON s.id=ce.student_id "
        "WHERE ce.course_code=%s AND ce.academic_year=%s AND ce.semester=%s AND ce.status='approved' "
        "ORDER BY s.roll_no,s.last_name,s.first_name",
        (assignment["course_code"], assignment["academic_year"], assignment["semester"]),
    )
    attendance_rows = query(
        "SELECT student_id,attended FROM course_attendance WHERE course_code=%s AND academic_year=%s "
        "AND semester=%s AND attendance_date=%s",
        (assignment["course_code"], assignment["academic_year"], assignment["semester"], selected_date),
    )
    attendance = {row["student_id"]: row["attended"] for row in attendance_rows}
    return render_template("faculty_course_attendance.html", assignment=assignment,
                           students=students, attendance=attendance, selected_date=selected_date)


@app.route("/faculty/courses/<course_code>/grades", methods=["GET", "POST"])
@roles_required("faculty")
def faculty_course_grades(course_code):
    assignment = faculty_course_assignment(current_user()["id"], course_code.upper())
    roster = query(
        "SELECT ce.enrollment_id,ce.student_id,CONCAT_WS(' ',s.first_name,s.middle_name,s.last_name) AS name,s.roll_no "
        "FROM course_enrollments ce JOIN student s ON s.id=ce.student_id "
        "WHERE ce.course_code=%s AND ce.academic_year=%s AND ce.semester=%s AND ce.status='approved' "
        "ORDER BY s.roll_no,s.last_name,s.first_name",
        (assignment["course_code"], assignment["academic_year"], assignment["semester"]),
    )
    if request.method == "POST":
        connection = db_connection()
        try:
            cursor = connection.cursor()
            for student in roster:
                enrollment_id = str(student["enrollment_id"])
                raw_marks = request.form.get(f"marks_{enrollment_id}", "").strip()
                raw_maximum = request.form.get(f"maximum_{enrollment_id}", "100").strip()
                feedback = request.form.get(f"feedback_{enrollment_id}", "").strip()[:1000]
                if not raw_marks:
                    continue
                try:
                    marks, maximum = float(raw_marks), float(raw_maximum)
                except ValueError as exc:
                    raise ValueError("Enter numeric marks and maximum marks for each student.") from exc
                if maximum <= 0 or marks < 0 or marks > maximum or maximum > 9999:
                    raise ValueError("Marks must be between zero and the maximum marks.")
                cursor.execute(
                    "INSERT INTO course_grades (enrollment_id,marks,maximum_marks,letter_grade,feedback,updated_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE marks=VALUES(marks), "
                    "maximum_marks=VALUES(maximum_marks),letter_grade=VALUES(letter_grade),feedback=VALUES(feedback),updated_by=VALUES(updated_by)",
                    (student["enrollment_id"], marks, maximum, letter_grade(marks, maximum), feedback or None, current_user()["id"]),
                )
            connection.commit()
            flash("Gradebook saved.", "success")
        except ValueError as exc:
            connection.rollback()
            flash(str(exc), "error")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return redirect(url_for("faculty_course_grades", course_code=course_code))
    grades = query(
        "SELECT cg.enrollment_id,cg.marks,cg.maximum_marks,cg.letter_grade,cg.feedback "
        "FROM course_grades cg JOIN course_enrollments ce ON ce.enrollment_id=cg.enrollment_id "
        "WHERE ce.course_code=%s AND ce.academic_year=%s AND ce.semester=%s",
        (assignment["course_code"], assignment["academic_year"], assignment["semester"]),
    )
    grade_by_enrollment = {row["enrollment_id"]: row for row in grades}
    return render_template("faculty_course_grades.html", assignment=assignment, roster=roster,
                           grade_by_enrollment=grade_by_enrollment)


@app.get("/student/transcript")
@roles_required("student")
def student_transcript():
    rows = query(
        "SELECT ce.academic_year,ce.semester,c.course_code,c.title,c.credits,cg.marks,cg.maximum_marks, "
        "cg.letter_grade,cg.feedback,(SELECT COUNT(*) FROM course_attendance ca WHERE ca.student_id=ce.student_id "
        "AND ca.course_code=ce.course_code AND ca.academic_year=ce.academic_year AND ca.semester=ce.semester AND ca.attended='Y') AS attended, "
        "(SELECT COUNT(*) FROM course_attendance ca WHERE ca.student_id=ce.student_id "
        "AND ca.course_code=ce.course_code AND ca.academic_year=ce.academic_year AND ca.semester=ce.semester) AS meetings "
        "FROM course_enrollments ce JOIN courses c ON c.course_code=ce.course_code "
        "LEFT JOIN course_grades cg ON cg.enrollment_id=ce.enrollment_id "
        "WHERE ce.student_id=%s AND ce.status='approved' "
        "ORDER BY ce.academic_year DESC,ce.semester DESC,c.course_code", (current_user()["id"],),
    )
    total_credits = sum(float(r["credits"]) for r in rows)
    points = {"O": 10.0, "A": 9.0, "B": 8.0, "C": 7.0, "D": 6.0, "F": 0.0}
    graded_credits = sum(float(r["credits"]) for r in rows if r.get("letter_grade") in points)
    earned_credits = sum(float(r["credits"]) for r in rows if r.get("letter_grade") in points and points[r["letter_grade"]] > 0)
    total_points = sum(float(r["credits"]) * points[r["letter_grade"]] for r in rows if r.get("letter_grade") in points)
    cgpa = round(total_points / graded_credits, 2) if graded_credits > 0 else None
    return render_template(
        "student_transcript.html",
        rows=rows,
        total_credits=total_credits,
        earned_credits=earned_credits,
        cgpa=cgpa,
    )


@app.get("/schedule")
@login_required
def schedule():
    user = current_user()
    academic_year, semester = academic_period()
    sql = (
        "SELECT s.weekday,s.starts_at,s.ends_at,s.room,c.course_code,c.title,c.credits, "
        "CONCAT_WS(' ',f.first_name,f.last_name) AS faculty_name "
        "FROM course_schedule s JOIN courses c ON c.course_code=s.course_code "
        "JOIN faculty f ON f.id=s.faculty_id WHERE s.academic_year=%s AND s.semester=%s"
    )
    params = [academic_year, semester]
    if user["typeofuser"] == "student":
        sql += " AND EXISTS (SELECT 1 FROM course_enrollments ce WHERE ce.student_id=%s AND ce.course_code=s.course_code AND ce.academic_year=s.academic_year AND ce.semester=s.semester AND ce.status='approved')"
        params.append(user["id"])
    elif user["typeofuser"] == "faculty":
        sql += " AND s.faculty_id=%s"
        params.append(user["id"])
    rows = query(sql + " ORDER BY s.weekday,s.starts_at,c.course_code", tuple(params))
    return render_template("schedule.html", rows=rows, academic_year=academic_year, semester=semester)


@app.route("/announcements", methods=["GET", "POST"])
@login_required
def announcements():
    role = current_user()["typeofuser"]
    can_publish = role in {"admin", "superadmin"}
    if request.method == "POST":
        if not can_publish:
            abort(403)
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        audience = request.form.get("audience", "all")
        if not title or len(title) > 160 or not body or len(body) > 10000 or audience not in {"all", "student", "faculty", "staff"}:
            flash("Enter a title, message, and valid audience.", "error")
        else:
            execute("INSERT INTO announcements (title,body,audience,created_by) VALUES (%s,%s,%s,%s)",
                    (title, body, audience, current_user()["id"]))
            flash("Notice published.", "success")
        return redirect(url_for("announcements"))
    rows = announcements_for_role(role, limit=100)
    return render_template("announcements.html", rows=rows, can_publish=can_publish)


@app.post("/announcements/<int:announcement_id>/delete")
@roles_required("admin", "superadmin")
def delete_announcement(announcement_id):
    execute("DELETE FROM announcements WHERE announcement_id=%s", (announcement_id,))
    flash("Notice removed.", "success")
    return redirect(url_for("announcements"))


@app.get("/reports")
@roles_required("admin", "superadmin")
def reports():
    totals = query(
        "SELECT (SELECT COUNT(*) FROM student) AS students,(SELECT COUNT(*) FROM faculty) AS faculty, "
        "(SELECT COUNT(*) FROM departments WHERE active=1) AS departments,(SELECT COUNT(*) FROM courses WHERE active=1) AS courses, "
        "(SELECT COUNT(*) FROM course_enrollments WHERE status='pending') AS pending, "
        "(SELECT COUNT(*) FROM course_enrollments WHERE status='approved') AS active_enrollments, "
        "(SELECT COUNT(*) FROM attendance WHERE attended='Y') AS school_attendance_days, "
        "(SELECT COUNT(*) FROM course_attendance WHERE attended='Y') AS course_attendance", one=True,
    )
    enrollment_rows = query(
        "SELECT c.course_code,c.title,fc.academic_year,fc.semester,SUM(ce.status='approved') AS enrolled, "
        "SUM(ce.status='pending') AS pending FROM faculty_courses fc JOIN courses c ON c.course_code=fc.course_code "
        "LEFT JOIN course_enrollments ce ON ce.course_code=fc.course_code AND ce.academic_year=fc.academic_year AND ce.semester=fc.semester "
        "GROUP BY c.course_code,c.title,fc.academic_year,fc.semester "
        "ORDER BY fc.academic_year DESC,fc.semester DESC,c.course_code LIMIT 100"
    )
    attendance_rows = query(
        "SELECT attendance_date,COUNT(*) AS marked,SUM(attended='Y') AS present FROM course_attendance "
        "GROUP BY attendance_date ORDER BY attendance_date DESC LIMIT 14"
    )
    return render_template("reports.html", totals=totals, enrollment_rows=enrollment_rows,
                           attendance_rows=attendance_rows)


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
        if role == "faculty":
            assignment = query("SELECT std,divison FROM div_details WHERE faculty_id=%s", (current_user()["id"],), one=True)
            access = [
                "EXISTS (SELECT 1 FROM course_enrollments ce JOIN faculty_courses fc "
                "ON fc.course_code=ce.course_code AND fc.academic_year=ce.academic_year AND fc.semester=ce.semester "
                "WHERE ce.student_id=student.id AND ce.status='approved' AND fc.faculty_id=%s)"
            ]
            access_params = [current_user()["id"]]
            if assignment:
                access.append("(student.std=%s AND student.division=%s)")
                access_params.extend([assignment["std"], assignment["divison"]])
            student_where = " WHERE (" + " OR ".join(access) + ")"
            student_params = access_params
            if search_text:
                student_where += " AND (" + " OR ".join(f"{column} LIKE %s" for column in searches[record_type]) + ")"
                student_params += [f"%{search_text}%"] * len(searches[record_type])
            rows = query(
                "SELECT id, first_name, middle_name, last_name, std AS year_of_study, division AS section, "
                "roll_no AS roll_number FROM student" +
                student_where + " ORDER BY std, division, roll_no", student_params,
            )
        else:
            rows = query(
                "SELECT id, first_name, middle_name, last_name, std AS year_of_study, division AS section, "
                "roll_no AS roll_number "
                "FROM student" + where + " ORDER BY std, division, roll_no", params
            )
        title = "Students"
    elif record_type == "faculty":
        rows = query(
            "SELECT id, first_name, middle_name, last_name, sub AS academic_discipline, email "
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
    if record_type == "admins":
        record = query("SELECT id, NAME AS name, address, phoneno, age, sex FROM admin WHERE id=%s",
                       (user_id,), one=True)
    else:
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
            execute("UPDATE login_details SET password=SHA2(%s,256) WHERE id=%s",
                    (password, current_user()["id"]))
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
            abort(400, "Choose a valid year of study.")
        division = request.form.get("division", "")
        if standard not in range(1, 11) or division not in {"A", "B", "C", "D"}:
            abort(400, "Choose a valid year of study and section.")
        existing = query("SELECT faculty_id FROM div_details WHERE faculty_id=%s", (faculty_id,), one=True)
        if existing:
            execute("UPDATE div_details SET std=%s, divison=%s WHERE faculty_id=%s", (standard, division, faculty_id))
        else:
            execute("INSERT INTO div_details (std, divison, faculty_id) VALUES (%s,%s,%s)", (standard, division, faculty_id))
        flash("Your year adviser assignment was saved.", "success")
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
            abort(403, "A year adviser assignment is required for this attendance register.")
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


# ==========================================
# ASSIGNMENTS & HOMEWORK ENGINE
# ==========================================

@app.get("/student/assignments")
@roles_required("student")
def student_assignments_list():
    academic_year, _ = academic_period()
    student_id = current_user()["id"]
    assignments = query(
        "SELECT a.assignment_id, a.course_code, c.title AS course_title, a.title, a.description, "
        "a.due_date, a.max_marks, a.allowed_extensions, "
        "sub.submission_id, sub.submitted_at, sub.status AS sub_status, sub.marks_awarded, sub.feedback, "
        "(a.due_date < NOW()) AS is_past_due "
        "FROM assignments a "
        "JOIN courses c ON a.course_code = c.course_code "
        "JOIN course_enrollments ce ON a.course_code = ce.course_code "
        "LEFT JOIN assignment_submissions sub ON a.assignment_id = sub.assignment_id AND sub.student_id = %s "
        "WHERE ce.student_id = %s AND ce.status = 'approved' "
        "ORDER BY a.due_date ASC",
        (student_id, student_id)
    )
    return render_template("student_assignments.html", assignments=assignments, academic_year=academic_year)


@app.route("/student/assignments/<int:assignment_id>/submit", methods=["GET", "POST"])
@roles_required("student")
def student_assignment_submit(assignment_id):
    student_id = current_user()["id"]
    assignment = query(
        "SELECT a.*, c.title AS course_title "
        "FROM assignments a "
        "JOIN courses c ON a.course_code = c.course_code "
        "JOIN course_enrollments ce ON a.course_code = ce.course_code "
        "WHERE a.assignment_id = %s AND ce.student_id = %s AND ce.status = 'approved'",
        (assignment_id, student_id),
        one=True
    )
    if not assignment:
        abort(404)

    submission = query(
        "SELECT * FROM assignment_submissions WHERE assignment_id = %s AND student_id = %s",
        (assignment_id, student_id),
        one=True
    )

    if request.method == "POST":
        if "submission_file" not in request.files:
            flash("Please choose a file to upload.", "error")
            return redirect(request.url)
        file = request.files["submission_file"]
        if not file or file.filename == "":
            flash("No file was selected.", "error")
            return redirect(request.url)

        filename = secure_filename(file.filename)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        allowed = [x.strip().lower() for x in assignment["allowed_extensions"].split(",") if x.strip()]
        if ext not in allowed:
            flash(f"Invalid file extension '.{ext}'. Allowed types: {assignment['allowed_extensions']}", "error")
            return redirect(request.url)

        unique_name = f"assign_{assignment_id}_{student_id}_{int(datetime.now().timestamp())}.{ext}"
        stored_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
        file.save(stored_path)

        now = datetime.now()
        sub_status = "late" if now > assignment["due_date"] else "on_time"
        notes = request.form.get("student_notes", "").strip()

        connection = db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO assignment_submissions (assignment_id, student_id, file_path, original_filename, student_notes, submitted_at, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE file_path=VALUES(file_path), original_filename=VALUES(original_filename), student_notes=VALUES(student_notes), submitted_at=VALUES(submitted_at), status=VALUES(status)",
                (assignment_id, student_id, unique_name, filename, notes, now, sub_status)
            )
            connection.commit()
            flash("Assignment submitted successfully!", "success")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return redirect(url_for("student_assignments_list"))

    return render_template("student_assignment_submit.html", assignment=assignment, submission=submission)


@app.get("/faculty/assignments")
@roles_required("faculty")
def faculty_assignments_list():
    academic_year, _ = academic_period()
    faculty_id = current_user()["id"]
    assignments = query(
        "SELECT a.assignment_id, a.course_code, c.title AS course_title, a.title, a.description, "
        "a.due_date, a.max_marks, "
        "COUNT(DISTINCT sub.submission_id) AS submission_count, "
        "COUNT(DISTINCT CASE WHEN sub.marks_awarded IS NOT NULL THEN sub.submission_id END) AS graded_count, "
        "(SELECT COUNT(*) FROM course_enrollments ce WHERE ce.course_code = a.course_code AND ce.status = 'approved') AS enrolled_count "
        "FROM assignments a "
        "JOIN courses c ON a.course_code = c.course_code "
        "LEFT JOIN assignment_submissions sub ON a.assignment_id = sub.assignment_id "
        "WHERE a.faculty_id = %s "
        "GROUP BY a.assignment_id, a.course_code, c.title, a.title, a.description, a.due_date, a.max_marks "
        "ORDER BY a.created_at DESC",
        (faculty_id,)
    )
    return render_template("faculty_assignments.html", assignments=assignments, academic_year=academic_year)


@app.route("/faculty/assignments/new", methods=["GET", "POST"])
@roles_required("faculty")
def faculty_assignment_create():
    academic_year, semester = academic_period()
    faculty_id = current_user()["id"]
    courses = query(
        "SELECT fc.course_code, c.title "
        "FROM faculty_courses fc "
        "JOIN courses c ON fc.course_code = c.course_code "
        "WHERE fc.faculty_id = %s AND fc.academic_year = %s AND fc.semester = %s",
        (faculty_id, academic_year, semester)
    )

    if request.method == "POST":
        course_code = request.form.get("course_code", "").strip()
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        due_date_raw = request.form.get("due_date", "").strip()
        max_marks = float(request.form.get("max_marks", 100))
        allowed_extensions = request.form.get("allowed_extensions", "pdf,docx,zip,txt,py").strip()

        if not course_code or not title or not description or not due_date_raw:
            flash("All required fields must be filled.", "error")
            return redirect(request.url)

        try:
            due_date = datetime.strptime(due_date_raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash("Invalid date format. Please use the calendar selector.", "error")
            return redirect(request.url)

        connection = db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO assignments (course_code, faculty_id, title, description, due_date, max_marks, allowed_extensions) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (course_code, faculty_id, title, description, due_date, max_marks, allowed_extensions)
            )
            connection.commit()
            flash("Assignment published successfully!", "success")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return redirect(url_for("faculty_assignments_list"))

    return render_template("faculty_assignment_form.html", courses=courses)


@app.get("/faculty/assignments/<int:assignment_id>/submissions")
@roles_required("faculty")
def faculty_assignment_submissions(assignment_id):
    faculty_id = current_user()["id"]
    assignment = query(
        "SELECT a.*, c.title AS course_title "
        "FROM assignments a "
        "JOIN courses c ON a.course_code = c.course_code "
        "WHERE a.assignment_id = %s AND a.faculty_id = %s",
        (assignment_id, faculty_id),
        one=True
    )
    if not assignment:
        abort(404)

    submissions = query(
        "SELECT s.id AS student_id, s.first_name, s.last_name, s.roll_no, "
        "sub.submission_id, sub.original_filename, sub.submitted_at, sub.status, "
        "sub.marks_awarded, sub.feedback, sub.student_notes "
        "FROM course_enrollments ce "
        "JOIN student s ON ce.student_id = s.id "
        "LEFT JOIN assignment_submissions sub ON ce.student_id = sub.student_id AND sub.assignment_id = %s "
        "WHERE ce.course_code = %s AND ce.status = 'approved' "
        "ORDER BY s.roll_no ASC",
        (assignment_id, assignment["course_code"])
    )
    return render_template("faculty_assignment_submissions.html", assignment=assignment, submissions=submissions)


@app.post("/faculty/assignments/submissions/<int:submission_id>/grade")
@roles_required("faculty")
def faculty_grade_submission(submission_id):
    faculty_id = current_user()["id"]
    submission = query(
        "SELECT sub.*, a.assignment_id, a.faculty_id "
        "FROM assignment_submissions sub "
        "JOIN assignments a ON sub.assignment_id = a.assignment_id "
        "WHERE sub.submission_id = %s AND a.faculty_id = %s",
        (submission_id, faculty_id),
        one=True
    )
    if not submission:
        abort(404)

    marks = float(request.form.get("marks_awarded", 0))
    feedback = request.form.get("feedback", "").strip()

    connection = db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE assignment_submissions "
            "SET marks_awarded = %s, feedback = %s, graded_by = %s, graded_at = NOW() "
            "WHERE submission_id = %s",
            (marks, feedback, faculty_id, submission_id)
        )
        connection.commit()
        flash("Grade and rubric feedback saved successfully.", "success")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return redirect(url_for("faculty_assignment_submissions", assignment_id=submission["assignment_id"]))


@app.get("/assignments/submissions/<int:submission_id>/download")
@login_required
def download_assignment_submission(submission_id):
    user = current_user()
    submission = query(
        "SELECT sub.*, a.course_code, a.faculty_id "
        "FROM assignment_submissions sub "
        "JOIN assignments a ON sub.assignment_id = a.assignment_id "
        "WHERE sub.submission_id = %s",
        (submission_id,),
        one=True
    )
    if not submission:
        abort(404)

    if user["typeofuser"] == "student" and user["id"] != submission["student_id"]:
        abort(403)
    elif user["typeofuser"] == "faculty" and user["id"] != submission["faculty_id"]:
        abort(403)

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        submission["file_path"],
        as_attachment=True,
        download_name=submission["original_filename"]
    )


# ==========================================
# TIMED ONLINE QUIZZES & EXAMINATION ENGINE
# ==========================================

@app.get("/student/quizzes")
@roles_required("student")
def student_quizzes_list():
    academic_year, _ = academic_period()
    student_id = current_user()["id"]
    quizzes = query(
        "SELECT q.quiz_id, q.course_code, c.title AS course_title, q.title, q.description, "
        "q.duration_minutes, q.passing_marks, q.due_date, "
        "att.attempt_id, att.status AS attempt_status, att.total_score, att.max_possible_score, "
        "(SELECT COUNT(*) FROM quiz_questions qq WHERE qq.quiz_id = q.quiz_id) AS question_count, "
        "(q.due_date < NOW()) AS is_past_due "
        "FROM quizzes q "
        "JOIN courses c ON q.course_code = c.course_code "
        "JOIN course_enrollments ce ON q.course_code = ce.course_code "
        "LEFT JOIN quiz_attempts att ON q.quiz_id = att.quiz_id AND att.student_id = %s "
        "WHERE ce.student_id = %s AND ce.status = 'approved' AND q.published = 1 "
        "ORDER BY q.due_date ASC",
        (student_id, student_id)
    )
    return render_template("student_quizzes.html", quizzes=quizzes, academic_year=academic_year)


@app.route("/student/quizzes/<int:quiz_id>/take", methods=["GET", "POST"])
@roles_required("student")
def student_quiz_take(quiz_id):
    student_id = current_user()["id"]
    quiz = query(
        "SELECT q.*, c.title AS course_title "
        "FROM quizzes q "
        "JOIN courses c ON q.course_code = c.course_code "
        "JOIN course_enrollments ce ON q.course_code = ce.course_code "
        "WHERE q.quiz_id = %s AND ce.student_id = %s AND ce.status = 'approved' AND q.published = 1",
        (quiz_id, student_id),
        one=True
    )
    if not quiz:
        abort(404)

    attempt = query(
        "SELECT * FROM quiz_attempts WHERE quiz_id = %s AND student_id = %s",
        (quiz_id, student_id),
        one=True
    )
    if attempt and attempt["status"] == "completed":
        return redirect(url_for("student_quiz_result", quiz_id=quiz_id))

    now = datetime.now()
    if not attempt:
        connection = db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO quiz_attempts (quiz_id, student_id, started_at, status) VALUES (%s, %s, %s, 'in_progress')",
                (quiz_id, student_id, now)
            )
            connection.commit()
            attempt_id = cursor.lastrowid
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        started_at = now
    else:
        attempt_id = attempt["attempt_id"]
        started_at = attempt["started_at"]

    deadline = started_at + timedelta(minutes=quiz["duration_minutes"])
    remaining_seconds = max(0, int((deadline - now).total_seconds()))

    questions = query(
        "SELECT question_id, question_text, option_a, option_b, option_c, option_d, marks, order_num "
        "FROM quiz_questions WHERE quiz_id = %s ORDER BY order_num ASC",
        (quiz_id,)
    )

    if request.method == "POST":
        total_score = 0.0
        max_possible = 0.0
        answers_to_save = []

        full_questions = query(
            "SELECT question_id, correct_option, marks FROM quiz_questions WHERE quiz_id = %s",
            (quiz_id,)
        )
        for q in full_questions:
            qid = q["question_id"]
            selected = request.form.get(f"question_{qid}", "").strip().upper()
            is_correct = (selected == q["correct_option"])
            awarded = float(q["marks"]) if is_correct else 0.0
            total_score += awarded
            max_possible += float(q["marks"])
            answers_to_save.append((attempt_id, qid, selected if selected else None, is_correct, awarded))

        connection = db_connection()
        cursor = connection.cursor()
        try:
            cursor.executemany(
                "INSERT INTO quiz_answers (attempt_id, question_id, selected_option, is_correct, marks_awarded) "
                "VALUES (%s, %s, %s, %s, %s)",
                answers_to_save
            )
            cursor.execute(
                "UPDATE quiz_attempts "
                "SET submitted_at = NOW(), total_score = %s, max_possible_score = %s, status = 'completed' "
                "WHERE attempt_id = %s",
                (total_score, max_possible, attempt_id)
            )
            connection.commit()
            flash("Assessment submitted and evaluated successfully!", "success")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        return redirect(url_for("student_quiz_result", quiz_id=quiz_id))

    return render_template(
        "student_quiz_take.html",
        quiz=quiz,
        questions=questions,
        remaining_seconds=remaining_seconds
    )


@app.get("/student/quizzes/<int:quiz_id>/result")
@roles_required("student")
def student_quiz_result(quiz_id):
    student_id = current_user()["id"]
    quiz = query(
        "SELECT q.*, c.title AS course_title "
        "FROM quizzes q "
        "JOIN courses c ON q.course_code = c.course_code "
        "WHERE q.quiz_id = %s",
        (quiz_id,),
        one=True
    )
    if not quiz:
        abort(404)

    attempt = query(
        "SELECT * FROM quiz_attempts WHERE quiz_id = %s AND student_id = %s AND status = 'completed'",
        (quiz_id, student_id),
        one=True
    )
    if not attempt:
        flash("You have not completed this assessment yet.", "error")
        return redirect(url_for("student_quizzes_list"))

    questions = query(
        "SELECT qq.*, qa.selected_option, qa.is_correct, qa.marks_awarded "
        "FROM quiz_questions qq "
        "LEFT JOIN quiz_answers qa ON qq.question_id = qa.question_id AND qa.attempt_id = %s "
        "WHERE qq.quiz_id = %s "
        "ORDER BY qq.order_num ASC",
        (attempt["attempt_id"], quiz_id)
    )
    return render_template("student_quiz_result.html", quiz=quiz, attempt=attempt, questions=questions)


@app.get("/faculty/quizzes")
@roles_required("faculty")
def faculty_quizzes_list():
    academic_year, _ = academic_period()
    faculty_id = current_user()["id"]
    quizzes = query(
        "SELECT q.quiz_id, q.course_code, c.title AS course_title, q.title, q.description, "
        "q.duration_minutes, q.passing_marks, q.due_date, "
        "(SELECT COUNT(*) FROM quiz_questions qq WHERE qq.quiz_id = q.quiz_id) AS question_count, "
        "(SELECT COUNT(*) FROM quiz_attempts qa WHERE qa.quiz_id = q.quiz_id AND qa.status = 'completed') AS attempt_count "
        "FROM quizzes q "
        "JOIN courses c ON q.course_code = c.course_code "
        "WHERE q.faculty_id = %s "
        "ORDER BY q.created_at DESC",
        (faculty_id,)
    )
    return render_template("faculty_quizzes.html", quizzes=quizzes, academic_year=academic_year)


@app.route("/faculty/quizzes/new", methods=["GET", "POST"])
@roles_required("faculty")
def faculty_quiz_create():
    academic_year, semester = academic_period()
    faculty_id = current_user()["id"]
    courses = query(
        "SELECT fc.course_code, c.title "
        "FROM faculty_courses fc "
        "JOIN courses c ON fc.course_code = c.course_code "
        "WHERE fc.faculty_id = %s AND fc.academic_year = %s AND fc.semester = %s",
        (faculty_id, academic_year, semester)
    )

    if request.method == "POST":
        course_code = request.form.get("course_code", "").strip()
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        duration_minutes = int(request.form.get("duration_minutes", 30))
        passing_marks = float(request.form.get("passing_marks", 50))
        due_date_raw = request.form.get("due_date", "").strip()

        if not course_code or not title or not due_date_raw:
            flash("All required fields must be provided.", "error")
            return redirect(request.url)

        try:
            due_date = datetime.strptime(due_date_raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash("Invalid date format.", "error")
            return redirect(request.url)

        connection = db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO quizzes (course_code, faculty_id, title, description, duration_minutes, passing_marks, due_date) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (course_code, faculty_id, title, description, duration_minutes, passing_marks, due_date)
            )
            connection.commit()
            quiz_id = cursor.lastrowid
            flash("Quiz created successfully! Now add questions below.", "success")
            return redirect(url_for("faculty_quiz_questions", quiz_id=quiz_id))
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    return render_template("faculty_quiz_form.html", courses=courses)


@app.route("/faculty/quizzes/<int:quiz_id>/questions", methods=["GET", "POST"])
@roles_required("faculty")
def faculty_quiz_questions(quiz_id):
    faculty_id = current_user()["id"]
    quiz = query(
        "SELECT q.*, c.title AS course_title "
        "FROM quizzes q "
        "JOIN courses c ON q.course_code = c.course_code "
        "WHERE q.quiz_id = %s AND q.faculty_id = %s",
        (quiz_id, faculty_id),
        one=True
    )
    if not quiz:
        abort(404)

    if request.method == "POST":
        text = request.form.get("question_text", "").strip()
        a = request.form.get("option_a", "").strip()
        b = request.form.get("option_b", "").strip()
        c = request.form.get("option_c", "").strip()
        d = request.form.get("option_d", "").strip()
        correct = request.form.get("correct_option", "").strip().upper()
        marks = float(request.form.get("marks", 2.0))
        explanation = request.form.get("explanation", "").strip()

        if not text or not a or not b or not c or not d or correct not in ["A", "B", "C", "D"]:
            flash("All question details and options must be provided.", "error")
            return redirect(request.url)

        order_row = query("SELECT COALESCE(MAX(order_num), 0) + 1 AS next_order FROM quiz_questions WHERE quiz_id = %s", (quiz_id,), one=True)
        next_order = order_row["next_order"] if order_row else 1

        connection = db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO quiz_questions (quiz_id, question_text, option_a, option_b, option_c, option_d, correct_option, marks, explanation, order_num) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (quiz_id, text, a, b, c, d, correct, marks, explanation, next_order)
            )
            connection.commit()
            flash("Question added successfully.", "success")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return redirect(request.url)

    questions = query(
        "SELECT * FROM quiz_questions WHERE quiz_id = %s ORDER BY order_num ASC",
        (quiz_id,)
    )
    total_marks = sum(float(q["marks"]) for q in questions)
    return render_template("faculty_quiz_questions.html", quiz=quiz, questions=questions, total_marks=total_marks)


@app.post("/faculty/quizzes/<int:quiz_id>/questions/<int:question_id>/delete")
@roles_required("faculty")
def faculty_quiz_question_delete(quiz_id, question_id):
    faculty_id = current_user()["id"]
    quiz = query("SELECT quiz_id FROM quizzes WHERE quiz_id = %s AND faculty_id = %s", (quiz_id, faculty_id), one=True)
    if not quiz:
        abort(404)

    connection = db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("DELETE FROM quiz_questions WHERE question_id = %s AND quiz_id = %s", (question_id, quiz_id))
        connection.commit()
        flash("Question deleted.", "success")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return redirect(url_for("faculty_quiz_questions", quiz_id=quiz_id))


@app.get("/faculty/quizzes/<int:quiz_id>/attempts")
@roles_required("faculty")
def faculty_quiz_attempts(quiz_id):
    faculty_id = current_user()["id"]
    quiz = query(
        "SELECT q.*, c.title AS course_title "
        "FROM quizzes q "
        "JOIN courses c ON q.course_code = c.course_code "
        "WHERE q.quiz_id = %s AND q.faculty_id = %s",
        (quiz_id, faculty_id),
        one=True
    )
    if not quiz:
        abort(404)

    attempts = query(
        "SELECT qa.*, s.first_name, s.last_name, s.roll_no "
        "FROM quiz_attempts qa "
        "JOIN student s ON qa.student_id = s.id "
        "WHERE qa.quiz_id = %s "
        "ORDER BY qa.submitted_at DESC",
        (quiz_id,)
    )
    return render_template("faculty_quiz_attempts.html", quiz=quiz, attempts=attempts)


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
