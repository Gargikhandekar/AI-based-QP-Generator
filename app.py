from flask import Flask, render_template, request, send_file, make_response, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, SelectField, IntegerField
from wtforms.validators import DataRequired, Email, Length, EqualTo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import nltk
from generator import allocate_questions
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from docx import Document
from docx.shared import Inches
import io
import tempfile
import os
import openai
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

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
nltk.download('stopwords')

# Enhanced options templates with realistic alternatives
mcq_options_templates = {
    "software engineering": {
        "performance": ["Improved system speed", "Reduced memory usage", "Better user experience", "Enhanced security"],
        "scalability": ["Handling increased load", "Reducing complexity", "Improving reliability", "Enhancing maintainability"],
        "maintainability": ["Easier code updates", "Better performance", "Reduced costs", "Improved security"],
        "reliability": ["System stability", "Better performance", "Easier testing", "Reduced complexity"]
    },
    "data architecture": {
        "performance": ["Faster data processing", "Reduced storage costs", "Better data quality", "Improved security"],
        "scalability": ["Handling data growth", "Reducing complexity", "Improving reliability", "Enhancing flexibility"],
        "governance": ["Data quality control", "Performance optimization", "Cost reduction", "User experience"],
        "integration": ["System connectivity", "Data consistency", "Performance improvement", "Security enhancement"]
    },
    "data structures": {
        "time_complexity": ["O(1) constant time", "O(log n) logarithmic", "O(n) linear time", "O(n²) quadratic"],
        "space_complexity": ["O(1) constant space", "O(n) linear space", "O(log n) logarithmic", "O(n²) quadratic"],
        "access_pattern": ["Random access", "Sequential access", "Indexed access", "Hash-based access"],
        "use_case": ["Search operations", "Sorting algorithms", "Memory management", "Network protocols"]
    },
    "database": {
        "performance": ["Query optimization", "Data compression", "Index management", "Connection pooling"],
        "consistency": ["ACID properties", "Data integrity", "Transaction management", "Concurrency control"],
        "scalability": ["Horizontal scaling", "Vertical scaling", "Load balancing", "Data partitioning"],
        "security": ["Access control", "Data encryption", "Audit logging", "Backup strategies"]
    }
}

# Load environment variables for API keys
load_dotenv()

# Initialize OpenAI client
openai_client = None
try:
    openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
except Exception as e:
    print(f"OpenAI client initialization failed: {e}")
    openai_client = None

def generate_fallback_questions(input_text: str, desired_count: int, subject_hint: str = "", question_type: str = "short_answer") -> list:
    import re
    import random
    
    # Normalize inputs
    text = (input_text or subject_hint or "").strip()
    normalized = re.sub(r"\s+", " ", text)
    subject_key = normalized.lower()

    # Subtopic pools by subject
    subject_to_subtopics = {
        "software engineering": [
            "SDLC phases", "requirements (functional vs non-functional)", "UML (use case, sequence)",
            "testing levels", "verification vs validation", "coupling vs cohesion",
            "SOLID principles", "design patterns", "CI/CD", "project management", "metrics", "configuration management"
        ],
        "data structures": [
            "array vs linked list", "stack and queue", "binary trees and traversals",
            "hash tables", "Big O notation", "dynamic programming", "graphs (BFS/DFS)",
            "balanced trees (AVL/RB)", "heaps"
        ],
        "database": [
            "ACID properties", "SQL vs NoSQL", "normalization (1NF/2NF/3NF)", "relationships",
            "indexing", "triggers and stored procedures", "database models", "backup and recovery",
            "concurrency control", "security and access control"
        ],
        "data architecture": [
            "enterprise data strategy", "conceptual/logical/physical models", "data lake vs warehouse vs lakehouse",
            "batch vs streaming pipelines", "data mesh", "data governance (ownership, lineage, catalog)",
            "analytical schema (star vs snowflake)", "data quality dimensions", "medallion architecture",
            "CDC patterns"
        ]
    }

    # Difficulty tuning tokens
    difficulty = "medium"
    # Try to detect difficulty from text if provided
    if re.search(r"\b(easy|beginner)\b", subject_key):
        difficulty = "easy"
    elif re.search(r"\b(advanced|hard|difficult)\b", subject_key):
        difficulty = "hard"

    # Pick subject by fuzzy match of keys
    def pick_subject(key: str) -> str:
        if not key:
            return "software engineering"
        for s in subject_to_subtopics.keys():
            if s in key:
                return s
        # fallback simple heuristics
        if any(w in key for w in ["db", "sql", "database"]):
            return "database"
        if any(w in key for w in ["data architecture", "lakehouse", "warehouse", "pipeline", "governance", "mesh"]):
            return "data architecture"
        if any(w in key for w in ["stack", "queue", "tree", "graph", "algorithm"]):
            return "data structures"
        return "software engineering"

    chosen_subject = pick_subject(subject_key)
    subtopics = subject_to_subtopics.get(chosen_subject, subject_to_subtopics["software engineering"])[:]

    # Question templates with placeholders
    templates_easy = [
        "Define {topic} in the context of {subject}.",
        "List key characteristics of {topic}.",
        "Give a simple example that illustrates {topic}.",
        "Why is {topic} important in {subject}?"
    ]
    templates_medium = [
        "Compare and contrast {topic} with a closely related concept in {subject}.",
        "Explain how {topic} impacts design decisions in {subject}.",
        "Describe a real-world scenario where {topic} is applied.",
        "Identify common pitfalls when working with {topic} and how to avoid them."
    ]
    templates_hard = [
        "Evaluate trade-offs of alternative approaches to {topic} in {subject}.",
        "Design a solution that incorporates {topic} and justify the choices.",
        "Propose metrics to assess effectiveness of {topic} in practice.",
        "Explain how {topic} scales and what bottlenecks may arise."
    ]
    
    # Enhanced MCQ templates with subject-specific content
    mcq_templates = {
        "software engineering": [
            "Which of the following is the most appropriate use case for the {topic} design pattern?",
            "In the context of {subject}, what is the primary benefit of implementing {topic}?",
            "Which statement best describes the relationship between {topic} and software quality?",
            "When designing a system that uses {topic}, which consideration is most critical?",
            "Which of the following is NOT a valid application of {topic} in {subject}?",
            "What is the main challenge associated with implementing {topic} in large-scale systems?",
            "In {subject}, {topic} is most commonly used to address which problem?",
            "Which factor is most important when evaluating the effectiveness of {topic}?"
        ],
        "data architecture": [
            "In a data architecture context, which approach best describes {topic}?",
            "What is the primary advantage of using {topic} in enterprise data management?",
            "Which of the following scenarios would most benefit from implementing {topic}?",
            "In data architecture, {topic} is primarily used to solve which problem?",
            "Which statement accurately describes the role of {topic} in data governance?",
            "What is the main consideration when designing a system that incorporates {topic}?",
            "Which of the following is NOT a characteristic of effective {topic} implementation?",
            "In the context of data architecture, {topic} is most closely related to which concept?"
        ],
        "data structures": [
            "Which of the following best describes the time complexity of {topic} operations?",
            "In what scenario would you choose {topic} over alternative data structures?",
            "Which statement accurately describes the space complexity of {topic}?",
            "What is the primary advantage of using {topic} for this specific use case?",
            "Which of the following is NOT a valid operation on {topic}?",
            "When implementing {topic}, which consideration is most important for performance?",
            "Which data structure would be most appropriate as an alternative to {topic}?",
            "What is the main limitation of {topic} in certain applications?"
        ],
        "database": [
            "In database design, which principle is most relevant to {topic}?",
            "What is the primary purpose of {topic} in database management systems?",
            "Which of the following scenarios would most benefit from {topic}?",
            "In the context of database optimization, {topic} is used to address which issue?",
            "Which statement best describes the impact of {topic} on query performance?",
            "What is the main consideration when implementing {topic} in a distributed database?",
            "Which of the following is NOT a valid application of {topic} in database systems?",
            "In database architecture, {topic} is most closely related to which concept?"
        ]
    }

    # Seed with topics extracted from input text
    extra_topics = []
    if input_text:
        extra_topics = extract_topics_from_text(input_text, max_topics=12)

    pool = subtopics + extra_topics
    if not pool:
        pool = ["core concepts"]

    # Build unique questions based on type
    questions = []
    used = set()
    attempts = 0
    
    while len(questions) < desired_count and attempts < desired_count * 10:
        attempts += 1
        topic = random.choice(pool)
        
        if question_type == "mcq":
            # Generate MCQ using subject-specific templates
            subject_templates = mcq_templates.get(chosen_subject, mcq_templates["software engineering"])
            template = random.choice(subject_templates)
            question_text = template.format(topic=topic, subject=chosen_subject)
            
            # Get realistic options based on subject and topic
            options = generate_realistic_mcq_options(chosen_subject, topic, template)
            
            # Format MCQ
            correct_answer = random.choice(['A', 'B', 'C', 'D'])
            q = f"{question_text}\nA) {options[0]}\nB) {options[1]}\nC) {options[2]}\nD) {options[3]}\nCorrect Answer: {correct_answer}"
            
        elif question_type == "mixed":
            # Randomly choose between short answer and MCQ
            if random.choice([True, False]):
                # Short answer
                if difficulty == "easy":
                    templates = templates_easy
                elif difficulty == "hard":
                    templates = templates_hard
                else:
                    templates = templates_medium
                template = random.choice(templates)
                q = template.format(topic=topic, subject=chosen_subject)
            else:
                # MCQ
                subject_templates = mcq_templates.get(chosen_subject, mcq_templates["software engineering"])
                template = random.choice(subject_templates)
                question_text = template.format(topic=topic, subject=chosen_subject)
                options = generate_realistic_mcq_options(chosen_subject, topic, template)
                correct_answer = random.choice(['A', 'B', 'C', 'D'])
                q = f"{question_text}\nA) {options[0]}\nB) {options[1]}\nC) {options[2]}\nD) {options[3]}\nCorrect Answer: {correct_answer}"
        else:
            # Short answer
            if difficulty == "easy":
                templates = templates_easy
            elif difficulty == "hard":
                templates = templates_hard
            else:
                templates = templates_medium
            template = random.choice(templates)
            q = template.format(topic=topic, subject=chosen_subject)
        
        if q.lower() in used:
            continue
        used.add(q.lower())
        questions.append(q)

    # If still short, backfill with generic prompts
    while len(questions) < desired_count:
        if question_type == "mcq":
            questions.append(f"Which of the following best describes a key concept in {chosen_subject}?\nA) Option A\nB) Option B\nC) Option C\nD) Option D\nCorrect Answer: A")
        else:
            questions.append(f"Discuss a key concept in {chosen_subject} and its practical implications.")

    # Build concise subject/topics summary for display
    topics_summary = ", ".join(t.title() for t in pool[:5]) if pool else chosen_subject.title()
    display_subject = subject_hint or topics_summary or chosen_subject.title()
    # Return tuples: (question, subject/topics summary, difficulty)
    return [(q, display_subject, difficulty) for q in questions[:desired_count]]

def extract_topics_from_text(text: str, max_topics: int = 12) -> list:
    """Extract salient topics/phrases from raw text using simple statistical heuristics.
    Avoids heavy POS taggers to keep dependencies light.
    """
    import re
    from collections import Counter
    from nltk.corpus import stopwords

    if not text:
        return []

    stop = set(stopwords.words('english'))
    # Basic cleanup
    cleaned = re.sub(r"[^A-Za-z0-9\-\s]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Candidate words (exclude short/common tokens)
    tokens = [t.lower() for t in cleaned.split(" ") if len(t) > 2 and t.lower() not in stop]

    # Build bigrams for more specific topics
    bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)
               if tokens[i] not in stop and tokens[i+1] not in stop]

    # Count frequencies
    unigram_counts = Counter(tokens)
    bigram_counts = Counter(bigrams)

    # Boost bigrams so they rank higher than generic singletons
    scored = {}
    for term, c in unigram_counts.items():
        scored[term] = scored.get(term, 0) + c
    for term, c in bigram_counts.items():
        scored[term] = scored.get(term, 0) + c * 2

    # Promote Title-Case phrases (likely proper topics) found in original text
    title_phrases = re.findall(r"(?:[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)", text)
    for phrase in title_phrases:
        key = phrase.strip().lower()
        scored[key] = scored.get(key, 0) + 3

    # Sort by score and length to prefer informative phrases
    candidates = sorted(scored.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)

    topics = []
    seen = set()
    for term, _ in candidates:
        # Skip overly generic terms
        if term in seen or term in {"introduction", "summary", "conclusion", "overview"}:
            continue
        seen.add(term)
        topics.append(term)
        if len(topics) >= max_topics:
            break
    return topics

def generate_ai_questions_openai(input_text: str, num_questions: int, subject: str = "", difficulty: str = "medium", total_marks: int = 0, question_type: str = "short_answer", topics: list | None = None) -> list:
    """Generate questions using OpenAI API"""
    if not openai_client:
        return []
    
    # Calculate marks per question if total marks specified
    marks_info = ""
    if total_marks > 0:
        marks_per_question = total_marks // num_questions
        remaining_marks = total_marks % num_questions
        marks_info = f" (Total marks: {total_marks}, approximately {marks_per_question} marks per question)"
    
    # Determine question format with enhanced instructions
    if question_type == "mcq":
        format_instruction = "Format your response as a JSON array of objects, where each object has 'question' (string), 'options' (array of 4 strings), and 'correct_answer' (string)."
        question_instruction = """Generate high-quality multiple choice questions with these requirements:
- Each question should test specific knowledge or understanding
- Provide 4 realistic options (A, B, C, D) where only one is clearly correct
- Make incorrect options plausible but definitively wrong
- Avoid obvious or trivial questions
- Include questions that test application, analysis, and evaluation
- Ensure questions are appropriate for the specified difficulty level
- Make options similar in length and complexity to avoid obvious answers"""
    elif question_type == "mixed":
        format_instruction = "Format your response as a JSON array of objects, where each object has 'question' (string), 'type' ('short_answer' or 'mcq'), and if type is 'mcq', also include 'options' (array of 4 strings) and 'correct_answer' (string)."
        question_instruction = """Generate a mix of high-quality short answer questions and multiple choice questions:
- Short answer questions should require explanation, analysis, or problem-solving
- MCQs should have 4 realistic options with only one correct answer
- Ensure variety in question types and difficulty levels
- Make questions test different cognitive levels (knowledge, comprehension, application, analysis)"""
    else:  # short_answer
        format_instruction = "Format your response as a JSON array of strings, where each string is a complete question."
        question_instruction = "Generate short answer questions that require explanation, analysis, or problem-solving."
    
    # Build the prompt
    topics_clause = ""
    if topics:
        topics_clause = "\nKey topics to prioritize (ordered):\n- " + "\n- ".join(topics[:12]) + "\n"
    if input_text:
        prompt = f"""Based on the following source text about {subject or 'the topic'}, generate {num_questions} high-quality questions that test understanding at {difficulty} level{marks_info}.

Text: {input_text}

Instructions:
- Use the source text faithfully. Prefer the following topics if relevant:
{topics_clause}
- Avoid trivial definitions. Include application and analysis where possible.
- Vary verbs and cognitive levels (Bloom's taxonomy).
- Use precise technical terminology from the text.
- Keep each question self-contained and unambiguous.
- {question_instruction}

{format_instruction}"""
    else:
        prompt = f"""Generate {num_questions} high-quality questions about {subject or 'general topics'} at {difficulty} difficulty level{marks_info}.

The questions should:
- Be clear and specific
- Test both conceptual understanding and practical application
- Be appropriate for {difficulty} difficulty level
- Cover important aspects of {subject or 'the subject'}
- Be suitable for the specified mark allocation
- {question_instruction}

{format_instruction}"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert educator who creates high-quality exam questions. Always respond with valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1400,
            temperature=0.4
        )
        
        content = response.choices[0].message.content.strip()
        
        # Try to parse JSON response
        try:
            questions = json.loads(content)
            if isinstance(questions, list):
                # Process different question types
                processed_questions = []
                for q in questions[:num_questions]:
                    if isinstance(q, dict):
                        # MCQ or mixed format
                        if 'options' in q and 'correct_answer' in q:
                            # MCQ format
                            question_text = q['question']
                            options = q['options']
                            correct = q['correct_answer']
                            formatted_q = f"{question_text}\nA) {options[0]}\nB) {options[1]}\nC) {options[2]}\nD) {options[3]}\nCorrect Answer: {correct}"
                        else:
                            # Short answer format
                            formatted_q = q.get('question', str(q))
                    else:
                        # Simple string format
                        formatted_q = str(q)
                    
                    processed_questions.append(formatted_q)
                
                # Allocate marks to questions
                questions_with_marks = allocate_marks_to_questions(processed_questions, total_marks)
                return [(q, subject or "AI Generated", marks) for q, marks in questions_with_marks]
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract questions from text
            lines = content.split('\n')
            questions = []
            for line in lines:
                line = line.strip()
                if line and ('?' in line or line.startswith(('Q', 'Question'))):
                    # Clean up the line
                    q = line.replace('Q1.', '').replace('Q2.', '').replace('Q3.', '').replace('Q4.', '').replace('Q5.', '').strip()
                    if q and len(q) > 10:  # Basic quality check
                        questions.append(q)
            
            # Allocate marks to questions
            questions_with_marks = allocate_marks_to_questions(questions[:num_questions], total_marks)
            return [(q, subject or "AI Generated", marks) for q, marks in questions_with_marks]
        
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return []
    
    return []

def generate_realistic_mcq_options(subject: str, topic: str, template: str) -> list:
    """Generate realistic MCQ options based on subject, topic, and template"""
    import random
    
    # Get subject-specific options
    subject_options = mcq_options_templates.get(subject, mcq_options_templates["software engineering"])
    
    # Try to match topic to option categories
    topic_lower = topic.lower()
    matched_category = None
    
    for category in subject_options.keys():
        if category in topic_lower or any(word in topic_lower for word in category.split('_')):
            matched_category = category
            break
    
    if matched_category:
        base_options = subject_options[matched_category][:]
    else:
        # Use a random category from the subject
        base_options = random.choice(list(subject_options.values()))[:]
    
    # Create variations and ensure they're realistic
    options = []
    for i, base_option in enumerate(base_options):
        if i == 0:
            # First option is usually the most direct/obvious
            options.append(base_option)
        else:
            # Create variations that are plausible but wrong
            variations = [
                base_option.replace("improved", "reduced").replace("better", "worse"),
                base_option.replace("increased", "decreased").replace("enhanced", "diminished"),
                base_option.replace("optimized", "compromised").replace("efficient", "inefficient"),
                f"Alternative approach to {topic}",
                f"Different method for {topic}",
                f"Opposite of {base_option.lower()}",
                f"Related but incorrect concept"
            ]
            options.append(random.choice(variations))
    
    # Ensure all options are unique and realistic
    while len(set(options)) < 4:
        options = list(set(options))
        if len(options) < 4:
            options.append(f"Additional option related to {topic}")
    
    return options[:4]

def allocate_marks_to_questions(questions: list, total_marks: int) -> list:
    """Allocate marks to questions based on total marks"""
    if total_marks <= 0 or not questions:
        return [(q, "") for q in questions]
    
    num_questions = len(questions)
    base_marks = total_marks // num_questions
    extra_marks = total_marks % num_questions
    
    questions_with_marks = []
    for i, question in enumerate(questions):
        # Give extra marks to first few questions if there's a remainder
        marks = base_marks + (1 if i < extra_marks else 0)
        questions_with_marks.append((question, str(marks)))
    
    return questions_with_marks

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20 MB upload limit

ALLOWED_EXTENSIONS = {'.pdf', '.ppt', '.pptx'}

def allowed_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_stream: io.BytesIO) -> str:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_stream)
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or '')
        return '\n'.join(texts).strip()
    except Exception as e:
        print(f"PDF extract error: {e}")
        return ''

def extract_text_from_pptx(file_stream: io.BytesIO) -> str:
    try:
        from pptx import Presentation
        prs = Presentation(file_stream)
        texts = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, 'text'):
                    texts.append(shape.text)
        return '\n'.join(texts).strip()
    except Exception as e:
        print(f"PPTX extract error: {e}")
        return ''

def clean_extracted_text(text: str) -> str:
    """Remove obvious metadata like instructor names, dates, contacts, and headers.
    Keeps only substantive content lines.
    """
    import re
    if not text:
        return text
    noise_patterns = [
        r"professor|associate|assistant|faculty|instructor|dr\.|mr\.|ms\.|mrs\.|prof\.",
        r"department|dept\.|school of|college of|university|institute|campus",
        r"contact|phone|mobile|email|mailto|www\.|http[s]?://",
        r"^\s*page\s+\d+|^\s*\d+\s*/\s*\d+\s*$",
        r"\bjan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|aug(ust)?|sep(t)?(ember)?|oct(ober)?|nov(ember)?|dec(ember)?\b",
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",  # dates
        r"\b\d{4}\b",  # standalone years
    ]
    noise_re = re.compile("(" + ")|(".join(noise_patterns) + ")", re.IGNORECASE)
    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # drop very short lines or bullet-only lines
        if len(line.split()) < 3:
            continue
        if noise_re.search(line):
            continue
        # remove excessive bullets/dots
        line = re.sub(r"[•·]+", " ", line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)
# Session/cookie security settings
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Set to True in production behind HTTPS
app.config['SESSION_COOKIE_SECURE'] = False if os.getenv('FLASK_ENV') != 'production' else True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# Password reset token serializer
def get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config['SECRET_KEY'])

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# qg is initialized above; may be None if Questgen not available

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    questions = db.relationship('QuestionHistory', backref='user', lazy=True)

# Question database model for pre-existing questions
class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    topic = db.Column(db.String(100), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # short_answer, mcq
    question_text = db.Column(db.Text, nullable=False)
    marks = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Question History model
class QuestionHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    question_type = db.Column(db.String(50), nullable=False)
    difficulty = db.Column(db.String(50), nullable=False)
    questions_generated = db.Column(db.Text, nullable=False)  # JSON string of questions
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Custom filter for JSON parsing in templates
@app.template_filter('from_json')
def from_json_filter(json_string):
    import json
    try:
        return json.loads(json_string)
    except:
        return []

# Function to seed the database with pre-existing questions
def seed_questions():
    """Add pre-existing questions to the database if they don't exist"""
    if Question.query.count() > 0:
        return  # Database already has questions
    
    questions_data = [
        # Software Engineering Questions
        {"subject": "software engineering", "topic": "SDLC", "difficulty": "Easy", "question_type": "short_answer", "question_text": "What are the main phases of the Software Development Life Cycle?", "marks": 2},
        {"subject": "software engineering", "topic": "SDLC", "difficulty": "Medium", "question_type": "short_answer", "question_text": "Compare Waterfall and Agile development models. When would you use each?", "marks": 5},
        {"subject": "software engineering", "topic": "Requirements", "difficulty": "Easy", "question_type": "short_answer", "question_text": "Differentiate between functional and non-functional requirements with examples.", "marks": 3},
        {"subject": "software engineering", "topic": "Testing", "difficulty": "Medium", "question_type": "short_answer", "question_text": "Explain the difference between verification and validation in software testing.", "marks": 4},
        {"subject": "software engineering", "topic": "Design", "difficulty": "Hard", "question_type": "short_answer", "question_text": "Explain the SOLID principles with examples for each principle.", "marks": 8},
        {"subject": "software engineering", "topic": "Design", "difficulty": "Medium", "question_type": "short_answer", "question_text": "What are design patterns? Explain Factory and Observer patterns with use cases.", "marks": 6},
        {"subject": "software engineering", "topic": "Testing", "difficulty": "Easy", "question_type": "short_answer", "question_text": "List the different levels of software testing.", "marks": 2},
        {"subject": "software engineering", "topic": "CI/CD", "difficulty": "Medium", "question_type": "short_answer", "question_text": "Explain Continuous Integration and Continuous Deployment (CI/CD) pipeline.", "marks": 5},
        
        # Data Structures Questions
        {"subject": "data structures", "topic": "Arrays", "difficulty": "Easy", "question_type": "short_answer", "question_text": "Compare arrays and linked lists. What are their advantages and disadvantages?", "marks": 4},
        {"subject": "data structures", "topic": "Trees", "difficulty": "Medium", "question_type": "short_answer", "question_text": "Explain different tree traversal methods (preorder, inorder, postorder) with examples.", "marks": 5},
        {"subject": "data structures", "topic": "Complexity", "difficulty": "Easy", "question_type": "short_answer", "question_text": "What is Big O notation? Give examples of O(1), O(n), and O(n²) algorithms.", "marks": 3},
        {"subject": "data structures", "topic": "Sorting", "difficulty": "Medium", "question_type": "short_answer", "question_text": "Compare the time complexity of Bubble Sort, Quick Sort, and Merge Sort.", "marks": 4},
        {"subject": "data structures", "topic": "Graphs", "difficulty": "Hard", "question_type": "short_answer", "question_text": "Explain BFS and DFS algorithms. When would you use each?", "marks": 6},
        {"subject": "data structures", "topic": "Hash Tables", "difficulty": "Medium", "question_type": "short_answer", "question_text": "How do hash tables work? Explain collision resolution techniques.", "marks": 5},
        
        # Database Questions
        {"subject": "database", "topic": "ACID", "difficulty": "Easy", "question_type": "short_answer", "question_text": "Explain ACID properties in database transactions.", "marks": 3},
        {"subject": "database", "topic": "Normalization", "difficulty": "Medium", "question_type": "short_answer", "question_text": "What is database normalization? Explain 1NF, 2NF, and 3NF with examples.", "marks": 6},
        {"subject": "database", "topic": "SQL vs NoSQL", "difficulty": "Medium", "question_type": "short_answer", "question_text": "Compare SQL and NoSQL databases. When would you use each?", "marks": 5},
        {"subject": "database", "topic": "Indexing", "difficulty": "Medium", "question_type": "short_answer", "question_text": "Explain database indexing and its impact on query performance.", "marks": 4},
        {"subject": "database", "topic": "Relationships", "difficulty": "Easy", "question_type": "short_answer", "question_text": "Describe different types of database relationships with examples.", "marks": 3},
        
        # Data Architecture Questions
        {"subject": "data architecture", "topic": "Data Warehouse", "difficulty": "Medium", "question_type": "short_answer", "question_text": "What is a data warehouse? Explain its key characteristics and benefits.", "marks": 4},
        {"subject": "data architecture", "topic": "ETL", "difficulty": "Medium", "question_type": "short_answer", "question_text": "Explain the ETL process with examples.", "marks": 5},
        {"subject": "data architecture", "topic": "Data Lake", "difficulty": "Hard", "question_type": "short_answer", "question_text": "Compare data lake and data warehouse. What is a data lakehouse?", "marks": 6},
        {"subject": "data architecture", "topic": "OLTP vs OLAP", "difficulty": "Easy", "question_type": "short_answer", "question_text": "Differentiate between OLTP and OLAP systems.", "marks": 3},
        {"subject": "data architecture", "topic": "Data Governance", "difficulty": "Hard", "question_type": "short_answer", "question_text": "What is data governance? Explain its key components and importance.", "marks": 7},
    ]
    
    for q_data in questions_data:
        question = Question(**q_data)
        db.session.add(question)
    
    db.session.commit()
    print(f"Seeded {len(questions_data)} questions to the database")

# Forms
class LoginForm(FlaskForm):
    # Use non-standard field names to discourage browser autofill matching
    login_username = StringField('Username', validators=[DataRequired()])
    login_password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class SignupForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

class QuestionForm(FlaskForm):
    question_source = SelectField('Question Source', choices=[('generate', 'Generate New Questions'), ('database', 'Use Existing Questions from Database')], default='generate')
    input_text = TextAreaField('Enter text to generate questions (optional)', render_kw={"rows": 6, "placeholder": "Enter paragraph or text here to generate questions..."})
    prompt_subject = StringField('Subject / Topic', render_kw={"placeholder": "e.g., Software Engineering"})
    difficulty = SelectField('Select difficulty', choices=[('', 'Any'), ('Easy', 'Easy'), ('Medium', 'Medium'), ('Hard', 'Hard')])
    num_questions = IntegerField('Number of questions', validators=[DataRequired()], default=5, render_kw={"min": 1, "max": 20})
    question_type = SelectField('Question Type', choices=[('short_answer', 'Short Answer'), ('mcq', 'Multiple Choice'), ('mixed', 'Mixed')], default='short_answer')
    submit = SubmitField('Get Questions')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Send reset link')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.login_username.data).first()
        if user and check_password_hash(user.password_hash, form.login_password.data):
            # Regenerate session and mark as permanent to apply lifetime
            session.clear()
            session.permanent = True
            session['last_activity'] = datetime.utcnow().isoformat()
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html', form=form)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = SignupForm()
    if form.validate_on_submit():
        # Check if user already exists
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already exists', 'error')
            return render_template('signup.html', form=form)
        
        if User.query.filter_by(email=form.email.data).first():
            flash('Email already registered', 'error')
            return render_template('signup.html', form=form)
        
        # Create new user
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data)
        )
        db.session.add(user)
        db.session.commit()
        
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

def generate_reset_token(email: str) -> str:
    s = get_serializer()
    return s.dumps({'email': email})

def verify_reset_token(token: str, max_age_seconds: int = 3600) -> str:
    s = get_serializer()
    try:
        data = s.loads(token, max_age=max_age_seconds)
        return data.get('email', '')
    except SignatureExpired:
        return ''
    except BadSignature:
        return ''

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        # Always respond generically to avoid user enumeration
        if user:
            token = generate_reset_token(user.email)
            reset_url = url_for('reset_password', token=token, _external=True)
            print(f"Password reset link for {user.email}: {reset_url}")
        flash('If the email exists, a reset link has been sent.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html', form=form)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    email = verify_reset_token(token)
    if not email:
        flash('The password reset link is invalid or has expired.', 'error')
        return redirect(url_for('forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('forgot_password'))
        user.password_hash = generate_password_hash(form.password.data)
        db.session.commit()
        flash('Your password has been reset. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form)

@app.route('/dashboard')
@login_required
def dashboard():
    # Get user's question history
    questions = QuestionHistory.query.filter_by(user_id=current_user.id).order_by(QuestionHistory.created_at.desc()).limit(10).all()
    return render_template('dashboard.html', questions=questions)

@app.route('/generate_questions')
@login_required
def generate_questions():
    form = QuestionForm()
    return render_template('index.html', form=form)

@app.route('/generate', methods=['GET', 'POST'])
@login_required
def generate():
    form = QuestionForm()
    
    if form.validate_on_submit():
        question_source = form.question_source.data
        num_questions = form.num_questions.data
        subject = form.prompt_subject.data or "General"
        difficulty = form.difficulty.data or ""
        question_type = form.question_type.data
        
        # If a file is uploaded, extract text and override input_text for generation
        upload = request.files.get('upload')
        if upload and upload.filename and allowed_file(upload.filename):
            filename = secure_filename(upload.filename)
            _, ext = os.path.splitext(filename.lower())
            file_bytes = io.BytesIO(upload.read())
            extracted = ''
            if ext == '.pdf':
                extracted = extract_text_from_pdf(file_bytes)
            else:
                # supports .ppt and .pptx via python-pptx
                extracted = extract_text_from_pptx(file_bytes)
            if extracted:
                extracted = clean_extracted_text(extracted)
                # Prepend uploaded content to any typed text
                if form.input_text.data:
                    form.input_text.data = f"{extracted}\n\n{form.input_text.data}"
                else:
                    form.input_text.data = extracted

        if question_source == 'database':
            # Get questions from database
            query = Question.query
            
            # Filter by subject if provided
            if subject and subject.lower() != "general":
                query = query.filter(Question.subject.ilike(f"%{subject.lower()}%"))
            
            # Filter by difficulty if provided
            if difficulty:
                query = query.filter(Question.difficulty == difficulty)
            
            # Filter by question type if provided
            if question_type != 'mixed':
                query = query.filter(Question.question_type == question_type)
            
            # Get random questions
            questions = query.order_by(db.func.random()).limit(num_questions).all()
            
            if questions:
                questions_list = [(q.question_text, q.topic, q.marks) for q in questions]
            else:
                flash('No questions found in database matching your criteria. Try generating new questions instead.', 'info')
                return render_template('index.html', form=form)
        
        else:
            # Generate new questions (existing logic)
            input_text = form.input_text.data
            total_marks = int(request.form.get('total_marks', 0) or 0)
            
            # Try AI generation first (OpenAI), then Questgen, then fallback
            questions_list = []
            
            # 1. Try OpenAI API first
            if openai_client:
                # Provide extracted topics (if any) for better guidance, after cleaning noise
                clean_for_topics = clean_extracted_text(input_text) if input_text else ""
                extracted_topics = extract_topics_from_text(clean_for_topics, max_topics=12) if clean_for_topics else []
                questions_list = generate_ai_questions_openai(input_text, num_questions, subject, difficulty, total_marks, question_type, topics=extracted_topics)
            
            # 2. If OpenAI fails, try Questgen
            if not questions_list and qg is not None:
                try:
                    if input_text:
                        payload = {"input_text": input_text}
                        result = qg.predict_shortq(payload)
                        raw_questions = result.get('questions', [])[:num_questions]
                        questions_list = [(q, subject or "", difficulty) for q in raw_questions]
                    else:
                        prompt_parts = [p for p in [subject, difficulty] if p]
                        prompt = ", ".join(prompt_parts) or (subject or "General")
                        payload = {"input_text": prompt}
                        result = qg.predict_shortq(payload)
                        raw_questions = result.get('questions', [])[:num_questions]
                        questions_list = [(q, subject or "", difficulty) for q in raw_questions]
                except Exception as e:
                    print(f"Questgen error: {e}")
                    questions_list = []

            # 3. Fallback to template-based generation
            if not questions_list:
                if input_text:
                    questions_list = generate_fallback_questions(input_text, num_questions, subject_hint=subject or "", question_type=question_type)
                else:
                    prompt_parts = [p for p in [subject, difficulty] if p]
                    prompt = ", ".join(prompt_parts) or (subject or "General")
                    questions_list = generate_fallback_questions(prompt, num_questions, subject_hint=subject or "", question_type=question_type)

            # Allocate marks to fallback questions if total marks specified
            if total_marks > 0:
                questions_with_marks = allocate_marks_to_questions([q[0] for q in questions_list], total_marks)
                questions_list = [(q, subject or questions_list[0][1] if questions_list else "General", marks) for q, marks in questions_with_marks]

        # Save questions to database
        if questions_list:
            question_history = QuestionHistory(
                user_id=current_user.id,
                subject=subject or "General",
                question_type=question_type,
                difficulty=difficulty or "Any",
                questions_generated=json.dumps(questions_list)
            )
            db.session.add(question_history)
            db.session.commit()

        return render_template('paper.html', questions=questions_list)
    
    return render_template('index.html', form=form)

@app.route('/export_pdf', methods=['POST'])
def export_pdf():
    questions_data = request.form.get('questions_data')
    subject = request.form.get('subject', 'Question Paper')
    
    if not questions_data:
        return "No questions data provided", 400
    
    # Parse questions from the form data
    import json
    try:
        questions = json.loads(questions_data)
    except:
        return "Invalid questions data", 400
    
    # Create PDF in memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    # Get styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=1  # Center alignment
    )
    question_style = ParagraphStyle(
        'CustomQuestion',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=12,
        leftIndent=20
    )
    
    # Build content
    story = []
    story.append(Paragraph(f"{subject} - Question Paper", title_style))
    story.append(Spacer(1, 20))
    
    for i, question in enumerate(questions, 1):
        if isinstance(question, list) and len(question) > 0:
            question_text = question[0]
        else:
            question_text = str(question)
        
        story.append(Paragraph(f"Q{i}. {question_text}", question_style))
        story.append(Spacer(1, 10))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    # Create response
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{subject.replace(" ", "_")}_questions.pdf"'
    
    return response

# Prevent caching of pages with user data to avoid showing after logout
@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Idle session timeout enforcement
@app.before_request
def enforce_idle_timeout():
    if not current_user.is_authenticated:
        return
    try:
        last = session.get('last_activity')
        now = datetime.utcnow()
        session['last_activity'] = now.isoformat()
        if last:
            last_dt = datetime.fromisoformat(last)
            if now - last_dt > app.config.get('PERMANENT_SESSION_LIFETIME', timedelta(minutes=30)):
                logout_user()
                session.clear()
                flash('Your session expired due to inactivity. Please log in again.', 'info')
                return redirect(url_for('login'))
    except Exception:
        # If parsing fails, reset activity timestamp
        session['last_activity'] = datetime.utcnow().isoformat()

@app.route('/export_docx', methods=['POST'])
def export_docx():
    questions_data = request.form.get('questions_data')
    subject = request.form.get('subject', 'Question Paper')
    
    if not questions_data:
        return "No questions data provided", 400
    
    # Parse questions from the form data
    import json
    try:
        questions = json.loads(questions_data)
    except:
        return "Invalid questions data", 400
    
    # Create DOCX document
    doc = Document()
    
    # Add title
    title = doc.add_heading(f"{subject} - Question Paper", 0)
    title.alignment = 1  # Center alignment
    
    # Add questions
    for i, question in enumerate(questions, 1):
        if isinstance(question, list) and len(question) > 0:
            question_text = question[0]
        else:
            question_text = str(question)
        
        doc.add_paragraph(f"Q{i}. {question_text}")
        doc.add_paragraph()  # Add spacing
    
    # Save to memory
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    
    # Create response
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    response.headers['Content-Disposition'] = f'attachment; filename="{subject.replace(" ", "_")}_questions.docx"'
    
    return response

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_questions()  # Add pre-existing questions to database
    app.run(debug=True)
