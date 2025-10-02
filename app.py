from flask import Flask, render_template, request
import pandas as pd
from Questgen.QGen import QGen
import nltk
nltk.download('punkt')

app = Flask(__name__)

# Load questions from CSV (kept for fallback or other use)
df = pd.read_csv("questions.csv")

# Initialize Questgen Question Generator
qg = QGen()

@app.route('/')
def home():
    subjects = df['subject'].unique()
    difficulties = df['difficulty'].unique()
    return render_template('index.html', subjects=subjects, difficulties=difficulties)

@app.route('/generate', methods=['POST'])
def generate():
    # Optionally get inputs for Questgen from the form (e.g. text or subject)
    input_text = request.form.get('input_text')  # A text paragraph for question generation
    num_questions = int(request.form.get('num_questions', 5))

    if input_text:
        # Generate questions dynamically using Questgen
        payload = {"input_text": input_text}
        result = qg.predict_shortq(payload)

        questions_list = result.get('questions', [])[:num_questions]

        # Format questions if needed for rendering (e.g., topic and marks defaulted)
        questions_list = [(q, "", "") for q in questions_list]
    else:
        # Fallback: Filter from CSV based on subject and difficulty
        subject = request.form.get('subject')
        difficulty = request.form.get('difficulty')
        filtered_df = df[(df['subject'] == subject) & (df['difficulty'] == difficulty)]
        selected_questions = filtered_df.sample(n=min(num_questions, len(filtered_df)), random_state=42)
        questions_list = selected_questions[['question', 'topic', 'marks']].values.tolist()

    return render_template('paper.html', questions=questions_list)

if __name__ == "__main__":
    app.run(debug=True)
