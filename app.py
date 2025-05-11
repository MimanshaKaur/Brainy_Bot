import os
import uuid
import fitz
from flask import Flask, render_template, request, redirect,url_for, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from chatbot import ask_gemini
import whisper
import yt_dlp
from fpdf import FPDF
from io import BytesIO
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# Force whisper/ffmpeg to use the right binary
os.environ["PATH"] += os.pathsep + r"C:/Users/Mimansha/OneDrive/Documents/GitHub/practice/ffmpeg-7.1.1-essentials_build/ffmpeg-7.1.1-essentials_build/bin"

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

class Notes(db.Model):
    notes_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.u_id), nullable = False)

    def __str__(self):
        return f'{self.filename}({self.notes_id})'

class mcqs(db.Model):
    mcq_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.u_id), nullable = False)

    def __str__(self):
        return f'{self.filename}({self.mcq_id})'

class flashcard(db.Model):
    flash_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.u_id), nullable = False)

    def __str__(self):
        return f'{self.filename}({self.flash_id})'

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
notes_texts = {}
mcq_notes_texts ={}
flash_notes_texts ={}
notes_answer = ""
mcq_answer = ""
flash_answer = ""

@app.route('/')
def home():
    pdf_loaded = ("pdf_uuid" in session)
    video_id= ("video_id" in session)
    return render_template('home.html', pdf_loaded=pdf_loaded, video_id=video_id)

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

class CustomPDF(FPDF):
    def header(self):
        # Add the app title
        self.ln(12)
        self.set_font("Arial", style="B", size=20)
        self.cell(0, 10, "BrainyBot: AI Smart Study Assistant", align="C", ln=True)
        self.ln(10)

    def footer(self):
        # Add the footer with page number
        self.set_y(-15)
        self.set_font("Arial", size=12)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def draw_black_margin(self):
        self.set_draw_color(0, 0, 0)
        self.set_line_width(1)
        self.rect(5, 5, 200, 287)

    def add_page(self, orientation='', format='', same=False):
        super().add_page(orientation, format, same)
        self.draw_black_margin()

def wrap_text_line(text, max_length=100):
    import textwrap
    return textwrap.wrap(text, width=max_length)

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
        print("Invalid YouTube URL.")
        return redirect(url_for('ask_youtube'))

    video_id = match.group(1)
    base_filename = os.path.join("uploads", video_id)

    ffmpeg_path = r"C:/Users/Mimansha/OneDrive/Documents/GitHub/practice/ffmpeg-7.1.1-essentials_build/ffmpeg-7.1.1-essentials_build/bin"  # your path

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': base_filename,
        'ffmpeg_location': ffmpeg_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            print("Video downloaded successfully.")
    except Exception as e:
        print(f"Error downloading video: {e}")
        return redirect(url_for('ask_youtube'))

    audio_path = base_filename + ".mp3"
    print("Audio path:", audio_path)

    if not os.path.exists(audio_path):
        print("Audio file was not created. Something went wrong with yt_dlp or FFmpeg.")
        return redirect(url_for('ask_youtube'))

    # Transcribe
    try:
        model = whisper.load_model("base")
        result = model.transcribe(audio_path)
        transcript = result["text"]
        print("Transcription complete.")
    except Exception as e:
        print(f"Error transcribing video: {e}")
        return redirect(url_for('ask_youtube'))


    # Save transcript in session and file
    session['youtube_transcript'] = transcript
    session['video_id'] = video_id
    print("Transcript saved in session.")

    # Save transcript to PDF
    transcript_path = Path("static/downloads")
    transcript_path.mkdir(parents=True, exist_ok=True)
    print("Transcript path created.")

    pdf_file = transcript_path / f"{video_id}.pdf"
    pdf = CustomPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    def draw_black_margin():
        pdf.set_draw_color(0, 0, 0)  # Black color
        pdf.set_line_width(1)       # Line thickness
        pdf.rect(5, 5, 200, 287)    # Rectangle (x, y, width, height)

    # Add the starting page
    pdf.add_page()
    draw_black_margin()
    pdf.set_font("Arial", size=14)

    for line in transcript.split('\n'):
        pdf.multi_cell(0, 10, line)
    pdf.output(str(pdf_file))

    print("Transcription complete. Ask your questions!")
    return redirect(url_for('ask_youtube'))

@app.route('/ask_youtube', methods=['GET','POST'])
def ask_youtube():
    if 'is_logged_in' not in session:
        flash('You need to login first', 'warning')
        return redirect('/login')

    if request.method == 'POST':
        yt_question = request.form.get('yt_question')
        yt_content = session.get('youtube_transcript')
        video_id = session.get('video_id')

        if not yt_content:
            print("No transcript found. Please upload a video first.")
            return redirect(url_for('ask_youtube'))

        if not video_id:
            print("No video ID found. Please upload a video first.")
            return redirect(url_for('ask_youtube'))

        prompt = (
            "Use the following YouTube video transcript to answer the question:\n\n"
            f"{yt_content}\n\nQuestion: {yt_question}"
        )
        yt_answer = ask_gemini(prompt)
        yt_conversation.append({'yt_question': yt_question, 'yt_answer': yt_answer})
        print("YouTube question answered.")
        print('video_id:', video_id)

        return render_template('youtube.html', video_id= ('video_id' in session), yt_conversation = yt_conversation)

    # GET request will render a question form
    return render_template('youtube.html', video_id= ('video_id' in session), yt_conversation = yt_conversation)

@app.route('/download_transcript')
def download_transcript():
    video_id = session.get('video_id')
    if not video_id:
        flash("No transcript to download.")
        return redirect(url_for('ask_youtube'))

    path = f"static/downloads/{video_id}.pdf"
    if not os.path.exists(path):
        flash("Transcript file not found.")
        return redirect(url_for('ask_youtube'))

    return redirect(f"/{path}")

@app.route('/clear_video')
def clear_video():
    session.pop('video_id', None)
    session.pop('youtube_transcript', None)
    global yt_conversation
    yt_conversation.clear()
    print("YouTube video context cleared.")
    return redirect(url_for('ask_youtube'))

#--------END CHAT WITH YOUTUBE implementation--------
#--------START NOTES SUMMARIZER IMPLEMENTATION--------
@app.route('/upload_notes', methods=['POST'])
def upload_notes():
    notes_file = request.files.get('notes_file')
    if not notes_file or not notes_file.filename.lower().endswith('.pdf'):
        print("Please upload a valid PDF.")
        return redirect(url_for('get_notes'))

    # If there's already one loaded, remove its text entry
    old_notes_id = session.get('notes_id')
    if old_notes_id and old_notes_id in notes_texts:
        del notes_texts[old_notes_id]

    # Save new PDF
    unique_id = str(uuid.uuid4())
    filename = secure_filename(unique_id + '.pdf')
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    notes_file.save(save_path)

    # Extract text
    doc = fitz.open(save_path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    print("Text extracted from PDF for notes.")

    # Store and mark session
    notes_texts[unique_id] = text
    session['notes_id'] = unique_id

    print("PDF uploaded and indexed. You can now ask questions about it!")
    return redirect(url_for('get_notes'))

@app.route('/get_notes', methods=['GET','POST'])
def get_notes():
    print("Notes page loaded")
    if 'is_logged_in' not in session:
        flash('You need to login first', 'warning')
        return redirect('/login')
    if request.method == 'POST':
        notes_question = "Please Summarize this text"
        print("Notes question:")

        if 'notes_id' in session:
            # fetch the stored text; if missing, treat as no PDF
            notes_content = notes_texts.get(session['notes_id'], "")
            prompt = (
                "Use the following PDF content and summarize it:\n\n"
                f"{notes_content}\n\nQuestion: {notes_question}"
            )
            notes_answer = ask_gemini(prompt)
            print('Notes question answered.')
            return render_template( 'notes.html', notes_loaded=('notes_id' in session), notes_answer=notes_answer)
        else:
            print("No PDF  for notes loaded. Please upload a PDF first.")
            return redirect(url_for('get_notes'))
    # GET request will render a question form
    return render_template( 'notes.html', notes_loaded=('notes_id' in session))

@app.route('/download_pdf', methods=['POST'])
def download_pdf():
    notes_id = session.get('notes_id')
    notes = request.form.get('notes_answer', '')

    pdf = CustomPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Add the starting page
    pdf.add_page()
    pdf.set_font("Arial", size=14)

    # Split the text into lines so it wraps properly
    lines = notes.split('\n')
    for line in lines:
        pdf.multi_cell(w=180, h=10, txt=line, align='L')

    # Output PDF to memory
    pdf_buffer = BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"{notes_id or 'notes_output'}.pdf",
        mimetype='application/pdf'
    )

# —— clear notesPDF ——
@app.route('/clear_notes')
def clear_notes():
    notes_id = session.pop('notes_id', None)
    if notes_id and notes_id in pdf_texts:
        del notes_texts[notes_id]
    flash("PDF notes context cleared.")
    return redirect(url_for('get_notes'))

#--------END NOTES SUMMARIZER IMPLEMENTATION--------
#-----------START REVISION IMPLEMENTATION-----------
@app.route('/revision', methods=['GET','POST'])
def revision():
    if 'is_logged_in' not in session:
        flash('You need to login first', 'warning')
        return redirect('/login')
    return render_template('revision.html')

#--------START GENERATING MCQs----------------------
@app.route('/mcq_generator', methods = ['GET','POST'])
def mcq_generator():
    if 'is_logged_in' not in session:
        flash('You need to login first', 'warning')
        return redirect('/login')
    return render_template('mcq.html')

@app.route('/upload_mcq_notes', methods=['POST'])
def upload_mcq_notes():
    mcq_notes_file = request.files.get('mcq_notes_file')
    if not mcq_notes_file or not mcq_notes_file.filename.lower().endswith('.pdf'):
        print("Please upload a valid mcq PDF.")
        return redirect(url_for('get_mcq'))

    # If there's already one loaded, remove its text entry
    old_mcq_notes_id = session.get('mcq_id')
    if old_mcq_notes_id and old_mcq_notes_id in mcq_notes_texts:
        del mcq_notes_texts[old_mcq_notes_id]

    # Save new PDF
    unique_id = str(uuid.uuid4())
    filename = secure_filename(unique_id + '.pdf')
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    mcq_notes_file.save(save_path)

    # Extract text
    doc = fitz.open(save_path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    print("Text extracted from mcq PDF for mcqs.")

    # Store and mark session
    mcq_notes_texts[unique_id] = text
    session['mcq_notes_id'] = unique_id

    print("PDF uploaded and indexed. You can now generate mcqs!")
    return redirect(url_for('get_mcq'))

@app.route('/get_mcq', methods=['GET','POST'])
def get_mcq():
    print("mcq Notes page loaded")
    if 'is_logged_in' not in session:
        flash('You need to login first', 'warning')
        return redirect('/login')
    if request.method == 'POST':
        mcq_notes_question = "Please generate 10 MCQs each with 4 options in separate lines from this PDF Content. Also show its correct answer only without explanation. just show mcqs with options and correct answer no extra text."
        print("mcq-Notes question:")

        if 'mcq_notes_id' in session:
            # fetch the stored text; if missing, treat as no PDF
            mcq_notes_content = mcq_notes_texts.get(session['mcq_notes_id'], "")
            prompt = (
                "Use the following PDF content and generate 10 MCQs with 4 options of each in separate line. Also show correct answer of each MCQ without explanation and no extra text, just show the mcqs with options and correct answer:\n\n"
                f"{mcq_notes_content}\n\nQuestion: {mcq_notes_question}"
            )
            mcq_notes_answer = ask_gemini(prompt)
            print('mcq created.')
            return render_template( 'mcq.html', mcq_loaded=('mcq_notes_id' in session), mcq_notes_answer=mcq_notes_answer)
        else:
            print("No PDF  for mcqs loaded. Please upload a PDF first.")
            return redirect(url_for('get_mcq'))
    # GET request will render a question form
    return render_template( 'mcq.html', mcq_loaded=('mcq_notes_id' in session))

# —— clear MCQ PDF ——
@app.route('/clear_mcq')
def clear_mcq():
    mcq_notes_id = session.pop('mcq_notes_id', None)
    if mcq_notes_id and mcq_notes_id in mcq_notes_texts:
        del mcq_notes_texts[mcq_notes_id]
    flash("MCQ PDF cleared.")
    return redirect(url_for('get_mcq'))

# —— download MCQ PDF ——
@app.route('/download_mcq', methods=['POST'])
def download_mcq():
    print('in download mcqs function')
    mcq_notes_id = session.get('mcq_notes_id', '')
    mcq_notes = request.form.get('mcq_notes_answer', '')

    pdf = CustomPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.add_page()
    pdf.set_font("Arial", size=14)

    lines = mcq_notes.split('\n')
    for line in lines:
        if not line.strip():
            pdf.ln(5)
            continue

        wrapped = wrap_text_line(line, max_length=100)  # 100 works well with 180mm width
        for part in wrapped:
            pdf.multi_cell(w=180, h=10, txt=part, align='L')
        pdf.ln(3)  # Space after each MCQ section

    # Output PDF to memory
    pdf_buffer = BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"{mcq_notes_id or 'mcq_output'}.pdf",
        mimetype='application/pdf'
    )

#--------------------END GENERATING MCQS-------------------------
# --------------START GENERATING FLASHCARDS-----------------------

@app.route('/flashcard_generator', methods = ['GET','POST'])
def flashcard_generator():
    if 'is_logged_in' not in session:
        flash('You need to login first', 'warning')
        return redirect('/login')
    return render_template('flashcard.html')

@app.route('/upload_flash_notes', methods=['POST'])
def upload_flash_notes():
    flash_notes_file = request.files.get('flash_notes_file')
    if not flash_notes_file or not flash_notes_file.filename.lower().endswith('.pdf'):
        print("Please upload a valid flashcard PDF.")
        return redirect(url_for('get_flash'))

    # If there's already one loaded, remove its text entry
    old_flash_notes_id = session.get('flash_id')
    if old_flash_notes_id and old_flash_notes_id in flash_notes_texts:
        del flash_notes_texts[old_flash_notes_id]

    # Save new PDF
    unique_id = str(uuid.uuid4())
    filename = secure_filename(unique_id + '.pdf')
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    flash_notes_file.save(save_path)

    # Extract text
    doc = fitz.open(save_path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    print("Text extracted from flashcard PDF for mcqs.")

    # Store and mark session
    flash_notes_texts[unique_id] = text
    session['flash_notes_id'] = unique_id

    print("PDF uploaded and indexed. You can now generate flashcards!")
    return redirect(url_for('get_flash'))


@app.route('/get_flash', methods=['GET','POST'])
def get_flash():
    print("flashcard Notes loaded")
    if 'is_logged_in' not in session:
        flash('You need to login first', 'warning')
        return redirect('/login')
    if request.method == 'POST':
        flash_notes_question = "Please generate flashcards from this text only and NO EXTRA explanation needed."
        print("flashcard question:")

        if 'flash_notes_id' in session:
            # fetch the stored text; if missing, treat as no PDF
            flash_notes_content = flash_notes_texts.get(session['flash_notes_id'], "")
            prompt = (
                "Use the following PDF content and generate Flashcards only. NO EXTRA explanation needed.:\n\n"
                f"{flash_notes_content}\n\nQuestion: {flash_notes_question}"
            )
            flash_notes_answer = ask_gemini(prompt)
            print('flashcards created.')
            return render_template( 'flashcard.html', flash_loaded=('flash_notes_id' in session), flash_notes_answer=flash_notes_answer)
        else:
            print("No PDF  for mcqs loaded. Please upload a PDF first.")
            return redirect(url_for('get_flash'))
    # GET request will render a question form
    return render_template( 'flashcard.html', flash_loaded=('flash_notes_id' in session))

@app.route('/download_flash', methods=['POST'])
def download_flash():
    print('in download flashcard function')
    flash_notes_id = session.get('flash_notes_id', '')
    flash_notes = request.form.get('flash_notes_answer', '')

    pdf = CustomPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.add_page()
    pdf.set_font("Arial", size=14)

    lines = flash_notes.split('\n')
    for line in lines:
        if not line.strip():
            pdf.ln(5)
            continue

        wrapped = wrap_text_line(line, max_length=100)  # 100 works well with 180mm width
        for part in wrapped:
            pdf.multi_cell(w=180, h=10, txt=part, align='L')
        pdf.ln(3)  # Space after each MCQ section

    # Output PDF to memory
    pdf_buffer = BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"{flash_notes_id or 'flash_output'}.pdf",
        mimetype='application/pdf'
    )

# —— clear flashcard PDF ——
@app.route('/clear_flash')
def clear_flash():
    flash_notes_id = session.pop('flash_notes_id', None)
    if flash_notes_id and flash_notes_id in flash_notes_texts:
        del flash_notes_texts[flash_notes_id]
    flash("flashcard PDF cleared.")
    return redirect(url_for('get_flash'))

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
