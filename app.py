import os
import ast
import json
import asyncio
import nest_asyncio
import streamlit as st
import pdfplumber
import docx
from io import BytesIO
from fpdf import FPDF
from langchain_groq import ChatGroq
from langchain.schema import HumanMessage, SystemMessage
from langchain.memory import ConversationBufferMemory

# Allow asyncio to run in Streamlit
nest_asyncio.apply()

# ------------------------------
# Configuration & Setup
# ------------------------------
st.set_page_config(page_title="Interactive MCQ & Chatbot Generator", layout="wide")

# Sidebar: Mode selection
mode = st.sidebar.radio("Select Mode", ["Chatbot", "Document MCQ"])

# Set your Groq API key (hardcoded as requested)
os.environ["GROQ_API_KEY"] = "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"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Chat Model (used in both modes)
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
chat = ChatGroq(temperature=0.7, model_name="llama3-70b-8192", groq_api_key=GROQ_API_KEY)

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
            return " ".join(para.text for para in doc.paragraphs)
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

def query_chatbot(user_query):
    """
    Chatbot query function.
    Uses conversation memory and a system prompt.
    """
    system_prompt = """
You are a helpful educational assistant. Answer questions and provide educational guidance.
"""
    past = st.session_state.memory.load_memory_variables({}).get("chat_history", [])
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Past Chat: {past}\n\nUser: {user_query}")
    ]
    try:
        response = chat.invoke(messages)
        st.session_state.memory.save_context({"input": user_query}, {"output": response.content})
        return response.content if response else "⚠️ No response."
    except Exception as e:
        return f"⚠️ Error: {str(e)}"

def create_txt_summary(mcqs, responses):
    """Create text summary for MCQ test results."""
    lines = []
    score = 0
    for i, (q, user_ans) in enumerate(zip(mcqs, responses)):
        correct = q[-1].strip().upper()
        is_correct = (user_ans.strip().upper() == correct)
        if is_correct:
            score += 1
        lines.append(f"Q{i+1}: {q[0]}")
        lines.append(f"   A: {q[1]}")
        lines.append(f"   B: {q[2]}")
        lines.append(f"   C: {q[3]}")
        lines.append(f"   D: {q[4]}")
        lines.append(f"Your Answer: {user_ans} | Correct Answer: {correct}")
        lines.append("Explanation: (Not provided)")
        lines.append("--------------------------------------")
    lines.insert(0, f"Final Score: {score} / {len(mcqs)}\\n")
    return "\n".join(lines)

def create_pdf_summary(mcqs, responses):
    """Create a PDF summary of the MCQ test results and return its bytes."""
    score = 0
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "MCQ Test Results", ln=True, align="C")
    pdf.ln(5)
    for i, (q, user_ans) in enumerate(zip(mcqs, responses)):
        correct = q[-1].strip().upper()
        is_correct = (user_ans.strip().upper() == correct)
        if is_correct:
            score += 1
        pdf.multi_cell(0, 10, f"Q{i+1}: {q[0]}")
        pdf.multi_cell(0, 10, f"A: {q[1]}")
        pdf.multi_cell(0, 10, f"B: {q[2]}")
        pdf.multi_cell(0, 10, f"C: {q[3]}")
        pdf.multi_cell(0, 10, f"D: {q[4]}")
        pdf.multi_cell(0, 10, f"Your Answer: {user_ans} | Correct Answer: {correct}")
        pdf.multi_cell(0, 10, "Explanation: (Not provided)")
        pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
    pdf.set_font("Arial", size=14)
    pdf.cell(0, 10, f"Final Score: {score} / {len(mcqs)}", ln=True, align="C")
    return pdf.output(dest="S").encode("latin1")

# ------------------------------
# Custom CSS for Modern, Attractive UI
# ------------------------------
st.markdown(
    """
    <style>
    body { background: linear-gradient(90deg, #74ABE2, #5563DE); color: #E0E0E0; }
    .stButton>button { background-color: #ff5c5c; color: #fff; border-radius: 8px; border: none; padding: 0.5rem 1rem; }
    .stButton>button:hover { background-color: #ff3c3c; }
    .title-container { text-align: center; font-size: 48px; font-weight: bold; margin-top: 10px; }
    .sidebar .sidebar-content { background-color: #333333; color: #E0E0E0; padding: 1rem; border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------
# Main App UI
# ------------------------------
st.markdown("<div class='title-container'>Interactive MCQ & Chatbot Generator</div>", unsafe_allow_html=True)

if mode == "Document MCQ":
    st.sidebar.markdown("### Document MCQ Mode")
    st.sidebar.write("Upload a document to generate an interactive MCQ test.")
    
    uploaded_file = st.file_uploader("Upload Document (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])
    
    if uploaded_file is not None:
        if allowed_file(uploaded_file.name):
            file_bytes = uploaded_file.read()
            file_obj = BytesIO(file_bytes)
            doc_text = extract_text(file_obj, uploaded_file.name)
            if doc_text:
                st.success("Document processed successfully!")
                st.write("Document preview (first 500 characters):")
                st.write(doc_text[:500] + "...")
                num_questions = st.number_input("Number of MCQs:", min_value=1, max_value=20, value=5)
                if st.button("Generate MCQ Test"):
                    try:
                        # Fixed multiline f-string without escapes:
                        mcq_list = ast.literal_eval(
                            ChatGroq(
                                temperature=0.7,
                                groq_api_key=GROQ_API_KEY,
                                model_name="llama3-70b-8192"
                            ).invoke([
                                HumanMessage(content=f"""You are an expert educational assessment generator. Generate a list of multiple-choice questions based on the following document text. Each question must be a Python list of 6 elements: [Question, OptionA, OptionB, OptionC, OptionD, CorrectOption]. Provide only a Python list output.
Document Text:
{doc_text}
""")
                            ]).content
                        )
                    except Exception as e:
                        st.error("Error generating MCQs: " + str(e))
                        mcq_list = []
                    if mcq_list and isinstance(mcq_list, list) and len(mcq_list) > 0:
                        st.session_state.mcqs = mcq_list
                        st.session_state.total = len(mcq_list)
                        st.session_state.current_q = 0
                        st.session_state.score = 0
                        st.session_state.answers = ["" for _ in range(len(mcq_list))]
                        st.session_state.done = False
                        st.success("MCQ Test Generated! Begin the test below.")
                    else:
                        st.error("No valid MCQs generated. Please try again.")
            else:
                st.error("Could not extract text from the document.")
        else:
            st.error("Invalid file format.")
    
    # If test is generated, display one question at a time
    if "mcqs" in st.session_state and st.session_state.get("mcqs") and not st.session_state.get("done", False):
        current = st.session_state.current_q
        total = st.session_state.total
        if current < total:
            q_data = st.session_state.mcqs[current]
            # Each question is a list: [Question, OptionA, OptionB, OptionC, OptionD, CorrectOption]
            st.markdown(f"### Question {current+1} of {total}")
            st.write(q_data[0])
            option_letters = ["A", "B", "C", "D"]
            options = [f"{letter}: {q_data[i+1]}" for i, letter in enumerate(option_letters)]
            user_choice = st.radio("Select your answer:", options, key=f"q{current}_options")
            if st.button("Submit Answer", key=f"submit_{current}"):
                selected_letter = user_choice.split(":")[0].strip().upper()
                st.session_state.answers[current] = selected_letter
                correct_letter = q_data[-1].strip().upper()
                if selected_letter == correct_letter:
                    st.success("Correct Answer! 🎉")
                    st.session_state.score += 1
                else:
                    st.error(f"Incorrect! The correct answer is {correct_letter}.")
                    st.info("Explanation: (Not provided)")
                if current < total - 1:
                    if st.button("Next Question", key=f"next_{current}"):
                        st.session_state.current_q += 1
                        st.experimental_rerun()
                else:
                    st.session_state.done = True
                    st.experimental_rerun()
    
    # Final Summary after test completion
    if "mcqs" in st.session_state and st.session_state.get("done", False):
        st.markdown("## Test Completed!")
        st.write(f"Final Score: {st.session_state.score} out of {st.session_state.total}")
        summary_txt = create_txt_summary(st.session_state.mcqs, st.session_state.answers)
        st.text_area("Test Summary", summary_txt, height=300)
        st.download_button("Download Summary as TXT", summary_txt, file_name="mcq_results.txt", mime="text/plain")
        pdf_bytes = create_pdf_summary(st.session_state.mcqs, st.session_state.answers)
        st.download_button("Download Summary as PDF", pdf_bytes, file_name="mcq_results.pdf", mime="application/pdf")
        if st.button("New Test"):
            st.session_state.clear()
            st.experimental_rerun()

elif mode == "Chatbot":
    st.sidebar.markdown("### Chatbot Mode")
    st.sidebar.write("Ask any educational question or discuss topics.")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "system", "content": "You are a helpful educational assistant."}
        ]
    user_input = st.text_input("Your message:")
    if st.button("Send") and user_input.strip() != "":
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.spinner("Assistant is typing..."):
            try:
                response = chat.invoke([HumanMessage(content=user_input)])
            except Exception as e:
                response = type("obj", (), {"content": f"Error: {str(e)}"})
        st.session_state.chat_history.append({"role": "assistant", "content": response.content})
    st.markdown("---")
    st.markdown("### Conversation:")
    for msg in st.session_state.chat_history:
        if msg["role"] == "assistant":
            st.markdown(f"<div class='chat-container assistant-bubble'>{msg['content']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-container user-bubble'>{msg['content']}</div>", unsafe_allow_html=True)
