from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os, fitz, whisper
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from textblob import TextBlob as textblob

app= Flask(__name__)
CORS(app)

#---configuration---
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:root@localhost/brainybot'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

db = SQLAlchemy()

#---MODELS---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(70), nullable=False)
    email = db.Column(db.String(80), nullable=False, unique=True)
    password = db.Column(db.String(40), nullable=False)

class document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable = False)
    filename = db.Column(db.String(120), nullable = False)
    processed_text = db.Column(db.Text, nullable = False)

#---ROUTES---

@app.route('/')
def index():
    return render_template('index.html')

@app.route("/user/register", methods = ["POST"])
def register():
    data = request.json
    hashed_pwd = generate_password_hash(data['password'])
    new_user = User(username=data['username'], email=data['email'], password=hashed_pwd)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "User registered successfully"})

@app.route("/user/login", methods = ["POST"])
def login():
    data = request.json
    user = User.query.filter_by(email = data['email']).first()
    if user and check_password_hash(User.password, data['password']):
        return jsonify({"message": "Login Successful", "user_id": User.id})
    else:
        return jsonify({"message": "Invalid credentials"}), 401

@app.route("/pdf/upload", methods = ["POST"])
def upload_pdf():
    user_id = request.form['user_id']
    file = request.files['file']
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(path)

    text = ""
    try:
        with fitz.open(path) as doc:
            for page in doc:
                text += page.get_text()
    except Exception as e:
        return jsonify({"error": "Failed to process PDF", "details": str(e)}), 500
    
    document = document(user_id=user_id, filename=file.filename, processed_text=text)
    db.session.add(document)
    db.session.commit()
    return jsonify({"message": "PDF uploaded successfully","text": text[:500]})


@app.route("/youtube/transcribe", methods = ["POST"])
def transcribe_youtube():
    url = request.json["url"]
    os.system(f' yt-dlp -x -- audio-format mp3 -o video.mp3 "{url}"')
    model = whisper.load_model("base")
    result = model.transcribe("video.mp3")
    return jsonify({"transcription": result["text"][:1000]})


@app.route("/summarize", methods = ["POST"])
def summarize():
    text = request.json["text"]
    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = LsaSummarizer()
    summary =  summarizer(parser.document, 5)
    return jsonify({"summary": " ".join(str(s) for s in summary)})


@app.route("/mcq", methods = ["POST"])
def mcq():
    text = request.json["text"]
    blob = textblob(text)
    keywords = [word for word, tag in blob.tags if tag == "NN"]
    mcqs = [{"q": f"What is {word}?", "a": "A"} for word in keywords[:5]]
    return jsonify({"MCQs": mcqs})


@app.route("/flashcards", methods = ["POST"])
def flashcards():
    text = request.json["text"]
    words = text.split()[:5]
    flashcards = [{"text": word , "definition": f"Explain{word}"} for word in words]
    return jsonify({"flashcards": flashcards})

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)