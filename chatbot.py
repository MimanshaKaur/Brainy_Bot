import google.generativeai as genai
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
# Configure Gemini (Bard) API key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def ask_gemini(question):
    """
    Send a user question to Gemini 1.5 Flash and return the response text.
    """
    model = genai.GenerativeModel('gemini-1.5-flash')
    chat = model.start_chat()
    response = chat.send_message(question)
    return response.text