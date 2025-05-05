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
    pdf_uuid = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.u_id), nullable = False)
    filename = db.Column(db.String(120), nullable = False)
    processed_text = db.Column(db.Text, nullable = False)

    def __str__(self):
        return f'{self.filename}({self.pdf_uuid})'

class Youtube(db.Model):
    video_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.u_id), nullable = False)
    video_url = db.Column(db.String(255), nullable = False)
    transcript_text = db.Column(db.Text, nullable = False)

    def __str__(self):
        return f'{self.filename}({self.video_id})'


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
conversation = [
    {'question': 'What is BrainyBot?', 'answer': 'Your Perfect Study Companion!'}
]

pdf_conversation = [
    {'pdf_question': 'Ask anything from the PDF!', 'pdf_answer': 'And get your answers instantly!'}
]

yt_conversation = [
    {'yt_question': 'Ask anything from the YouTube video!', 'yt_answer': 'And get your answers instantly!'}
]

# In‑memory store of extracted PDF text
pdf_texts = {}
yt_texts = {}

@app.route('/')
def home():
    pdf_loaded = ("pdf_uuid" in session)
    video_added = ("video_id" in session)
    return render_template('home.html', pdf_loaded=pdf_loaded, video_added=video_added)

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

@app.route('/ask', methods=['GET', 'POST'])
def ask():
    if 'is_logged_in' not in session:
        flash('You need to login first', 'warning')
        return redirect('/login')

    if request.method == 'POST':
        question = request.form.get('question')
        if not question:
            flash("Please enter a question.")
            return redirect(url_for('ask'))

        prompt = question
        answer = ask_gemini(prompt)
        conversation.append({'question': question, 'answer': answer})
        return render_template('ask_bot.html',conversation= conversation)

    # GET request will render a question form
    return render_template('ask_bot.html',conversation=conversation)

#------------END NORMAL CHAT WITH BOT--------------

#--------START CHAT WITH PDF implementation--------
@app.route('/ask_pdf', methods=['GET','POST'])
def ask_pdf():
    if 'is_logged_in' not in session:
        flash('You need to login first', 'warning')
        return redirect('/login')
    if request.method == 'POST':
        pdf_question = request.form.get('pdf_question')
        if not pdf_question:
            print("Please enter a question.")
            return redirect(url_for('ask_pdf'))
        if 'pdf_uuid' in session:
            # fetch the stored text; if missing, treat as no PDF
            content = pdf_texts.get(session['pdf_uuid'], "")
            prompt = (
                "Use the following PDF content to answer the question:\n\n"
                f"{content}\n\nQuestion: {pdf_question}"
            )
            pdf_answer = ask_gemini(prompt)
            pdf_conversation.append({'pdf_question': pdf_question, 'pdf_answer': pdf_answer})
            return render_template( 'pdf.html', pdf_loaded=('pdf_uuid' in session), pdf_conversation = pdf_conversation)
        else:
            flash("No PDF loaded. Please upload a PDF first.")
            return redirect(url_for('ask_pdf'))
    # GET request will render a question form
    return render_template('pdf.html', pdf_loaded=('pdf_uuid' in session), pdf_conversation=pdf_conversation)

# —— New: upload PDF ——
@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    global pdf_conversation
    file = request.files.get('pdf_file')
    if not file or not file.filename.lower().endswith('.pdf'):
        print("Please upload a valid PDF.")
        return redirect(url_for('ask_pdf'))

    # If there's already one loaded, remove its text entry
    old_uuid = session.get('pdf_uuid')
    if old_uuid and old_uuid in pdf_texts:
        del pdf_texts[old_uuid]

    # Save new PDF
    unique_id = str(uuid.uuid4())
    filename = secure_filename(unique_id + '.pdf')
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    # Extract text
    doc = fitz.open(save_path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()

    # Store and mark session
    pdf_texts[unique_id] = text
    session['pdf_uuid'] = unique_id

    print("PDF uploaded and indexed. You can now ask questions about it!")
    return redirect(url_for('ask_pdf'))


# —— clear PDF ——
@app.route('/clear_pdf')
def clear_pdf():
    pdf_conversation.clear()
    pdf_id = session.pop('pdf_uuid', None)
    if pdf_id and pdf_id in pdf_texts:
        del pdf_texts[pdf_id]
    flash("PDF context cleared.")
    return redirect(url_for('ask_pdf'))
#--------END CHAT WITH PDF implementation--------

#--------START CHAT WITH YOUTUBE implementation--------

@app.route('/process_youtube', methods=['POST'])
def process_youtube():
    url = request.form.get('youtube_url')
    if not url:
        flash("Please enter a valid YouTube URL.")
        return redirect(url_for('ask_youtube'))

    # Extract YouTube ID
    import re
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if not match:
        flash("Invalid YouTube URL.")
        return redirect(url_for('ask_youtube'))

    video_id = match.group(1)

    # Paths
    audio_filename = f"{video_id}.mp3"
    audio_path = os.path.join("uploads", audio_filename)

    # Ensure the uploads folder exists
    os.makedirs("uploads", exist_ok=True)

    # Download audio using yt-dlp
    ffmpeg_path = r"C:/Users/Mimansha/OneDrive/Documents/GitHub/practice/ffmpeg-7.1.1-essentials_build/ffmpeg-7.1.1-essentials_build/bin/ffmpeg.exe"

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': audio_path,
        'ffmpeg_location': ffmpeg_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
    }
    print("Downloading audio...")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            print("Audio downloaded successfully.")
    except Exception as e:
        flash(f"Error downloading video: {e}")
        return redirect(url_for('ask_youtube'))

    # Transcribe using Whisper
    try:
        model = whisper.load_model("base")
        print(f"Audio path exists: {os.path.exists(audio_path)} - {audio_path}")
        result = model.transcribe(audio_path)
        transcript = result["text"]
        print("Transcription completed with whisper.")

    except Exception as e:
        flash(f"Error transcribing video: {e}")
        return redirect(url_for('ask_youtube'))

    # Save transcript in session and file
    yt_texts[video_id] = transcript
    session['video_id'] = video_id
    print("Transcript saved in session.")

    # Save transcript to PDF
    transcript_path = Path("static/downloads")
    transcript_path.mkdir(parents=True, exist_ok=True)

    pdf_file = transcript_path / f"{video_id}.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)
    for line in transcript.split('\n'):
        pdf.multi_cell(0, 10, line)
    pdf.output(str(pdf_file))

    print("Transcription complete. Ask your questions!")
    return render_template('youtube.html', video_added= True, yt_conversation = yt_conversation)


@app.route('/ask_youtube', methods=['GET','POST'])
def ask_youtube():
    if 'is_logged_in' not in session:
        flash('You need to login first', 'warning')
        return redirect('/login')

    if request.method == 'POST':
        yt_question = request.form.get('yt_question')
        video_id = session.get('video_id')
        yt_content = yt_texts.get(video_id, "")

        if not yt_content:
            print("No transcript found. Please upload a video first.")
            return redirect(url_for('ask_youtube'))

        prompt = (
            "Use the following YouTube video transcript to answer the question:\n\n"
            f"{yt_content}\n\nyt_Question: {yt_question}"
        )
        yt_answer = ask_gemini(prompt)
        yt_conversation.append({'yt_question': yt_question, 'yt_answer': yt_answer})

        return render_template('youtube.html', video_added= ('video_id' in session), yt_conversation = yt_conversation)

    # GET request will render a question form
    return render_template('youtube.html', video_added= ('video_id' in session), yt_conversation = yt_conversation)

#--------END CHAT WITH YOUTUBE implementation--------
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
