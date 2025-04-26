import os
import uuid
import fitz
from flask import Flask, render_template, request, redirect,url_for, session, flash
from werkzeug.utils import secure_filename
from chatbot import ask_gemini
import whisper
import yt_dlp
from fpdf import FPDF
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY']   = os.getenv('SECRET_KEY')
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# In‑memory store of extracted PDF text
pdf_texts = {}

# ——— existing routes ———
@app.route('/')
def home():
    pdf_loaded = ("pdf_uuid" in session)
    return render_template('home.html', pdf_loaded=pdf_loaded)

'''
def index():
    # Tell template if a PDF is loaded
    pdf_loaded = ("pdf_uuid" in session)
    return render_template('index.html', pdf_loaded=pdf_loaded)
'''

@app.route('/about')
def about():
    return render_template('about.html')

#------START CHAT WITH PDF implementation--------
@app.route('/ask', methods=['POST'])
def ask():
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


# —— New: upload PDF ——
@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    file = request.files.get('pdf')
    if not file or not file.filename.lower().endswith('.pdf'):
        flash("Please upload a valid PDF.")
        return redirect(url_for('home'))

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

    flash("PDF uploaded and indexed. You can now ask questions about it!")
    return redirect(url_for('home'))


# —— Optional: clear PDF ——
@app.route('/clear_pdf')
def clear_pdf():
    pdf_id = session.pop('pdf_uuid', None)
    if pdf_id and pdf_id in pdf_texts:
        del pdf_texts[pdf_id]
    flash("PDF context cleared.")
    return redirect(url_for('home'))
#------END CHAT WITH PDF implementation--------

#------START CHAT WITH YOUTUBE implementation--------

@app.route('/youtube')
def youtube():
    return render_template('youtube.html')

@app.route('/process_youtube', methods=['POST'])
def process_youtube():
    url = request.form.get('youtube_url')
    if not url:
        flash("Please enter a valid YouTube URL.")
        return redirect(url_for('youtube'))

    # Extract YouTube ID
    import re
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if not match:
        flash("Invalid YouTube URL.")
        return redirect(url_for('youtube'))

    video_id = match.group(1)

    # Paths
    audio_filename = f"{video_id}"
    audio_path = os.path.join("uploads", audio_filename)
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


    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        flash(f"Error downloading video: {e}")
        return redirect(url_for('youtube'))


    # Transcribe using Whisper
    try:
        model = whisper.load_model("base")
        result = model.transcribe(audio_path)
        transcript = result["text"]

    except Exception as e:
        flash(f"Error transcribing video: {e}")
        return redirect(url_for('youtube'))

    # Save transcript in session and file
    session['youtube_transcript'] = transcript
    session['youtube_video_id'] = video_id

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

    flash("Transcription complete. Ask your questions!")
    return render_template('youtube.html', video_id=video_id)

@app.route('/ask_youtube', methods=['POST'])
def ask_youtube():
    question = request.form.get('question')
    transcript = session.get(session['youtube_transcript'])
    video_id = session.get(session['youtube_video_id'])

    if not transcript or not video_id:
        flash("No transcript found. Please upload a video first.")
        return redirect(url_for('youtube'))

    prompt = (
        "Use the following YouTube video transcript to answer the question:\n\n"
        f"{transcript}\n\nQuestion: {question}"
    )

    answer = ask_gemini(prompt)

    return render_template(
        'youtube.html',
        video_id=video_id,
        answer=answer
    )

@app.route('/download_transcript')
def download_transcript():
    video_id = session.get('youtube_video_id')
    if not video_id:
        flash("No transcript to download.")
        return redirect(url_for('youtube'))

    path = f"static/downloads/{video_id}.pdf"
    if not os.path.exists(path):
        flash("Transcript file not found.")
        return redirect(url_for('youtube'))

    return redirect(f"/{path}")


if __name__ == '__main__':
    app.run(debug=True)
