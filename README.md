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
