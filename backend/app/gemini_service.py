import google.generativeai as genai

from app.config import GEMINI_API_KEY


def _get_model():
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel("gemini-2.0-flash")


def chat(message: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured. Add it to backend/.env")

    model = _get_model()
    response = model.generate_content(message)
    return response.text
