## AI-based Question Paper Generator (Flask)

### Overview
- Generate questions from input text using Questgen (if installed) or a local fallback.
- AI-only mode: no CSV dependency. You can also generate by specifying subject/difficulty.

### Structure
```
app.py
generator.py
static/
  style.css
templates/
  index.html
  paper.html
requirements.txt
```

### Setup (Windows PowerShell)
1) Create and activate a virtual environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2) Install dependencies
```powershell
pip install -r requirements.txt
python -c "import nltk; nltk.download('punkt')"
```
Questgen is optional. If it fails to install, the app uses a simple fallback for text-based generation.

### Run
```powershell
python app.py
```
Open `http://127.0.0.1:5000` in your browser.

### Usage
- Enter a paragraph to generate questions via Questgen (or fallback).
- Or provide a `Subject / Topic` and optional `difficulty` and `num_questions`.

### Notes
- The app no longer depends on a CSV file; all questions are generated.

