import os
import json
import asyncio
import nest_asyncio
import streamlit as st
import pdfplumber
import docx
from io import BytesIO
from fpdf import FPDF
from langchain_groq import ChatGroq

# Allow asyncio in Streamlit
nest_asyncio.apply()

# ------------------------------
# Configuration & Setup
# ------------------------------
st.set_page_config(page_title="Interactive MCQ Test Generator", layout="centered")

# Set your Groq API key (hardcoded as requested)
os.environ["GROQ_API_KEY"] = "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"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ------------------------------
# Utility Functions
# ------------------------------
def allowed_file(filename):
    allowed_extensions = ["pdf", "docx", "txt"]
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def extract_text(file_obj, filename):
    ext = filename.rsplit('.', 1)[1].lower()
    if ext == "pdf":
        try:
            with pdfplumber.open(file_obj) as pdf:
                text = "".join(page.extract_text() or "" for page in pdf.pages)
            return text
        except Exception as e:
            st.error(f"Error extracting PDF: {e}")
            return ""
    elif ext == "docx":
        try:
            doc = docx.Document(file_obj)
            text = " ".join(para.text for para in doc.paragraphs)
            return text
        except Exception as e:
            st.error(f"Error extracting DOCX: {e}")
            return ""
    elif ext == "txt":
        try:
            return file_obj.read().decode("utf-8", errors="ignore")
        except Exception as e:
            st.error(f"Error reading TXT file: {e}")
            return ""
    else:
        return ""

async def async_generate_mcqs(input_text, num_questions, difficulty):
    """
    Generate MCQs from the input text.
    The prompt instructs the model to output valid JSON with key 'questions', which maps to a list
    of question objects. Each object contains:
      - question: str
      - options: list of four strings (each option text)
      - correct: one of 'A', 'B', 'C', 'D'
      - explanation: str (explanation for the correct answer)
    """
    prompt = f"""
You are an AI assistant that generates multiple-choice questions (MCQs) based on the text provided.
Difficulty: {difficulty}
Number of Questions: {num_questions}

For each question, output an object with the following keys:
  - \"question\": The question text.
  - \"options\": A list of four answer options.
  - \"correct\": The letter (A, B, C, or D) indicating the correct answer.
  - \"explanation\": A short explanation of why the correct answer is correct.

Output the results as a valid JSON object with a key \"questions\" that maps to a list of question objects.

Text:
\"\"\"{input_text}\"\"\"
"""
    llm = ChatGroq(
        temperature=0.7,
        groq_api_key=GROQ_API_KEY,
        model_name="mixtral-8x7b-32768"
    )
    messages = [{"role": "user", "content": prompt}]
    response = await llm.ainvoke(messages)
    try:
        data = json.loads(response.content)
        return data.get("questions", [])
    except Exception as e:
        st.error("Error parsing MCQ output: " + str(e))
        return []

def generate_mcqs(input_text, num_questions, difficulty):
    """Run the asynchronous MCQ generation in a blocking way."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    mcqs = loop.run_until_complete(async_generate_mcqs(input_text, num_questions, difficulty))
    loop.close()
    return mcqs

def create_txt_summary(mcqs, responses):
    """Create a summary text for the test results."""
    summary_lines = []
    score = 0
    for i, (q, user_ans) in enumerate(zip(mcqs, responses)):
        correct_ans = q.get("correct", "").strip().upper()
        is_correct = (user_ans.strip().upper() == correct_ans)
        if is_correct:
            score += 1
        summary_lines.append(f"Q{i+1}: {q.get('question', '')}")
        for opt in q.get("options", []):
            summary_lines.append(opt)
        summary_lines.append(f"Your Answer: {user_ans} | Correct Answer: {correct_ans}")
        summary_lines.append(f"Explanation: {q.get('explanation', '')}")
        summary_lines.append(\"\"\"--------------------------------------\"\"\")
    summary_lines.insert(0, f\"Final Score: {score}/{len(mcqs)}\\n\")
    return "\n".join(summary_lines)

def create_pdf_summary(mcqs, responses):
    """Generate a PDF file from the test results and return as bytes."""
    score = 0
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "MCQ Test Results", ln=True, align='C')
    pdf.ln(5)
    for i, (q, user_ans) in enumerate(zip(mcqs, responses)):
        correct_ans = q.get("correct", "").strip().upper()
        is_correct = (user_ans.strip().upper() == correct_ans)
        if is_correct:
            score += 1
        pdf.multi_cell(0, 10, f"Q{i+1}: {q.get('question', '')}")
        for opt in q.get("options", []):
            pdf.multi_cell(0, 10, opt)
        pdf.multi_cell(0, 10, f"Your Answer: {user_ans} | Correct Answer: {correct_ans}")
        pdf.multi_cell(0, 10, f"Explanation: {q.get('explanation', '')}")
        pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
    pdf.set_font("Arial", size=14)
    pdf.cell(0, 10, f"Final Score: {score}/{len(mcqs)}", ln=True, align='C')
    output = BytesIO()
    pdf.output(output, dest="F")
    with open("temp.pdf", "rb") as f:  # Read the temporary file created by FPDF\n        pdf_bytes = f.read()\n    os.remove("temp.pdf")\n    return pdf_bytes

# ------------------------------
# Custom CSS for Modern UI
# ------------------------------
st.markdown(
    """
    <style>
    .main { background: linear-gradient(90deg, #74ABE2, #5563DE); }
    .stTextArea, .stNumberInput, .stSelectbox { margin-bottom: 1rem; }
    .stButton>button { background-color: #ff5c5c; color: #fff; border-radius: 8px; border: none; padding: 0.5rem 1rem; }
    .stButton>button:hover { background-color: #ff3c3c; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------
# Streamlit App UI
# ------------------------------
st.title("📚 Interactive MCQ Test Generator")
st.write("Upload a document (PDF, DOCX, or TXT) to generate an MCQ test. Answer each question to get immediate feedback!")

# Upload file
uploaded_file = st.file_uploader("Choose a file", type=["pdf", "docx", "txt"])

if uploaded_file is not None:
    if allowed_file(uploaded_file.name):
        file_bytes = uploaded_file.read()
        file_obj = BytesIO(file_bytes)
        text = extract_text(file_obj, uploaded_file.name)
        if text:
            st.success("File processed successfully!")
            st.write("Extracted text preview (first 500 characters):")
            st.write(text[:500] + "...")
            
            # Test options
            num_questions = st.number_input("Number of MCQs:", min_value=1, max_value=20, value=5)
            difficulty = st.selectbox("Select Difficulty:", ["Easy", "Medium", "Hard"])
            
            if st.button("Generate Test"):
                with st.spinner("Generating MCQs..."):
                    mcqs = generate_mcqs(text, num_questions, difficulty)
                if mcqs:
                    st.session_state.mcqs = mcqs
                    st.session_state.current_q = 0
                    st.session_state.responses = [None] * len(mcqs)
                    st.success("Test generated! Begin your test below.")
                else:
                    st.error("No MCQs were generated. Please try again.")
        else:
            st.error("Could not extract text from the file.")
    else:
        st.error("Invalid file format. Please upload a PDF, DOCX, or TXT file.")

# If test is generated, show one question at a time
if "mcqs" in st.session_state and st.session_state.get("mcqs"):
    current = st.session_state.current_q
    total = len(st.session_state.mcqs)
    if current < total:
        q = st.session_state.mcqs[current]
        st.markdown(f"### Question {current+1} of {total}")
        st.write(q.get("question", ""))
        # Show options with radio buttons (display option letter + text)\n        option_mapping = {}\n        options_display = []\n        for idx, opt in enumerate(q.get(\"options\", [])):\n            letter = chr(65 + idx)  # A, B, C, D\n            option_mapping[letter] = opt\n            options_display.append(f\"{letter}: {opt}\")\n        user_choice = st.radio(\"Select your answer:\", options=list(option_mapping.keys()))\n        if st.button(\"Submit Answer\"):\n            st.session_state.responses[current] = user_choice\n            # Provide immediate feedback\n            correct_letter = q.get(\"correct\", \"\").strip().upper()\n            if user_choice.upper() == correct_letter:\n                st.success(\"Correct Answer! 🎉\")\n            else:\n                st.error(f\"Incorrect! The correct answer is {correct_letter}.\\nExplanation: {q.get('explanation', '')}\")\n            if current < total - 1:\n                if st.button(\"Next Question\"):\n                    st.session_state.current_q += 1\n                    st.experimental_rerun()\n            else:\n                st.success(\"Test Completed!\")\n                # Show final summary\n                score = sum(1 for i in range(total) if st.session_state.responses[i].upper() == st.session_state.mcqs[i].get(\"correct\", \"\").strip().upper())\n                st.markdown(f\"### Final Score: {score} / {total}\")\n                summary_text = create_txt_summary(st.session_state.mcqs, st.session_state.responses)\n                st.text_area(\"Test Summary\", summary_text, height=300)\n                st.download_button(\"Download Summary as TXT\", summary_text, file_name=\"mcq_results.txt\", mime=\"text/plain\")\n                pdf_bytes = create_pdf_summary(st.session_state.mcqs, st.session_state.responses)\n                st.download_button(\"Download Summary as PDF\", pdf_bytes, file_name=\"mcq_results.pdf\", mime=\"application/pdf\")\n    else:\n        st.write(\"No more questions.\")\n\n# Helper function to create text summary (used in final summary download)\ndef create_txt_summary(mcqs, responses):\n    lines = []\n    score = 0\n    for i, (q, ans) in enumerate(zip(mcqs, responses)):\n        correct = q.get(\"correct\", \"\").strip().upper()\n        is_correct = (ans.strip().upper() == correct)\n        if is_correct:\n            score += 1\n        lines.append(f\"Q{i+1}: {q.get('question', '')}\")\n        for idx, opt in enumerate(q.get('options', [])):\n            letter = chr(65+idx)\n            lines.append(f\"   {letter}: {opt}\")\n        lines.append(f\"Your Answer: {ans} | Correct Answer: {correct}\")\n        lines.append(f\"Explanation: {q.get('explanation', '')}\")\n        lines.append(\"--------------------------------------\")\n    lines.insert(0, f\"Final Score: {score} / {len(mcqs)}\\n\")\n    return \"\\n\".join(lines)\n"}
