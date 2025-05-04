import os
import uuid
import fitz
from flask import Flask, render_template, request, redirect,url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from chatbot import ask_gemini
import whisper
import yt_dlp
from fpdf import FPDF
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

#--Database Logic--

db = SQLAlchemy()

class User(db.Model):
    u_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(70), nullable=False)
    email = db.Column(db.String(80), nullable=False, unique=True)
    password = db.Column(db.String(40), nullable=False)

    def __str__(self):
        return f'{self.username}({ self.u_id})'

class pdf(db.Model):
    pdf_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.u_id), nullable = False)
    filename = db.Column(db.String(120), nullable = False)
    processed_text = db.Column(db.Text, nullable = False)

    def __str__(self):
        return f'{self.filename}({self.pdf_id})'

#--END of Database Logic--
# --FLASK APP logic--
def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///p2e.sqlite'
    app.config['SQLALCHEMY_ECHO'] = True
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY']   = os.getenv('SECRET_KEY')
    app.config['UPLOAD_FOLDER'] = 'static/uploads'
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    db.init_app(app)
    return app

app = create_app()

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def create_login_session(user: User):
    session['id'] = user.u_id
    session['username'] = user.username
    session['email'] = user.email
    session['is_logged_in'] = True

def destroy_login_session():
    if 'is_logged_in' in session:
        session.clear()

'''
to create the project database, open terminal
- type python and press enter
- type
    from app import app, db
    with app.app_context():
        db.create_all()
- enter twice to confirm
'''

@app.route('/')
def home():
    pdf_loaded = ("pdf_uuid" in session)
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

#----------REGISTER IMPLEMENTATION----------
@app.route('/register', methods = ['GET','POST'])
def register():
    errors =[]
    if request.method == 'POST':
        username = request.form.get('username')
        email= request.form.get('email')
        pwd= request.form.get('password')
        cpwd= request.form.get('confirmpassword')
        print(username, email, pwd, cpwd)
        if username and email and pwd and cpwd:
            if len(username) < 2:
                errors.append("Username is too small")
            if len(email) < 11 or '@' not in email:
                errors.append('Email is Invalid')
            if len(pwd) < 6:
                errors.append("Password should have 6 or more characters")
            if pwd != cpwd:
                errors.append("Password do not match")
            if len(errors) == 0:
                user = User(username = username, email = email, password = pwd)
                db.session.add(user)
                db.session.commit()
                flash('User account created successfully',"SUCCESS")
                print("registered done")
                return redirect('/login')
        else:
            errors.append('Fill all the fields')
            flash('User account cannot be created', "warning")
    return render_template('register.html', error_list = errors)

#----------LOGIN IMPLEMENTATION----------
@app.route('/login', methods = ['GET', 'POST'])
def login():
    errors={}
    if request.method =='POST':
        log_email= request.form.get('email')
        log_password= request.form.get('password')
        print("LOGGING IN", log_email,log_password)
        if log_email and log_password:
            if len(log_email) < 11 or '@' not in log_email:
                errors['email'] = 'Email is Invalid'
            if len(errors) == 0:
                user = User.query.filter_by(email= log_email).first()
                if user is not None:
                    print("User account found", user)
                    if user.password == log_password:
                        create_login_session(user)
                        flash('Login successful', "SUCCESS")
                        print('login successfully')
                        return redirect('/')
                    else:
                        errors['password'] = 'Password is invalid'
                else:
                    errors['email']= 'Account does not exists'
                    return redirect('/register')
        else:
            errors['email'] = 'Please fill valid details'
            errors['password'] = 'Please fill valid details'
    return render_template('login.html', errors = errors)

#-----------START NORMAL CHAT WITH BOT------------

@app.route('/ask', methods=['POST'])
def ask():
    if 'is_logged_in' not in session:
        flash('You need to login first', 'warning')
        return redirect('/login')
    else:
        return redirect('/ask_question')

@app.route('/ask_question', methods=['POST'])
def ask_question():
    question = request.form.get('question')
    if not question:
        flash("Please enter a question.")
        return redirect(url_for('home'))

    prompt = question
    answer = ask_gemini(prompt)
    return render_template(
        'home.html',
        answer=answer
    )

#------------END NORMAL CHAT WITH BOT--------------

#--------START CHAT WITH PDF implementation--------
def ask_pdf():
    question = request.form.get('question')
    if not question:
        flash("Please enter a question.")
        return redirect(url_for('home'))

    prompt = question
    if 'pdf_uuid' in session:
        # fetch the stored text; if missing, treat as no PDF
        content = pdf_texts.get(session['pdf_uuid'], "")
        prompt = (
            "Use the following PDF content to answer the question:\n\n"
            f"{content}\n\nQuestion: {question}"
        )

    answer = ask_gemini(prompt)
    return render_template(
        'home.html',
        answer=answer,
        pdf_loaded=('pdf_uuid' in session)
    )
#--------END CHAT WITH PDF implementation--------

#--------LOGOUT IMPLEMENTATION--------
@app.route('/logout')
def logout():
    destroy_login_session()
    flash('You are logged out','success')
    return redirect('/')
#--------END LOGOUT IMPLEMENTATION--------

#---------APP START------------
if __name__ == '__main__':
    # create database tables
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
