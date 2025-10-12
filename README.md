# AI-based Question Paper Generator with User Authentication

## Overview
A Flask web application that generates academic questions using AI, with user authentication and question history tracking. Features include:

- **User Authentication**: Sign up, login, and secure sessions
- **AI Question Generation**: Uses Questgen (if available) or intelligent fallback
- **Multiple Question Types**: Short answer, MCQ, and mixed questions
- **Question History**: All generated questions are saved to user accounts
- **Database Storage**: SQLite database stores users and question history
- **Export Options**: PDF and Word document generation

## Project Structure
```
AI-based-QP-Generator/
├── app.py                 # Main Flask application
├── static/
│   └── style.css         # Styling
├── templates/
│   ├── index.html        # Question generation form
│   ├── login.html        # User login
│   ├── signup.html       # User registration
│   ├── dashboard.html    # User dashboard with history
│   └── paper.html        # Generated questions display
├── instance/
│   └── users.db          # SQLite database (auto-created)
├── requirements.txt      # Python dependencies
└── README.md
```

## Features

### User Management
- User registration with email validation
- Secure password hashing
- Session management
- User dashboard with question history

### Question Generation
- **Text-based**: Generate questions from input paragraphs
- **Subject-based**: Generate questions by subject/topic
- **Question Types**: Short answer, Multiple Choice (MCQ), Mixed
- **Difficulty Levels**: Easy, Medium, Hard
- **AI Integration**: Questgen for advanced generation, intelligent fallback

### Question History
- All generated questions saved to database
- View recent question sets
- Track generation metadata (subject, type, difficulty, date)

## Setup (Windows PowerShell)

### 1. Create Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
python -c "import nltk; nltk.download('punkt')"
```

### 3. Run Application
```powershell
python app.py
```

### 4. Access Application
Open `http://127.0.0.1:5000` in your browser.

## Usage

### First Time Setup
1. **Create Account**: Click "Sign up" to create a new account
2. **Login**: Use your credentials to access the dashboard

### Generating Questions
1. **Navigate to Generator**: Click "Generate Questions" from dashboard
2. **Choose Input Method**:
   - **Text Input**: Enter a paragraph to generate questions from
   - **Subject/Topic**: Specify a subject (e.g., "Software Engineering")
3. **Configure Options**:
   - Number of questions (1-20)
   - Difficulty level (Easy/Medium/Hard)
   - Question type (Short Answer/MCQ/Mixed)
   - Force AI generation (optional)
4. **Generate**: Click "Generate Questions" to create your question set

### Viewing History
- **Dashboard**: See your recent question sets
- **Question Details**: View subject, type, difficulty, and generation date
- **Question Preview**: See first few questions from each set

## Database

### User Data
- Username, email, encrypted password
- Account creation timestamp
- Linked question history

### Question History
- Subject/topic of questions
- Question type and difficulty
- Full question set (JSON format)
- Generation timestamp

### Accessing Database
```powershell
sqlite3 instance\users.db
.tables
SELECT * FROM user;
SELECT * FROM question_history;
```

## Dependencies

### Core
- **Flask**: Web framework
- **Flask-SQLAlchemy**: Database ORM
- **Flask-Login**: User session management
- **Flask-WTF**: Form handling and CSRF protection

### AI/ML
- **Questgen**: AI question generation (optional)
- **NLTK**: Natural language processing
- **NumPy**: Numerical operations

### Export
- **ReportLab**: PDF generation
- **python-docx**: Word document generation

### Security
- **Werkzeug**: Password hashing
- **email-validator**: Email validation

## Configuration

### Database
- **Type**: SQLite (file: `instance/users.db`)
- **Auto-creation**: Database and tables created on first run

### Security
- **Secret Key**: Change `SECRET_KEY` in production
- **Password Hashing**: Uses Werkzeug's secure hashing
- **CSRF Protection**: Enabled for all forms

## Notes

- **Questgen**: Optional AI library. If not installed, uses intelligent fallback
- **Database**: Automatically created in `instance/` folder
- **Sessions**: User sessions persist across browser restarts
- **Export**: Generated questions can be exported as PDF or Word documents
- **Responsive**: Works on desktop and mobile browsers