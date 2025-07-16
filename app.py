import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
import google.generativeai as genai
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import markdown


app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configure Gemini AI
genai.configure(api_key='AIzaSyBIqp4jVqPRuWcUnZVoQuVzW-UtUIrM2vI')
gemini_model = genai.GenerativeModel('gemini-2.0-flash')

# Database Initialization
def init_db():
    with sqlite3.connect('user_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER,
            question_id INTEGER,
            answer TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            PRIMARY KEY(user_id, question_id))''')

init_db()

# Personalization Questions
PERSONALIZATION_QUESTIONS = [
    {'id': 1, 'question': 'What is your primary hobby or interest?', 'options': ['Reading', 'Sports', 'Music', 'Traveling']},
    {'id': 2, 'question': 'What is your highest level of education?', 'options': ['High School', "Bachelor's Degree", "Master's Degree", 'PhD']},
    {'id': 3, 'question': 'What type of entertainment do you prefer?', 'options': ['Movies', 'TV Shows', 'Video Games', 'Books']},
    {'id': 4, 'question': 'How do you prefer to spend your weekends?', 'options': ['Socializing with friends', 'Relaxing at home', 'Exploring new places', 'Working on personal projects']},
    {'id': 5, 'question': 'What is your favorite type of cuisine?', 'options': ['Italian', 'Asian', 'Mexican', 'American']},
    {'id': 6, 'question': 'Which learning style suits you best?', 'options': ['Visual', 'Auditory', 'Reading/Writing', 'Hands-on']},
    {'id': 7, 'question': 'What is your preferred work environment?', 'options': ['Office', 'Remote', 'Hybrid', 'Coworking space']},
    {'id': 8, 'question': 'How do you prefer to exercise?', 'options': ['Gym workouts', 'Outdoor activities', 'Team sports', 'Yoga/Pilates']},
    {'id': 9, 'question': 'What type of music do you enjoy most?', 'options': ['Pop', 'Rock', 'Classical', 'Hip-hop']},
    {'id': 10, 'question': 'How would you describe your social media usage?', 'options': ['Heavy user', 'Moderate user', 'Light user', 'Rarely use']},
]

@app.route('/')
def index():
    return redirect(url_for('dashboard')) if 'user_id' in session else render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        email = request.form['email']
        phone = request.form.get('phone', '')

        try:
            with sqlite3.connect('user_data.db') as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO users (username, password, email, phone) VALUES (?, ?, ?, ?)',
                               (username, password, email, phone))
                session['user_id'] = cursor.lastrowid
                session['username'] = username
                return redirect(url_for('personalize'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists!', 'error')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with sqlite3.connect('user_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, username, password FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()

        if user and check_password_hash(user[2], password):
            session['user_id'], session['username'] = user[0], user[1]
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!', 'error')

    return render_template('index.html')

@app.route('/personalize', methods=['GET', 'POST'])
def personalize():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        with sqlite3.connect('user_data.db') as conn:
            cursor = conn.cursor()
            for q in PERSONALIZATION_QUESTIONS:
                ans = request.form.get(f'question_{q["id"]}')
                if ans:
                    cursor.execute('INSERT INTO user_preferences (user_id, question_id, answer) VALUES (?, ?, ?)',
                                   (session['user_id'], q['id'], ans))
        return redirect(url_for('dashboard'))

    return render_template('personalize.html', questions=PERSONALIZATION_QUESTIONS)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=session['username'])

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    response_text = query = ''

    if request.method == 'POST':
        query = request.form['query']
        with sqlite3.connect('user_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT question_id, answer FROM user_preferences WHERE user_id = ?', (session['user_id'],))
            preferences = cursor.fetchall()

        prompt = "Here are some quick preferences about the user:\n"
        for qid, answer in preferences:
            question = next((q['question'] for q in PERSONALIZATION_QUESTIONS if q['id'] == qid), '')
            prompt += f"- {question}: {answer}\n"

        prompt += (
            f"\nNow respond to this message: \"{query}\"\n"
            "Provide a helpful, friendly, and informative response in 5–7 lines. Consider the user's preferences while answering. If applicable, include examples, suggestions, or a brief explanation."
            "Focus on being helpful and engaging in 4-5 lines max."
        )

        try:
            response = gemini_model.generate_content(prompt)
            # response_text = response.text
            response_text = markdown.markdown(response.text)
        except Exception as e:
            response_text = f"Gemini API Error: {str(e)}"

    return render_template('chat.html', response=response_text, query=query, now=datetime.now())


@app.route('/text_summarize', methods=['GET', 'POST'])
def text_summarize():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    summary, original_text, format_choice, summary_length = '', '', 'bullets', 'medium'

    if request.method == 'POST':
        original_text = request.form['text']
        format_choice = request.form.get('format', 'bullets')
        summary_length = request.form.get('length', 'medium')

        prompt = (
            f"You are a smart summarization assistant. Summarize the following text into a {summary_length} "
            f"{'bullet-point list' if format_choice == 'bullets' else 'paragraph'}, focusing on key information:\n\n"
            f"{original_text}"
        )

        try:
            summary = markdown.markdown(gemini_model.generate_content(prompt).text)
        except Exception as e:
            summary = f"<p><strong>Gemini API Error:</strong> {str(e)}</p>"

    return render_template('text_summarize.html', summary=summary, original_text=original_text,
                           format_choice=format_choice, summary_length=summary_length)


@app.route('/video_summarize', methods=['GET', 'POST'])
def video_summarize():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    summary, video_url, transcript = '', '', ''

    if request.method == 'POST':
        video_url = request.form['video_url']
        transcript = request.form.get('transcript', '').strip()

        if transcript:
            prompt = (
                "You are a smart assistant. Summarize the following video transcript into 5–7 concise bullet points, "
                "focusing on key ideas, conclusions, or instructions:\n\n"
                f"{transcript}"
            )

            try:
                summary = markdown.markdown(gemini_model.generate_content(prompt).text)
            except Exception as e:
                summary = f"<p><strong>Gemini API Error:</strong> {str(e)}</p>"
        else:
            summary = "<p><strong>Transcript is required to generate a summary. Please paste it above.</strong></p>"

    return render_template('video_summarize.html', summary=summary, video_url=video_url, transcript=transcript)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)