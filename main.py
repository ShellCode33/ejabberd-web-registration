#!/usr/bin/python3
# -*- coding: utf-8 -*-

from flask import Flask, flash, redirect, render_template, request, session, abort, json
from flask_recaptcha import ReCaptcha
from flask_mysqldb import MySQL
from subprocess import call
import hashlib
import threading
import random
import string
import re
import smtplib
from email.message import EmailMessage

app = Flask(__name__,
            static_url_path='',
            static_folder='static',
            template_folder='templates')

app.config.from_pyfile('config.py')
recaptcha = ReCaptcha(app=app)
db = MySQL(app)

users_file_lock = threading.Lock()

@app.route("/")
def index():
    return render_template('register.html')


@app.route("/thanks")
def thanks():
    return render_template('thanks.html')


@app.route("/register", methods=['POST'])
def register():
    error = None

    if not recaptcha.verify():
        error = "Invalid Captcha"

    username = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")
    confirm_pass = request.form.get("confirm_password")

    if password != confirm_pass:
        error = "Passwords are different"

    if len(email) > 0 and not re.match(r"^[A-Za-z0-9\.\+_-]+@[A-Za-z0-9\._-]+\.[a-zA-Z]*$", email):
        error = "Invalid email address"

    if not error:
        with users_file_lock:
            users_waiting = {}
            file = open("users_waiting_approval", "r")
        
            for line in file:
                tab = line.split(":")

                if len(tab) == 3:
                    users_waiting[tab[0]] = (tab[1], tab[2])

            file.close()

            if username in users_waiting:
                error = "User already in registration process"
            else:
                # Register user using ejabberdctl
                code = call(["/usr/sbin/ejabberdctl", "register", username, app.config["XMPP_HOST"], password])

                if code == 1:
                    error = "User already registered"
                    print(error)
                    return json.dumps(error)

                # Get the hash from database and store it internally user:hash
                cur = db.connection.cursor()
                cur.execute("SELECT password FROM users WHERE username = %s", [username])
                hash = cur.fetchall()[0][0]

                users_waiting[username] = (hash, email)

                file = open("users_waiting_approval", "w")

                for username in users_waiting:
                    file.write(username + ":" + users_waiting[username][0] + ":" + users_waiting[username][1] + "\n")

                file.close()

                # Remove the hash from the database (user can't login until he's approved by an admin)
                cur.execute("UPDATE users SET password = '' WHERE username = %s", [username])
                db.connection.commit()

    return json.dumps(error)


@app.route("/admin/login", methods=['GET', 'POST'])
def admin_login():

    if 'connected' in session:
        return redirect("/admin", code=302)

    error = None

    if not recaptcha.verify():
        error = "Invalid Captcha"

    elif request.method == "POST":
        password = hashlib.sha512(request.form.get('password').encode("utf-8")).hexdigest()

        if password == app.config["ADMIN_PASSWORD"]:
            session['connected'] = 'ok'
            return redirect("/admin", code=302)
        else:
            error = "Wrong password"

    return render_template('admin_login.html', error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin/login", code=302)

@app.route("/admin")
def admin():

    if 'connected' not in session:
        return redirect("/admin/login", code=302)

    # Admin is connected
    # We read the file users_waiting_approval in order to display it

    users = []
    emails = []

    file = open("users_waiting_approval", "r")
    
    for line in file:
        tab = line.split(":")
        users.append(tab[0])
        emails.append(tab[2]) # even if email address is empty

    file.close()

    return render_template('admin.html', users=users, emails=emails)


@app.route("/approve/<username>")
def approve(username):

    if 'connected' not in session:
        return redirect("/admin/login", code=302)

    file = open("users_waiting_approval", "r")
    lines = []

    for line in file:
        if line.startswith(username):
            tab = line.split(":")

            # Restore hash in database
            cur = db.connection.cursor()
            cur.execute("UPDATE users SET password = %s WHERE username = %s", [tab[1], username])
            db.connection.commit()

            # Send email to tab[2]
            msg = EmailMessage()
            msg.set_content("Your account %s has been approved on %s" % (username, app.config['XMPP_HOST']))
            msg['Subject'] = 'Account approved'
            msg['From'] = "noreply@" + app.config['XMPP_HOST']
            msg['To'] = tab[2]
            s = smtplib.SMTP(app.config['SMTP_HOST'])
            s.send_message(msg)
            s.quit()
        else:
            lines.append(line)

    file.close()

    # Write file again without the approved user
    with users_file_lock:
        file = open("users_waiting_approval", "w")

        for line in lines:
            file.write(line)

        file.close()

    return "Approving " + username


@app.route("/deny/<username>")
def deny(username):

    if 'connected' not in session:
        return redirect("/admin/login", code=302)

    file = open("users_waiting_approval", "r")
    lines = []

    for line in file:
        if not line.startswith(username): # Exclude the user to deny
            lines.append(line)

    file.close()

    # Write file again without the approved user
    with users_file_lock:
        file = open("users_waiting_approval", "w")

        for line in lines:
            file.write(line)

        file.close()

    # Unregistering user with ejabberdctl
    call(["/usr/sbin/ejabberdctl", "unregister", username, app.config["XMPP_HOST"]])

    return "Denying " + username


def extract_key_value(config_line):
    tab = config_line.strip().split(": ")

    if len(tab) == 1:
        return tab[0], None

    tab[1] = tab[1].replace("\"", "") # Config lines are already strings within python, so we remove the " read from the config file

    return tab[0], tab[1]


def parse_ejabberd_yml():
    # try to read MySQL parameters
    file = open(app.config['EJABBERD_CONFIG_FILE'], "r")
    
    for line in file:
        if not line.strip().startswith("#"): # If it is not a comment
            key, value = extract_key_value(line)

            # Test if the config file has some requirements

            if key == "auth_method" and value != "sql":
                print("only sql auth method is supported !")
                exit(1)

            if key == "sql_type" and value != "mysql":
                print("MySQL is the only supported DBMS")
                exit(1)

            if key == "auth_password_format" and value != "scram":
                print("scram password format is the only way to secure users' password, please use it.")
                exit(1)


            # Read DB parameters

            if key == "sql_server":
                app.config['MYSQL_HOST'] = value

            elif key == "sql_database":
                app.config['MYSQL_DB'] = value

            elif key == "sql_username":
                app.config['MYSQL_USER'] = value

            elif key == "sql_password":
                app.config['MYSQL_PASSWORD'] = value

            elif key == "sql_port":
                app.config['MYSQL_PORT'] = int(value)

    file.close()


def change_config_values():

    # If the admin password in the config file is not hashed, we do it
    # If the SECRET_KEY is not set, we create a random one

    something_changed = False

    lines = []
    config_file = open("config.py", "r")

    for line in config_file:
        if line.startswith("ADMIN_PASSWORD") and len(app.config['ADMIN_PASSWORD']) != 128:
            hashed = hashlib.sha512(app.config['ADMIN_PASSWORD'].encode('utf-8')).hexdigest()
            lines.append("ADMIN_PASSWORD = \"" + hashed + "\"")
            app.config['ADMIN_PASSWORD'] = hashed
            something_changed = True

        elif line.startswith("SECRET_KEY") and len(app.config['SECRET_KEY']) == 0:
            new_key = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(24)])
            lines.append("SECRET_KEY = \"" + new_key + "\"\n")
            app.config['SECRET_KEY'] = new_key
            something_changed = True

        else:
            lines.append(line)

    config_file.close()

    if something_changed:
        config_file = open("config.py", "w")
        
        for line in lines:
            config_file.write(line)

        config_file.close()


if __name__ == "__main__":
    parse_ejabberd_yml()
    change_config_values()
    print("Running server " + app.config['WEBSITE_NAME'] + "...")
    app.run(host='localhost', port=1337)
    print("Stopping...")
