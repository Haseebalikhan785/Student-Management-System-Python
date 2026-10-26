# Student Management System in Python

![python](https://img.shields.io/badge/Python-v3.9.10-green?style=plastic&logo=python&logoWidth=20) ![gui](https://img.shields.io/badge/GUI-Tkinter-red?style=plastic&logo=appveyor) ![database](https://img.shields.io/badge/Database-mysql-brightgreen?style=plastic&logo=mysql&logoWidth=15) ![licnese](https://img.shields.io/badge/License-GPL-blue.svg)
<br/>

### Introduction :

<p align="justify"> Student Management System is made using python with tkinter gui and Database used is mysql. This management system consists of the Superadmin login,admin login, faculty login, student login. This can make the work of the college more simple.</p> <br />

### Modules Used :

- Tkinter
- mysql-connector python
- tkcalendar
- tktooltip
- PIL (Python Imaging Library)

### Working :

✳️**Types of Login** -

1. Super Admin - Super admin can add the admin and manages the admin or he can update the admin or can change his own password.
2. Admin - Admin can add the faculty, manage the faculty, add the student, manages the Student and can update the fees record or add the fees record.
3. Faculty - Faculty can mark the attendance for the specified date by selecting the class and division. Faculty can also view the student records. Faculty can assign the class teacher by themselves only.
4. Student - Student can see his profile and can view his attendance history or fees paid history.
   <br />

✳️ **Database Design** -

<p align="justify">The database is design in such a way that when a student, admin or faculty is added the database automatically assigns the id to them. I have used the concept like stored procedure, function and triggers to do this process. Also the attendance can be recorded and used such query.

### Project Video Link :

If you want to see the detail output of my project - [Click here](https://youtu.be/iMQJRHVZQHA)

### Installation Process :

<p align="justify">Follow these steps to set up and run the Student Management System:</p>

**Step 1: Clone the Repository**

    git clone https://github.com/Haseebalikhan785/Student-Management-System-Python.git

<br />

**Step 2: Install MySQL Server**

Download and install MySQL server locally on your machine from [MySQL Official Website](https://dev.mysql.com/downloads/mysql/)

<br />

**Step 3: Run the Database Script**

Execute the `Script.sql` file in your MySQL server to create the database and tables:

    - Open MySQL Command Line or MySQL Workbench
    - Run: source Resources/Script.sql

<br />

**Step 4: Install Dependencies**

Install all required Python dependencies using `uv sync` and activate the virtual environment:

    uv sync
    .venv\Scripts\activate

<br />

**Step 5: Update Configuration**

Edit the `config.ini` file with your MySQL database credentials:

    - database username
    - database password
    - database host
    - database name

<br />

**Step 6: Run the Application**

Execute the application:

    py app.py

### Author : Prathamesh Dhande


## Maintainer

This repository is an independently published copy maintained by Haseeb Ali. The original project was created by Prathamesh Dhande. Original source: https://github.com/PrathameshDhande22/Student-Management-System-in-Python.

This project is distributed under the GNU General Public License v3.0. See [LICENSE](LICENSE) for the full terms. Please retain this attribution and license when redistributing.

## Browser-based edition

This repository includes both the original Tkinter desktop app and a browser edition in `webapp.py`. Render runs the browser edition; the desktop app remains available through `python app.py` on a computer with a desktop environment.

**Live browser app:** [University Management System](https://student-management-system-web-hbun.onrender.com/)

The browser edition is branded University Management System and supports separate role-based dashboards for students, faculty, administrators, and superadmins. It includes student and faculty directories, academic departments and courses, faculty course assignments, student registration requests and approvals, course attendance, gradebooks, transcripts, timetables, notices, daily attendance, fee plans and records, and administrative reports. New student, faculty, and administrator records receive an account ID and a login in one transaction. The browser app creates missing application tables on first database connection; all newly created tables have primary keys for MySQL hosts that require them.

### Run locally

1. Install and configure MySQL, then run `Resources/Script.sql`.
2. Create a unique first superadmin account in `login_details`. The SQL file includes a commented example; choose a strong private password and do not commit it.
3. Install the browser app dependencies with `python3 -m pip install -r requirements-web.txt`.
4. Set `SECRET_KEY`, `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE` in your environment.
5. Start the development server with `flask --app webapp run`.

### Deploy to Render

The included `render.yaml` prepares a Render web service. In Render, create a Blueprint from this repository, connect a reachable MySQL database, and enter its connection settings as the prompted environment variables. Keep the database private and use a strong, unique superadmin password. Render will provide the web URL and redeploy when the linked Git branch is updated.

### Deploy to Google Cloud Run

This repository includes a production-ready `Dockerfile` optimized for Google Cloud Run:

1. **Via Google Cloud Console:**
   - Go to Google Cloud Console > Cloud Run > Create Service.
   - Choose "Continuously deploy from a repository" and link your GitHub repository.
   - Select Dockerfile build.
   - Under Variables & Secrets, set:
     - `MYSQL_HOST` (e.g. your Aiven host `student-management-db-....aivencloud.com`)
     - `MYSQL_PORT` (`21442`)
     - `MYSQL_USER` (`avnadmin`)
     - `MYSQL_PASSWORD` (your Aiven password)
     - `MYSQL_DATABASE` (`students_db` or `defaultdb`)
     - `SECRET_KEY` (a random secure string)
     - `COOKIE_SECURE` (`true`)

2. **Via gcloud CLI:**
   ```bash
   gcloud run deploy university-management \
     --source . \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars MYSQL_HOST="...",MYSQL_PORT="21442",MYSQL_USER="...",MYSQL_PASSWORD="...",MYSQL_DATABASE="...",SECRET_KEY="..."
   ```

This is an academic project, not a production school information system. Before putting real student data online, review privacy, backup, and access-control requirements. Keep database credentials in the host's private environment settings and never commit them. The sample superadmin login (`admin` / `admin1234`) has been removed from the SQL setup script.
