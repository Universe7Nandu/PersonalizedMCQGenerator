import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, send_file
import pdfplumber
import docx
from werkzeug.utils import secure_filename
from fpdf import FPDF
from langchain_groq import ChatGroq

# Allow asyncio to run in Flask
nest_asyncio.apply()

# ------------------------------
# Configuration & Setup
# ------------------------------
# Set your Groq API key here or via an environment variable
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['RESULTS_FOLDER'] = 'results/'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'txt', 'docx'}

# Ensure the necessary folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)

def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# ------------------------------
# File Extraction Functions
# ------------------------------
def extract_text_from_file(file_path):
    ext = file_path.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        with pdfplumber.open(file_path) as pdf:
            text = ''.join(page.extract_text() or "" for page in pdf.pages)
        return text
    elif ext == 'docx':
        doc = docx.Document(file_path)
        text = ' '.join(para.text for para in doc.paragraphs)
        return text
    elif ext == 'txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    return None

# ------------------------------
# MCQ Generation Function Using Groq
# ------------------------------
def generate_mcqs(input_text, num_questions):
    """
    Build a prompt by inserting the extracted text (input_text) into the prompt.
    The {input_text} placeholder is replaced by the content from the uploaded file.
    """
    prompt = """
You are an AI assistant helping the user generate multiple-choice questions (MCQs) based on the following text:
"{input_text}"
Please generate {num_questions} MCQs from the text. Each question should include:
- A clear question.
- Four answer options labeled A, B, C, D.
- The correct answer clearly indicated.

Format:
## MCQ
Question: [question]
A) [option A]
B) [option B]
C) [option C]
D) [option D]
Correct Answer: [correct option]
    """
    llm = ChatGroq(
        temperature=0.7,
        groq_api_key=GROQ_API_KEY,
        model_name="mixtral-8x7b-32768"
    )
    messages = [{"role": "user", "content": prompt}]
    response = asyncio.run(llm.ainvoke(messages))
    return response.content.strip()

# ------------------------------
# Functions to Save Results
# ------------------------------
def save_text_file(content, filename):
    path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path

def create_pdf_file(content, filename):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    # Split the MCQs into blocks using "## MCQ" as a delimiter
    for block in content.split("## MCQ"):
        if block.strip():
            pdf.multi_cell(0, 10, block.strip())
            pdf.ln(5)
    pdf_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    pdf.output(pdf_path)
    return pdf_path

# ------------------------------
# Flask Routes
# ------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    if 'file' not in request.files:
        return "No file part", 400
    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Extract text from the uploaded file
        text = extract_text_from_file(file_path)
        if text:
            try:
                num_questions = int(request.form.get('num_questions', 5))
            except ValueError:
                num_questions = 5

            # Generate MCQs using the Groq LLM
            mcqs = generate_mcqs(text, num_questions)

            # Save the generated MCQs to text and PDF files
            base_name = filename.rsplit('.', 1)[0]
            txt_filename = f"generated_mcqs_{base_name}.txt"
            pdf_filename = f"generated_mcqs_{base_name}.pdf"
            save_text_file(mcqs, txt_filename)
            create_pdf_file(mcqs, pdf_filename)

            return render_template('results.html', mcqs=mcqs, txt_filename=txt_filename, pdf_filename=pdf_filename)
    return "Invalid file format or no file uploaded", 400

@app.route('/download/<filename>')
def download(filename):
    path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    return send_file(path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
