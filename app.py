import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, send_file
import pdfplumber
import docx
from werkzeug.utils import secure_filename
from fpdf import FPDF
from langchain_groq import ChatGroq

###############################################################################
# ALLOW ASYNCIO IN FLASK
###############################################################################
nest_asyncio.apply()

###############################################################################
# CONFIGURATION
###############################################################################
# Hardcode your Groq API key here (not recommended for production).
os.environ["GROQ_API_KEY"] = "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"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['RESULTS_FOLDER'] = 'results/'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'docx', 'txt'}

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)

###############################################################################
# UTILITY FUNCTIONS
###############################################################################
def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_text_from_file(file_path):
    """Extract text from PDF, DOCX, or TXT."""
    ext = file_path.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        with pdfplumber.open(file_path) as pdf:
            text = ''.join((page.extract_text() or "") for page in pdf.pages)
        return text
    elif ext == 'docx':
        doc = docx.Document(file_path)
        text = ' '.join(para.text for para in doc.paragraphs)
        return text
    elif ext == 'txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    return None

async def async_generate_content(input_text, num_questions, difficulty, include_summary):
    """
    Build a prompt by inserting the extracted text (input_text) into the prompt.
    We also factor in the difficulty and an optional summary request.
    """
    base_prompt = f"""
You are an AI assistant helping the user generate multiple-choice questions (MCQs) based on the following text:
\"{input_text}\"

Difficulty: {difficulty}
Number of MCQs: {num_questions}
"""

    summary_part = ""
    if include_summary:
        summary_part = "Additionally, produce a short summary of the text labeled 'SUMMARY:' on its own line.\n"

    mcq_instructions = f"""
Please generate exactly {num_questions} MCQs from the text. Each question should include:
- A clear question
- Four answer options labeled A, B, C, D
- The correct answer clearly indicated

Format:
## MCQ
Question: [question]
A) [option A]
B) [option B]
C) [option C]
D) [option D]
Correct Answer: [correct option]
"""

    # Combine into one final prompt
    prompt = base_prompt + summary_part + mcq_instructions

    llm = ChatGroq(
        temperature=0.7,
        groq_api_key=GROQ_API_KEY,
        model_name="mixtral-8x7b-32768"
    )
    messages = [{"role": "user", "content": prompt}]
    response = await llm.ainvoke(messages)
    return response.content.strip()

def generate_content(input_text, num_questions, difficulty, include_summary):
    """Run the async function in a blocking way."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result_text = loop.run_until_complete(async_generate_content(input_text, num_questions, difficulty, include_summary))
    loop.close()
    return result_text

def save_text_file(content, filename):
    path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path

def create_pdf_file(content, filename):
    """
    Create a PDF file from the entire content. This may include a 'SUMMARY:' line
    plus multiple MCQs separated by '## MCQ'.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # We'll just place the entire text in the PDF, line by line.
    for line in content.split('\n'):
        pdf.multi_cell(0, 10, line)
    pdf_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    pdf.output(pdf_path)
    return pdf_path

###############################################################################
# FLASK ROUTES
###############################################################################
@app.route('/')
def index():
    """Render the main page (upload form)."""
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    """Handle file upload and MCQ generation."""
    if 'file' not in request.files:
        return "No file part", 400

    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Extract text
        text = extract_text_from_file(file_path)
        if text:
            # Number of MCQs
            num_questions = request.form.get('num_questions', '5')
            try:
                num_questions = int(num_questions)
            except ValueError:
                num_questions = 5

            # Difficulty
            difficulty = request.form.get('difficulty', 'Medium')

            # Summary?
            include_summary = bool(request.form.get('include_summary', False))

            # Generate the combined content
            output = generate_content(text, num_questions, difficulty, include_summary)

            # Save as TXT and PDF
            base_name = filename.rsplit('.', 1)[0]
            txt_filename = f"generated_content_{base_name}.txt"
            pdf_filename = f"generated_content_{base_name}.pdf"
            save_text_file(output, txt_filename)
            create_pdf_file(output, pdf_filename)

            # Render results
            return render_template('results.html',
                                   content=output,
                                   txt_filename=txt_filename,
                                   pdf_filename=pdf_filename)
    return "Invalid file format or no file uploaded", 400

@app.route('/download/<filename>')
def download_file(filename):
    """Serve the generated file for download."""
    file_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "File not found", 404

###############################################################################
# MAIN
###############################################################################
if __name__ == '__main__':
    # Some environments disallow the reloader due to signal usage
    app.run(debug=True, use_reloader=False)
