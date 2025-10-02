from flask import Flask, render_template, request
import nltk
from generator import allocate_questions

# Try to import Questgen; if unavailable, we'll use a local fallback
qg = None
try:
	from Questgen import main as questgen_main  # type: ignore
	qg = questgen_main.QGen()
except Exception:
	try:
		from Questgen.QGen import QGen as _QGen  # type: ignore
		qg = _QGen()
	except Exception:
		try:
			from questgen.qgen import QGen as _QGen  # type: ignore
			qg = _QGen()
		except Exception:
			qg = None

nltk.download('punkt')

def generate_fallback_questions(input_text: str, desired_count: int, subject_hint: str = "") -> list:
    import re
    
    # Extract the core subject from input
    text = (input_text or subject_hint or "").strip()
    # Clean up the text
    normalized = re.sub(r"\b\d+\b", " ", text, flags=re.IGNORECASE)
    normalized = re.sub(r"\bquestions?\b", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bof\b", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    
    # Map to specific Software Engineering topics
    se_topics = {
        "software engineering": [
            "Explain the Software Development Life Cycle (SDLC) phases with their key deliverables.",
            "Compare Waterfall, Agile, and Spiral models. When would you use each?",
            "What are functional vs non-functional requirements? Give examples of each.",
            "Explain Use Case diagrams and Sequence diagrams with a login example.",
            "Define software testing levels: unit, integration, system, and acceptance testing.",
            "What is the difference between verification and validation in software testing?",
            "Explain the concepts of coupling and cohesion in software design.",
            "Describe the SOLID principles with brief examples.",
            "What are design patterns? Explain Factory and Observer patterns.",
            "Compare Black-box, White-box, and Gray-box testing techniques.",
            "Explain Continuous Integration and Continuous Deployment (CI/CD).",
            "What are the key challenges in software project management?",
            "Describe software maintenance types and their characteristics.",
            "Explain software metrics and their importance in quality assurance.",
            "What is software configuration management? Why is it important?"
        ],
        "data structures": [
            "Compare time complexity of different sorting algorithms (Bubble, Quick, Merge).",
            "Explain the difference between arrays and linked lists with their trade-offs.",
            "Describe stack and queue data structures with real-world applications.",
            "What is a binary tree? Explain different tree traversal methods.",
            "Compare hash tables with other data structures for search operations.",
            "Explain the concept of Big O notation with examples.",
            "Describe dynamic programming with a classic example.",
            "What are graphs? Explain BFS and DFS algorithms.",
            "Compare different tree structures: BST, AVL, and Red-Black trees.",
            "Explain the heap data structure and its applications."
        ],
        "database": [
            "Explain ACID properties in database transactions.",
            "Compare SQL and NoSQL databases with their use cases.",
            "What is database normalization? Explain 1NF, 2NF, and 3NF.",
            "Describe different types of database relationships with examples.",
            "Explain database indexing and its impact on query performance.",
            "What are database triggers and stored procedures?",
            "Compare different database models: relational, hierarchical, and network.",
            "Explain database backup and recovery strategies.",
            "What is database concurrency control? Explain locking mechanisms.",
            "Describe database security measures and access control."
        ]
    }
    
    # Find matching topic
    core_subject = normalized.lower()
    questions = []
    
    for topic, topic_questions in se_topics.items():
        if topic in core_subject or any(word in core_subject for word in topic.split()):
            questions = topic_questions[:desired_count]
            break
    
    # If no specific topic found, use general software engineering questions
    if not questions:
        questions = se_topics["software engineering"][:desired_count]
    
    # Ensure we have the right number of questions
    while len(questions) < desired_count:
        questions.append(f"Explain a key concept in {normalized or 'software engineering'}.")
    
    return [(q, normalized.title() if normalized else (subject_hint or "Software Engineering"), "") for q in questions[:desired_count]]

app = Flask(__name__)

# qg is initialized above; may be None if Questgen not available

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    # Optionally get inputs for Questgen from the form (e.g. text or subject)
    input_text = request.form.get('input_text')  # A text paragraph for question generation
    num_questions = int(request.form.get('num_questions', 5))

    # AI-only fields
    total_marks = int(request.form.get('total_marks', 0) or 0)
    subject = request.form.get('subject') or request.form.get('prompt_subject') or "General"

    if input_text:
        # Generate questions dynamically using Questgen if available, else fallback
        if qg is not None:
            payload = {"input_text": input_text}
            result = qg.predict_shortq(payload)
            questions_list = result.get('questions', [])[:num_questions]
            questions_list = [(q, "", "") for q in questions_list]
        else:
            # Local fallback: generate multiple quiz-style questions from text
            questions_list = generate_fallback_questions(input_text, num_questions, subject_hint=subject or "")
    else:
        # Always AI generation when text is empty; build a prompt from subject + difficulty
        force_ai = True
        prompt_parts = [p for p in [subject, request.form.get('difficulty')] if p]
        prompt = ", ".join(prompt_parts) or (subject or "General")
        if qg is not None:
            payload = {"input_text": prompt}
            result = qg.predict_shortq(payload)
            raw = result.get('questions', [])[:num_questions]
            questions_list = [(q, subject or "", "") for q in raw]
        else:
            questions_list = generate_fallback_questions(prompt, num_questions, subject_hint=subject or "")

    return render_template('paper.html', questions=questions_list)

if __name__ == "__main__":
    app.run(debug=True)
