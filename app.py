from pathlib import Path
import os
import sqlite3
import mimetypes
import importlib
import importlib.util

from flask import Flask, jsonify, render_template, request, redirect, url_for
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Dynamically import the GenAI SDK (google.genai or genai)
genai = None
types = None
GEMINI_AVAILABLE = False

if importlib.util.find_spec("google.genai") is not None:
    genai = importlib.import_module("google.genai")
    types = importlib.import_module("google.genai.types")
    GEMINI_AVAILABLE = True
elif importlib.util.find_spec("genai") is not None:
    genai = importlib.import_module("genai")
    types = importlib.import_module("genai.types")
    GEMINI_AVAILABLE = True
else:
    # Allow the app to run without Gemini SDK; callers should check GEMINI_AVAILABLE
    print("Warning: Gemini SDK not installed; running without API access.")

# Load environment variables
env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

app = Flask(__name__)
UPLOAD_FOLDER = os.path.join("static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
DB_FILE = "nutrition.db"


# Database helper
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_name TEXT,
            image_filename TEXT,
            result TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
        )


init_db()


def get_gemini_client():
    if not GEMINI_AVAILABLE:
        raise RuntimeError("Gemini SDK not available in this environment")
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not loaded")
    return genai.Client(api_key=GEMINI_API_KEY)


def classify_image(filepath):
    if not GEMINI_AVAILABLE:
        return "other"
    try:
        client = get_gemini_client()
        with open(filepath, "rb") as f:
            image_data = f.read()
        mime_type = mimetypes.guess_type(filepath)[0] or "image/jpeg"
        image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)
        prompt = "Classify this image as fruit, meal, snack, juice, or other."
        contents = [
            types.Content(role="user", parts=[image_part, types.Part.from_text(text=prompt)])
        ]
        config = types.GenerateContentConfig()
        response = client.models.generate_content(model="gemini-2.5-flash", contents=contents, config=config)

        if getattr(response, "text", None):
            classification_text = response.text
        else:
            try:
                classification_text = response.candidates[0].content[0].text
            except Exception:
                classification_text = str(response)

        classification = classification_text.strip().lower()
        for category in ["fruit", "meal", "snack", "juice"]:
            if category in classification:
                return category
        return "other"
    except Exception as e:
        print(f"Image classification error: {e}")
        return "other"


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        food_name = request.form.get("food_name", "").lower()
        file = request.files.get("food_image")

        if not file and not food_name:
            error_message = "Please enter a food item or upload an image."
            return render_template("index.html", page="add", error=error_message)

        filename = None
        image_category = None
        image_warning = None
        filepath = None

        if file and file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)

            image_category = classify_image(filepath)
            if image_category == "other":
                image_warning = "Warning: Uploaded image is not recognized as fruit, meal, snack, or juice."
            else:
                if food_name and image_category not in food_name:
                    image_warning = "Warning: Uploaded image category differs from entered text."

        if filename and food_name:
            prompt = (
                f"Suggest 2-3 very easy, quick, home-made recipes using both the uploaded image (which is '{image_category}') "
                f"and the food name '{food_name}'. "
                "Format each recipe as HTML with: <h3>Recipe Name</h3>, <ul><li>Ingredients...</li></ul>, "
                "<b>Steps:</b>, <b>Estimated Time</b>, "
                "<b>Nutrition Tag</b> (weight/protein/fibre), <b>Who should avoid</b>."
            )
        elif filename:
            prompt = (
                f"Suggest 2-3 very easy, quick, home-made recipes for the uploaded image (which is '{image_category}'). "
                "Format each recipe as HTML with: <h3>Recipe Name</h3>, <ul><li>Ingredients...</li></ul>, "
                "<b>Steps:</b>, <b>Estimated Time</b>, <b>Nutrition Tag</b> (weight/protein/fibre), "
                "<b>Who should avoid</b>."
            )
        else:
            prompt = (
                f"Suggest 2-3 very easy, quick, home-made recipes for '{food_name}'. "
                "Format each recipe as HTML with: <h3>Recipe Name</h3>, <ul><li>Ingredients...</li></ul>, "
                "<b>Steps:</b>, <b>Estimated Time</b>, <b>Nutrition Tag</b> (weight/protein/fibre), <b>Who should avoid</b>."
            )

        try:
            if not GEMINI_AVAILABLE:
                raise RuntimeError("Gemini SDK not available")
            client = get_gemini_client()
            contents = []
            if filename and filepath:
                with open(filepath, "rb") as f:
                    image_data = f.read()

                image_part = types.Part.from_bytes(
                    data=image_data, mime_type=file.mimetype or mimetypes.guess_type(filepath)[0] or "image/jpeg"
                )
                contents = [types.Content(role="user", parts=[image_part, types.Part.from_text(text=prompt)])]
            else:
                contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]

            config = types.GenerateContentConfig()  # use defaults instead of invalid thinking_budget
            response = client.models.generate_content(
                model="gemini-2.5-flash", contents=contents, config=config
            )

            # safe extraction for main response
            if getattr(response, "text", None):
                result = response.text
            else:
                try:
                    result = response.candidates[0].content[0].text
                except Exception:
                    result = str(response)
        except Exception as e:
            result = f"Gemini API Error: {str(e)}"

        with get_db() as conn:
            conn.execute(
                "INSERT INTO chats (food_name, image_filename, result) VALUES (?, ?, ?)",
                (food_name, filename, result),
            )
            chat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        return redirect(url_for('chat_detail', chat_id=chat_id))

    return render_template('index.html', page='add')


@app.route('/chat/<int:chat_id>')
def chat_detail(chat_id):
    with get_db() as conn:
        chat = conn.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
    return render_template("index.html", page="view", chat=chat)


@app.route("/history")
def history():
    with get_db() as conn:
        chats = conn.execute(
            "SELECT id, food_name, image_filename, result, timestamp FROM chats ORDER BY id DESC"
        ).fetchall()
    return render_template("index.html", page="history", chats=chats)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)

