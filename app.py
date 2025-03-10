import streamlit as st
import pdfplumber
import docx
import os
import random
from fpdf import FPDF
from langchain.llms import HuggingFaceHub

# Set up LLM model (Groq API or Hugging Face)
API_KEY = "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"
llm = HuggingFaceHub(repo_id="tiiuae/falcon-7b-instruct", huggingfacehub_api_token=API_KEY)

# Function to extract text from different file formats
def extract_text(file):
    if file.type == "application/pdf":
        with pdfplumber.open(file) as pdf:
            return "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
    elif file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = docx.Document(file)
        return "\n".join(para.text for para in doc.paragraphs)
    elif file.type == "text/plain":
        return file.read().decode("utf-8")
    return None

# Function to generate MCQs using LLM
def generate_mcqs(text, num_questions, difficulty):
    prompt = f"""
    Generate {num_questions} multiple-choice questions (MCQs) from the following text.
    Difficulty Level: {difficulty}.
    Each question should have:
    - A question statement
    - Four answer options (A, B, C, D)
    - The correct answer indicated
    Format:
    {{
        "questions": [
            {{
                "question": "What is...",
                "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
                "correct": "B"
            }}
        ]
    }}
    
    Text:
    {text[:2000]}  # Limiting text to 2000 chars for processing
    """
    response = llm(prompt)
    return eval(response)  # Convert string response to dictionary

# Function to create a PDF report
def create_pdf(questions, responses):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="MCQ Test Results", ln=True, align='C')
    for i, (q, ans) in enumerate(zip(questions, responses)):
        pdf.multi_cell(0, 10, f"Q{i+1}: {q['question']}")
        for option in q['options']:
            pdf.multi_cell(0, 10, option)
        pdf.multi_cell(0, 10, f"Your Answer: {ans} | Correct Answer: {q['correct']}\n")
    pdf_path = "mcq_results.pdf"
    pdf.output(pdf_path)
    return pdf_path

# Streamlit UI
st.title("📚 AI-Powered MCQ Generator & Test")

uploaded_file = st.file_uploader("Upload a document (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"])
difficulty = st.selectbox("Select Difficulty Level", ["Easy", "Medium", "Hard"])
num_questions = st.slider("Number of MCQs", min_value=1, max_value=20, value=5)

if st.button("Generate MCQs") and uploaded_file:
    with st.spinner("Processing document..."):
        text = extract_text(uploaded_file)
        if text:
            mcq_data = generate_mcqs(text, num_questions, difficulty)
            st.session_state["mcqs"] = mcq_data["questions"]
            st.session_state["current_q"] = 0
            st.session_state["responses"] = []
            st.success("MCQs Generated! Start the test below.")

if "mcqs" in st.session_state and st.session_state["current_q"] < len(st.session_state["mcqs"]):
    q_index = st.session_state["current_q"]
    question_data = st.session_state["mcqs"][q_index]
    st.subheader(f"Q{q_index + 1}: {question_data['question']}")
    user_answer = st.radio("Select an answer:", question_data['options'])

    if st.button("Submit Answer"):
        st.session_state["responses"].append(user_answer[0])
        st.session_state["current_q"] += 1
        st.experimental_rerun()

if "mcqs" in st.session_state and st.session_state["current_q"] == len(st.session_state["mcqs"]):
    st.success("Test Completed! Here are your results:")
    score = sum(1 for i in range(len(st.session_state["mcqs"])) if st.session_state["responses"][i] == st.session_state["mcqs"][i]['correct'])
    st.write(f"Your Score: {score}/{len(st.session_state['mcqs'])}")
    pdf_path = create_pdf(st.session_state["mcqs"], st.session_state["responses"])
    st.download_button("Download Results as PDF", pdf_path)
    st.session_state.clear()
