SET autocommit = 0;

START TRANSACTION;

-- Create the Database
CREATE DATABASE students_db;

USE students_db;

-- create table for login details
CREATE TABLE login_details(
    id VARCHAR(12) PRIMARY KEY NOT NULL,
    uname VARCHAR(45) NOT NULL,
    PASSWORD VARCHAR(256) NOT NULL,
    typeofuser VARCHAR(45) NOT NULL
);

-- Create the first superadmin manually after importing this schema. Do not use
-- a shared default password for a publicly reachable deployment. For example:
-- INSERT INTO login_details (id, uname, password, typeofuser)
-- VALUES ('SA100', 'YOUR_UNIQUE_USERNAME', SHA2('YOUR_UNIQUE_LONG_PASSWORD', 256), 'superadmin');

-- -------------------------------- Tables ---------------------------------- 

# create the admin table
CREATE TABLE admin(
    id VARCHAR(8) PRIMARY KEY NOT NULL,
    NAME VARCHAR(45) NOT NULL UNIQUE,
    address TEXT NOT NULL,
    phoneno BIGINT NOT NULL,
    age INT NOT NULL,
    sex VARCHAR(10) NOT NULL
);

# create table for faculty
CREATE TABLE faculty (
    id VARCHAR(8) PRIMARY KEY NOT NULL,
    first_name VARCHAR(45) NOT NULL,
    middle_name VARCHAR(45) NOT NULL,
    last_name VARCHAR(45) NOT NULL,
    experience INT NOT NULL,
    doj DATE NOT NULL,
    dob DATE NOT NULL,
    email VARCHAR(255) NOT NULL,
    sub VARCHAR(255) NOT NULL,
    address TEXT NOT NULL,
    qualification TEXT NOT NULL,
    age INT NOT NULL,
    sex VARCHAR(8) NOT NULL,
    phoneno BIGINT NOT NULL
);

# create table for keeping the student record
CREATE TABLE student (
    id VARCHAR(8) PRIMARY KEY NOT NULL,
    first_name VARCHAR(45) NOT NULL,
    middle_name VARCHAR(45) NOT NULL,
    last_name VARCHAR(45) NOT NULL,
    roll_no INT NOT NULL,
    division CHAR(1) NOT NULL,
    address TEXT NOT NULL,
    phoneno BIGINT NOT NULL,
    father_name VARCHAR(100) NOT NULL,
    mother_name VARCHAR(100) NOT NULL,
    std INT NOT NULL,
    dob DATE NOT NULL,
    bloodgroup CHAR(4),
    doa DATE NOT NULL,
    father_occ VARCHAR(100),
    mother_occ VARCHAR(100),
    sex VARCHAR(10) NOT NULL
);

# create table for assigining the class teacher
CREATE TABLE div_details (
    std INT NOT NULL,
    divison CHAR(1) NOT NULL,
    faculty_id VARCHAR(8) NOT NULL PRIMARY KEY,
    FOREIGN KEY (faculty_id)
        REFERENCES faculty(id)
        ON DELETE NO ACTION
        ON UPDATE NO ACTION
);

# creating the table for storing the fees for each year
CREATE TABLE store_fees (
    year_ YEAR NOT NULL PRIMARY KEY,
    monthly INT,
    yearly INT
);

# Update the store_fees table with the fees for each year
INSERT INTO store_fees (year_, monthly, yearly) VALUES
    (2023, 1000, 12000),
    (2024, 1200, 14400),
    (2025, 1500, 18000),
    (2026, 1800, 21600),
    (2027, 2000, 24000);

# creating table for fees 
CREATE TABLE fees (
    id VARCHAR(8) NOT NULL,
    fullyearpaid ENUM('Y', 'N'),
    year_ YEAR NOT NULL,
    jan ENUM('Y', 'N'),
    feb ENUM('Y', 'N'),
    mar ENUM('Y', 'N'),
    april ENUM('Y', 'N'),
    may ENUM('Y', 'N'),
    june ENUM('Y', 'N'),
    july ENUM('Y', 'N'),
    aug ENUM('Y', 'N'),
    sept ENUM('Y', 'N'),
    oct ENUM('Y', 'N'),
    nov ENUM('Y', 'N'),
    dece ENUM('Y', 'N'),

    PRIMARY KEY (id, year_),

    FOREIGN KEY (id)
        REFERENCES student(id)
        ON DELETE CASCADE
        ON UPDATE NO ACTION,

    FOREIGN KEY (year_)
        REFERENCES store_fees(year_)
        ON DELETE NO ACTION
        ON UPDATE NO ACTION
);

# creating the present working days tabble
CREATE TABLE present (
    present_date DATE PRIMARY KEY NOT NULL
);

# creating a table for the attendance
CREATE TABLE attendance (
    id VARCHAR(8) NOT NULL,
    attended ENUM('Y', 'N') NOT NULL,
    date_attend DATE NOT NULL,

    PRIMARY KEY (id, date_attend),

    FOREIGN KEY (id)
        REFERENCES student(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    FOREIGN KEY (date_attend)
        REFERENCES present(present_date)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

--  -------------------------------- Triggers ----------------------------------
# trigger for deleting the record from admin and automatically from login details
DELIMITER &&
CREATE TRIGGER auto_delete_login
AFTER DELETE
ON admin
FOR EACH ROW
BEGIN
    DELETE FROM login_details
    WHERE id = OLD.id;
END &&
DELIMITER ;

# trigger for deleting the record from faculty and automatically from login details
DELIMITER &&
CREATE TRIGGER auto_delete_login_faculty
AFTER DELETE
ON faculty
FOR EACH ROW
BEGIN
    DELETE FROM login_details
    WHERE id = OLD.id;

    DELETE FROM div_details
    WHERE faculty_id = OLD.id;
END &&
DELIMITER ;

# creating a trigger to delete the div details 
DELIMITER &&
CREATE TRIGGER delete_from_div
BEFORE DELETE
ON faculty
FOR EACH ROW
BEGIN
    DELETE FROM div_details
    WHERE faculty_id = OLD.id;
END &&
DELIMITER ;

# creating trigger to auto delete the login detials form the student
DELIMITER &&
CREATE TRIGGER dele_student_login
AFTER DELETE
ON student
FOR EACH ROW
BEGIN
    DELETE FROM login_details
    WHERE id = OLD.id;
END &&
DELIMITER ;

# create a trigger to auto add the student in the fees table
DELIMITER &&
CREATE TRIGGER auto_add_fees
AFTER INSERT
ON student
FOR EACH ROW
BEGIN
    INSERT INTO fees
    VALUES (
        NEW.id,
        'N',
        YEAR(NEW.doa),
        'N',
        'N',
        'N',
        'N',
        'N',
        'N',
        'N',
        'N',
        'N',
        'N',
        'N',
        'N'
    );
END &&
DELIMITER ;

--  -------------------------------- Functions --------------------------------

# to add the correct admin id
DELIMITER &&
CREATE FUNCTION get_correct_fid(idi VARCHAR(8))
RETURNS VARCHAR(8)
DETERMINISTIC
BEGIN
    DECLARE i INT DEFAULT 0;
    DECLARE rore VARCHAR(8);
    DECLARE noofro INT;
    DECLARE ex_id INT;
    DECLARE returnid VARCHAR(8);
    SELECT COUNT(*) INTO noofro
    FROM student;
    id_label: LOOP
        SELECT id
        INTO rore
        FROM admin
        ORDER BY id
        LIMIT 1 OFFSET i;
        SELECT SUBSTRING(rore, 3, 5)
        INTO ex_id;
        IF i >= noofro THEN
            RETURN idi;
        ELSEIF rore = idi THEN
            SET ex_id = ex_id + 1;
            SET idi = CONCAT('AD', ex_id);
            SET i = i + 1;
        ELSE
            SET i = i + 1;
        END IF;
    END LOOP;
END &&
DELIMITER ;


# for adding the correcct faculty id 
DELIMITER &&
CREATE FUNCTION get_correct_aid(idi VARCHAR(8))
RETURNS VARCHAR(8)
DETERMINISTIC
BEGIN
    DECLARE i INT DEFAULT 0;
    DECLARE rore VARCHAR(8);
    DECLARE noofro INT;
    DECLARE ex_id INT;
    SELECT COUNT(*) INTO noofro
    FROM faculty;
    id_label: LOOP
        SELECT id
        INTO rore
        FROM faculty
        ORDER BY id
        LIMIT 1 OFFSET i;
        SELECT SUBSTRING(rore, 3, 5)
        INTO ex_id;
        IF i >= noofro THEN
            RETURN idi;
        ELSEIF rore = idi THEN
            SET ex_id = ex_id + 1;
            SET idi = CONCAT('FT', ex_id);
            SET i = i + 1;
        ELSE
            SET i = i + 1;
        END IF;
    END LOOP;
END &&
DELIMITER ;

# fucntion to get the correct id for studetn
DELIMITER &&
CREATE FUNCTION get_correct_sid(idi VARCHAR(8))
RETURNS VARCHAR(8)
DETERMINISTIC
BEGIN
    DECLARE i INT DEFAULT 0;
    DECLARE rore VARCHAR(8);
    DECLARE noofro INT;
    DECLARE ex_id INT;

    SELECT COUNT(*) INTO noofro
    FROM admin;

    id_label: LOOP
        SELECT id
        INTO rore
        FROM student
        ORDER BY id
        LIMIT 1 OFFSET i;

        SELECT SUBSTRING(rore, 3, 5)
        INTO ex_id;

        IF i >= noofro THEN
            RETURN idi;
        ELSEIF rore = idi THEN
            SET ex_id = ex_id + 1;
            SET idi = CONCAT('ST', ex_id);
            SET i = i + 1;
        ELSE
            SET i = i + 1;
        END IF;
    END LOOP;
END &&
DELIMITER ;

# creating a function for geting absent or present
DELIMITER &&
CREATE FUNCTION get_presentee(PA CHAR(1))
RETURNS VARCHAR(45)
DETERMINISTIC
BEGIN
    IF PA = 'Y' THEN
        RETURN 'Present';
    ELSEIF PA = 'N' THEN
        RETURN 'Absent';
    END IF;
END &&
DELIMITER ;

--  ---------------------------------- Stored Procedures -----------------------------------

# creating the stored procedure to add the admin id automatically
DELIMITER &&
CREATE PROCEDURE addadmin(
    IN name VARCHAR(255),
    IN address TEXT,
    IN phoneno BIGINT,
    IN age INT,
    IN sex VARCHAR(10)
)
BEGIN
    DECLARE countad INT DEFAULT 0;
    DECLARE i INT DEFAULT 1000;
    DECLARE idreturn VARCHAR(8);
    DECLARE getid VARCHAR(8);

    SELECT COUNT(*) INTO countad
    FROM admin;

    SET i = countad + i;
    SET idreturn = CONCAT('AD', i);

    INSERT INTO admin
    VALUES (
        get_correct_fid(idreturn),
        name,
        address,
        phoneno,
        age,
        sex
    );
END &&
DELIMITER ;

# stored procedure to add the faculty id automatically
DELIMITER &&
CREATE PROCEDURE addfaculty(
    IN fn VARCHAR(45),
    IN mn VARCHAR(45),
    IN ln VARCHAR(45),
    IN exp INT,
    IN doj DATE,
    IN dob DATE,
    IN email VARCHAR(255),
    IN sub VARCHAR(255),
    IN address TEXT,
    IN quali TEXT,
    IN age INT,
    IN sex VARCHAR(8),
    IN phone BIGINT
)
BEGIN
    DECLARE countad INT DEFAULT 0;
    DECLARE i INT DEFAULT 10000;
    DECLARE idreturn VARCHAR(8);
    DECLARE getid VARCHAR(8);

    SELECT id
    INTO getid
    FROM faculty
    ORDER BY id DESC
    LIMIT 1;

    SELECT COUNT(*) INTO countad
    FROM faculty;

    SET i = countad + i;
    SET idreturn = CONCAT('FT', i);

    INSERT INTO faculty
    VALUES (
        get_correct_aid(idreturn),
        fn,
        mn,
        ln,
        exp,
        doj,
        dob,
        email,
        sub,
        address,
        quali,
        age,
        sex,
        phone
    );
END &&
DELIMITER ;

# create a procedure to add the student id
DELIMITER &&
CREATE PROCEDURE addstudent(
    IN f_name VARCHAR(45),
    IN m_name VARCHAR(45),
    IN l_name VARCHAR(45),
    IN rolno INT,
    IN divi CHAR(1),
    IN addr TEXT,
    IN phone BIGINT,
    IN father_n VARCHAR(100),
    IN mother_n VARCHAR(100),
    IN std INT,
    IN dob DATE,
    IN bg CHAR(4),
    IN doa DATE,
    IN father_occ VARCHAR(100),
    IN mother_occ VARCHAR(100),
    IN sex VARCHAR(10)
)
BEGIN
    DECLARE countad INT DEFAULT 0;
    DECLARE i INT DEFAULT 10000;
    DECLARE idreturn VARCHAR(8);
    DECLARE getid VARCHAR(8);

    SELECT COUNT(*) INTO countad
    FROM student;

    SET i = countad + i;
    SET idreturn = CONCAT('ST', i);

    INSERT INTO student
    VALUES (
        get_correct_sid(idreturn),
        f_name,
        m_name,
        l_name,
        rolno,
        divi,
        addr,
        phone,
        father_n,
        mother_n,
        std,
        dob,
        bg,
        doa,
        father_occ,
        mother_occ,
        sex
    );
END &&
DELIMITER ;

# create procedure to add the fees 
DELIMITER &&
CREATE PROCEDURE add_fees(
    IN id_c VARCHAR(8),
    IN ye YEAR
)
BEGIN
    INSERT INTO fees
    VALUES (
        id_c,
        'N',
        ye,
        'N',
        'N',
        'N',
        'N',
        'N',
        'N',
        'N',
        'N',
        'N',
        'N',
        'N',
        'N'
    );
END &&
DELIMITER ;


COMMIT;
