import os
import asyncio
import nest_asyncio
import streamlit as st
import pdfplumber
import docx
from io import BytesIO
from fpdf import FPDF
from langchain_groq import ChatGroq

# Allow asyncio to run in Streamlit
nest_asyncio.apply()

# ------------------------------
# Configuration & Setup
# ------------------------------
st.set_page_config(page_title="MCQ Generator from Document", layout="centered")

# Set your Groq API key (hardcoded as requested)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")

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
            pdf = pdfplumber.open(file_obj)
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
            pdf.close()
            return text
        except Exception as e:
            st.error(f"Error extracting PDF: {e}")
            return ""
    elif ext == "docx":
        try:
            doc = docx.Document(file_obj)
            text = " ".join([para.text for para in doc.paragraphs])
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

async def async_generate_mcqs(input_text, num_questions, difficulty, include_summary):
    """
    Build a prompt that uses the extracted text. It includes:
      - The selected difficulty
      - The requested number of MCQs
      - Optionally, a short summary
    """
    summary_part = ""
    if include_summary:
        summary_part = "Also provide a short summary of the text labeled 'SUMMARY:' on its own line.\n"
    prompt = f"""
You are an AI assistant that generates multiple-choice questions (MCQs) from the following text:
"{input_text}"
Difficulty: {difficulty}
Number of Questions: {num_questions}
{summary_part}
Please generate exactly {num_questions} MCQs from the text. Each question should include:
- A clear question.
- Four answer options labeled A, B, C, D.
- The correct answer clearly indicated.

Format:
## MCQ
Question: [question text]
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
    response = await llm.ainvoke(messages)
    return response.content.strip()

def generate_mcqs(input_text, num_questions, difficulty, include_summary):
    """Run the asynchronous generation function in a blocking way."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    mcqs = loop.run_until_complete(async_generate_mcqs(input_text, num_questions, difficulty, include_summary))
    loop.close()
    return mcqs

def create_pdf(text):
    """Generate a PDF from the given text and return its bytes."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    # Write each line in the PDF
    for line in text.split("\n"):
        pdf.multi_cell(0, 10, line)
    output = BytesIO()
    pdf.output(output)
    return output.getvalue()

# ------------------------------
# Streamlit App UI
# ------------------------------
st.title("MCQ Generator from Document")
st.write("Upload a PDF, DOCX, or TXT file to generate multiple-choice questions (MCQs).")

uploaded_file = st.file_uploader("Choose a file", type=["pdf", "docx", "txt"])

if uploaded_file is not None:
    if allowed_file(uploaded_file.name):
        # Read file content into BytesIO for multiple reads
        file_bytes = uploaded_file.read()
        file_obj = BytesIO(file_bytes)
        text = extract_text(file_obj, uploaded_file.name)
        if text:
            st.success("File processed successfully!")
            st.write("Extracted text preview (first 500 characters):")
            st.write(text[:500] + "...")
            
            num_questions = st.number_input("Number of MCQs:", min_value=1, max_value=20, value=5)
            difficulty = st.selectbox("Select Difficulty:", ["Easy", "Medium", "Hard"])
            include_summary = st.checkbox("Include a short summary")
            
            if st.button("Generate MCQs"):
                with st.spinner("Generating MCQs..."):
                    output_text = generate_mcqs(text, num_questions, difficulty, include_summary)
                st.subheader("Generated Content")
                st.text_area("Output", output_text, height=300)
                
                st.download_button("Download as TXT", output_text, file_name="mcqs.txt", mime="text/plain")
                pdf_bytes = create_pdf(output_text)
                st.download_button("Download as PDF", pdf_bytes, file_name="mcqs.pdf", mime="application/pdf")
        else:
            st.error("Could not extract text from the file.")
    else:
        st.error("Invalid file format. Please upload a PDF, DOCX, or TXT file.")
