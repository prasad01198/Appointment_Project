import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_mysqldb import MySQL
from datetime import datetime, timedelta, date
from dotenv import load_dotenv
import pymysql
from passlib.hash import sha256_crypt

# Load environment variables from .env file
load_dotenv()

# Define the starting time for appointments
START_TIME = datetime.strptime("08:00", "%H:%M")

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# MySQL configurations
mysql = MySQL(app)
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')

# Custom exception for database connection error
class DatabaseConnectionError(Exception):
    pass

try:
    # Check database connection
    connection = pymysql.connect(host=app.config['MYSQL_HOST'],
                                 user=app.config['MYSQL_USER'],
                                 password=app.config['MYSQL_PASSWORD'],
                                 database=app.config['MYSQL_DB'])
    print("Database connection successful.")
except pymysql.Error as e:
    print("Error connecting to the database:", e)
    raise DatabaseConnectionError("Failed to connect to the database.")
finally:
    if connection:
        connection.close()

# Custom exception for invalid date format
class InvalidDateFormatError(Exception):
    pass

# Error handlers
@app.errorhandler(InvalidDateFormatError)
def handle_invalid_date_format_error(error):
    return render_template('appointment.html', error='Invalid date format. Please use MM/DD/YYYY format.'), 400

@app.errorhandler(DatabaseConnectionError)
def handle_database_connection_error(error):
    return render_template('error.html', error='Failed to connect to the database. Please try again later.'), 500

@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']

            cur = mysql.connection.cursor()
            query = "SELECT id, password FROM users WHERE username = %s"
            cur.execute(query, (username,))
            user = cur.fetchone()

            if user and sha256_crypt.verify(password, user[1]):
                session['logged_in'] = True
                session['username'] = username
                session['user_id'] = user[0]

                # Redirect to appropriate page after login
                if username == 'CareCentral' and password == 'CareCentral':
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('index'))
            else:
                return render_template('login.html', error='Invalid username or password')
        except Exception as e:
            return render_template('login.html', error='An error occurred while processing your request.'), 500

    return render_template('login.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    try:
        current_date = date.today()

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT id, user_id, name, email, phone, date, timeslot, message, created_at FROM appointments")
        appointments = cursor.fetchall()
        cursor.close()

        current_day_appointments = [appointment for appointment in appointments if appointment[5] == current_date]

        return render_template('admin_dashboard.html', current_day_appointments=current_day_appointments)
    except Exception as e:
        return render_template('admin_dashboard.html', error='An error occurred while processing your request.'), 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            email = request.form['email']
            
            cur = mysql.connection.cursor()
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            existing_user = cur.fetchone()
            
            if existing_user:
                cur.close()
                return render_template('register.html', error='Username already exists'), 400
            else:
                hashed_password = sha256_crypt.hash(password)
                cur.execute("INSERT INTO users (username, password, email) VALUES (%s, %s, %s)", (username, hashed_password, email))
                mysql.connection.commit()
                cur.close()
                return redirect(url_for('login'))
        except Exception as e:
            return render_template('register.html', error='An error occurred while processing your request.'), 500

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/appointment', methods=['GET', 'POST'])
def appointment():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            name = request.form['name']
            email = request.form['email']
            phone = request.form['phone']
            date_str = request.form['date']
            message = request.form['message']

            selected_date = datetime.strptime(date_str, '%m/%d/%Y').date()

            if selected_date < date.today():
                return render_template('appointment.html', error='Cannot book appointments for past dates.'), 400

            if selected_date == date.today():
                start_time = datetime.now().time()
                if start_time >= datetime.strptime("19:00", "%H:%M").time():
                    return render_template('appointment.html', error='Cannot book appointments after 19:00 today. Please select another date.'), 400

            formatted_date = selected_date.strftime('%Y-%m-%d')
            cur = mysql.connection.cursor()
            cur.execute("SELECT timeslot FROM appointments WHERE date = %s", (formatted_date,))
            appointments = cur.fetchall()

            next_timeslot = START_TIME
            while True:
                if next_timeslot >= datetime.strptime("19:00", "%H:%M"):
                    return render_template('appointment.html', error='All slots for today are booked. Please select another date.'), 400

                if next_timeslot.strftime("%H:%M") == "12:00":
                    next_timeslot += timedelta(hours=1)
                    continue
                
                timeslot_available = True
                for appointment in appointments:
                    if next_timeslot.strftime("%H:%M") == appointment[0].split(' to ')[0]:
                        timeslot_available = False
                        break
                
                if timeslot_available:
                    break
                
                next_timeslot += timedelta(hours=1)

            next_timeslot_str = next_timeslot.strftime("%H:%M") + " to " + (next_timeslot + timedelta(hours=1)).strftime("%H:%M")

            cur.execute("INSERT INTO appointments (user_id, name, email, phone, date, timeslot, message) VALUES (%s, %s, %s, %s, %s, %s, %s)", (session['user_id'], name, email, phone, formatted_date, next_timeslot_str, message))
            mysql.connection.commit()
            cur.close()
            return redirect(url_for('dashboard'))
        except ValueError:
            return render_template('appointment.html', error='Invalid date format. Please use MM/DD/YYYY format.'), 400
        except Exception as e:
            return render_template('appointment.html', error='An error occurred while processing your request.'), 500

    else:
        return render_template('appointment.html')

@app.route('/dashboard')
def dashboard():
    try:
        if 'user_id' in session:
            user_id = session['user_id']
            cur = mysql.connection.cursor()
            cur.execute("SELECT name, phone, date, timeslot, created_at FROM appointments WHERE user_id = %s", (user_id,))
            appointments = cur.fetchall()
            cur.close()
            return render_template('dashboard.html', appointments=appointments)
        else:
            return redirect(url_for('login'))
    except Exception as e:
        return render_template('dashboard.html', error='An error occurred while processing your request.'), 500

@app.route('/recent_appointments')
def recent_appointments():
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT id, user_id, name, email, phone, date, timeslot, message, created_at FROM appointments WHERE date < CURDATE()")
        past_appointments = cursor.fetchall()
        cursor.close()

        return render_template('recent_appointments.html', past_appointments=past_appointments)
    except Exception as e:
        return render_template('recent_appointments.html', error='An error occurred while processing your request.'), 500

@app.route('/upcoming_appointments')
def upcoming_appointments():
    try:
        current_date = date.today()

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT id, user_id, name, email, phone, date, timeslot, message, created_at FROM appointments WHERE date > %s", (current_date,))
        upcoming_appointments = cursor.fetchall()
        cursor.close()

        return render_template('upcoming_appointments.html', upcoming_appointments=upcoming_appointments)
    except Exception as e:
        return render_template('upcoming_appointments.html', error='An error occurred while processing your request.'), 500
    
@app.route('/delete_appointment/<int:appointment_id>', methods=['POST'])
def delete_appointment(appointment_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM appointments WHERE id = %s", (appointment_id,))
        mysql.connection.commit()
        cur.close()
        return redirect(url_for('upcoming_appointments'))
    except Exception as e:
        return render_template('upcoming_appointments.html', error='An error occurred while processing your request.'), 500


if __name__ == '__main__':
    app.run(debug=True)