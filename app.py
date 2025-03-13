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
# For older versions of langchain, we might need a fallback import
try:
    from langchain.schema import HumanMessage, SystemMessage
except ImportError:
    from langchain.schema.chat_message import HumanMessage, SystemMessage

from langchain.memory import ConversationBufferMemory

###############################################################################
# ALLOW ASYNCIO IN STREAMLIT
###############################################################################
nest_asyncio.apply()

###############################################################################
# CONFIGURATION
###############################################################################
st.set_page_config(page_title="Adaptive MCQ Generator", layout="wide")

# Hardcode your Groq API key (not recommended for production)
os.environ["GROQ_API_KEY"] = "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"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Chat Model
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

chat = ChatGroq(temperature=0.7, model_name="llama3-70b-8192", groq_api_key=GROQ_API_KEY)

###############################################################################
# UTILS
###############################################################################
def extract_text(file_obj, filename):
    """Extract text from PDF, DOCX, or TXT."""
    ext = filename.rsplit('.', 1)[1].lower()
    if ext == "pdf":
        try:
            with pdfplumber.open(file_obj) as pdf:
                return "".join(page.extract_text() or "" for page in pdf.pages)
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

def create_pdf_summary(mcqs, user_answers):
    """Generate a PDF summary from the MCQ results."""
    score = 0
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, "MCQ Test Results", ln=True, align="C")
    pdf.ln(5)

    for i, (mcq, ans) in enumerate(zip(mcqs, user_answers)):
        question = mcq[0]
        options = mcq[1:5]
        correct = mcq[-1].strip().upper()
        selected = ans.strip().upper()
        is_correct = (selected == correct)
        if is_correct:
            score += 1
        pdf.multi_cell(0, 10, f"Q{i+1}: {question}")
        letters = ["A", "B", "C", "D"]
        for idx, opt in enumerate(options):
            pdf.multi_cell(0, 10, f"{letters[idx]}) {opt}")
        pdf.multi_cell(0, 10, f"Your Answer: {selected} | Correct: {correct}")
        pdf.multi_cell(0, 10, "Explanation: (Not provided)")
        pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    pdf.set_font("Arial", size=14)
    pdf.cell(0, 10, f"Final Score: {score} / {len(mcqs)}", ln=True, align="C")

    return pdf.output(dest="S").encode("latin1")

def create_txt_summary(mcqs, user_answers):
    """Generate a TXT summary from the MCQ results."""
    lines = []
    score = 0
    for i, (mcq, ans) in enumerate(zip(mcqs, user_answers)):
        question = mcq[0]
        options = mcq[1:5]
        correct = mcq[-1].strip().upper()
        selected = ans.strip().upper()
        is_correct = (selected == correct)
        if is_correct:
            score += 1
        lines.append(f"Q{i+1}: {question}")
        letters = ["A", "B", "C", "D"]
        for idx, opt in enumerate(options):
            lines.append(f"   {letters[idx]}) {opt}")
        lines.append(f"Your Answer: {selected} | Correct: {correct}")
        lines.append("Explanation: (Not provided)")
        lines.append("--------------------------------------")
    lines.insert(0, f"Final Score: {score} / {len(mcqs)}\n")
    return "\n".join(lines)

def query_chatbot(user_query):
    """
    A normal chatbot query function.
    We store the conversation in st.session_state.memory
    """
    system_prompt = """
You are a helpful educational assistant. Provide clear, concise answers or clarifications about educational topics.
    """
    past = st.session_state.memory.load_memory_variables({}).get("chat_history", [])
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Past Chat: {past}\n\nUser: {user_query}")
    ]
    try:
        response = chat.invoke(messages)
        st.session_state.memory.save_context({"input": user_query}, {"output": response.content})
        return response.content
    except Exception as e:
        return f"Error: {str(e)}"

###############################################################################
# MCQ GENERATION
###############################################################################
def generate_mcqs(doc_text, difficulty, num_questions):
    """
    Prompt the model to generate a Python list of MCQs:
    [Question, OptionA, OptionB, OptionC, OptionD, CorrectOption]
    """
    prompt = f"""
You are an expert educational assessment generator. 
Difficulty: {difficulty}
Generate exactly {num_questions} multiple-choice questions based on the following text.
Each question must be a Python list of 6 elements:
[Question, OptionA, OptionB, OptionC, OptionD, CorrectOption].
Output only a Python list. 
Text:
{doc_text}
    """
    try:
        msgs = [HumanMessage(content=prompt)]
        response = asyncio.run(chat.ainvoke(msgs))
        data = ast.literal_eval(response.content)
        return data
    except Exception as e:
        st.error(f"Error generating MCQs: {e}")
        return []

###############################################################################
# ADAPTIVE LOGIC (Simple Example)
###############################################################################
def adapt_difficulty(score_ratio, current_difficulty):
    """
    Very basic logic:
    If user scored above 80%, increase difficulty.
    If user scored below 40%, decrease difficulty.
    Otherwise, keep the same.
    """
    difficulties = ["Easy", "Medium", "Hard"]
    idx = difficulties.index(current_difficulty) if current_difficulty in difficulties else 1
    if score_ratio > 0.8 and idx < 2:
        return difficulties[idx + 1]
    elif score_ratio < 0.4 and idx > 0:
        return difficulties[idx - 1]
    else:
        return current_difficulty

###############################################################################
# CUSTOM CSS FOR DARK THEME
###############################################################################
st.markdown("""
<style>
body {
    background: linear-gradient(90deg, #74ABE2, #5563DE) !important;
    color: #E0E0E0 !important;
}
.block-container {
    padding: 2rem;
}
.sidebar .sidebar-content {
    background-color: #333333;
    color: #E0E0E0;
    padding: 1rem;
    border-radius: 8px;
}
.stButton>button {
    background-color: #ff5c5c;
    color: #fff;
    border-radius: 8px;
    border: none;
    padding: 0.5rem 1rem;
}
.stButton>button:hover {
    background-color: #ff3c3c;
}
h1, h2, h3, h4, h5, label {
    color: #fff !important;
}
.chat-bubble {
    padding: 12px 18px;
    border-radius: 15px;
    margin-bottom: 10px;
    max-width: 75%;
    line-height: 1.5;
    font-size: 16px;
}
.user-bubble {
    background-color: #1E88E5;
    color: white;
    margin-left: auto;
    text-align: right;
    border-top-right-radius: 0px;
}
.assistant-bubble {
    background-color: #333333;
    color: #E0E0E0;
    margin-right: auto;
    text-align: left;
    border-top-left-radius: 0px;
}
</style>
""", unsafe_allow_html=True)

###############################################################################
# SIDEBAR
###############################################################################
st.sidebar.title("Adaptive MCQ Generator")
mode = st.sidebar.radio("Select Mode:", ["MCQ Generator", "Chatbot"])

###############################################################################
# MAIN APP
###############################################################################
st.title("Adaptive MCQ Generator & Chatbot")
st.write("An enterprise solution that automatically generates and adapts MCQs from uploaded documents. "
         "It also includes a chatbot for additional clarifications.")

if mode == "MCQ Generator":
    # Step 1: Upload Document
    uploaded_file = st.file_uploader("Upload Document (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        file_obj = BytesIO(file_bytes)
        doc_text = extract_text(file_obj, uploaded_file.name)
        if doc_text:
            st.success("Document processed successfully!")
            st.write("**Document Preview** (first 500 characters):")
            st.write(doc_text[:500] + "...")
            
            # Step 2: Difficulty & Number of Questions
            difficulty = st.selectbox("Select Difficulty", ["Easy", "Medium", "Hard"], index=1)
            num_questions = st.number_input("Number of MCQs to generate", min_value=1, max_value=20, value=5)
            
            if "mcqs" not in st.session_state:
                st.session_state.mcqs = []
            if "current_q" not in st.session_state:
                st.session_state.current_q = 0
            if "user_answers" not in st.session_state:
                st.session_state.user_answers = []
            if "score" not in st.session_state:
                st.session_state.score = 0
            if "done" not in st.session_state:
                st.session_state.done = False
            if "curr_difficulty" not in st.session_state:
                st.session_state.curr_difficulty = difficulty

            # Step 3: Generate MCQs
            if st.button("Generate MCQs"):
                st.session_state.mcqs = generate_mcqs(doc_text, difficulty, num_questions)
                st.session_state.current_q = 0
                st.session_state.user_answers = [None]*len(st.session_state.mcqs)
                st.session_state.score = 0
                st.session_state.done = False
                st.session_state.curr_difficulty = difficulty
                if st.session_state.mcqs:
                    st.success(f"Generated {len(st.session_state.mcqs)} MCQs! Scroll down to begin.")
                else:
                    st.warning("No MCQs were generated. Please try again or modify your document/difficulty.")

            # Step 4: Display MCQs one by one
            if st.session_state.mcqs and not st.session_state.done:
                idx = st.session_state.current_q
                total_q = len(st.session_state.mcqs)
                if idx < total_q:
                    mcq = st.session_state.mcqs[idx]
                    st.write(f"**Question {idx+1} of {total_q}**")
                    st.write(mcq[0])  # The question
                    options = mcq[1:5]
                    letters = ["A", "B", "C", "D"]
                    
                    # If user hasn't chosen an answer, default to None
                    if st.session_state.user_answers[idx] is None:
                        st.session_state.user_answers[idx] = ""

                    user_choice = st.radio(
                        "Select an answer:",
                        [f"{letters[i]}. {options[i]}" for i in range(4)],
                        key=f"mcq_{idx}"
                    )
                    
                    if st.button("Submit Answer", key=f"submit_{idx}"):
                        selected_letter = user_choice.split(".")[0].strip().upper()
                        st.session_state.user_answers[idx] = selected_letter
                        correct_letter = mcq[-1].strip().upper()
                        if selected_letter == correct_letter:
                            st.success("Correct Answer! 🎉")
                            st.session_state.score += 1
                        else:
                            st.error(f"Incorrect! The correct answer is {correct_letter}.")
                            st.info("Explanation: (Not provided)")  # Could extend the prompt to get an explanation
                        
                        # Move to next question or finalize
                        if idx < total_q - 1:
                            if st.button("Next Question", key=f"next_{idx}"):
                                st.session_state.current_q += 1
                                st.experimental_rerun()
                        else:
                            st.success("Test Completed!")
                            st.session_state.done = True
                            st.experimental_rerun()
                
                # Step 5: Final summary after last question
                if st.session_state.done:
                    st.write("## Test Completed!")
                    final_score = st.session_state.score
                    total = len(st.session_state.mcqs)
                    st.write(f"Final Score: {final_score} / {total}")
                    
                    # Adaptive Difficulty
                    score_ratio = final_score / total
                    new_difficulty = adapt_difficulty(score_ratio, st.session_state.curr_difficulty)
                    st.info(f"Next recommended difficulty: {new_difficulty}")
                    
                    summary_txt = create_txt_summary(st.session_state.mcqs, st.session_state.user_answers)
                    st.text_area("Test Summary", summary_txt, height=300)
                    
                    st.download_button("Download as TXT", summary_txt, file_name="mcq_results.txt", mime="text/plain")
                    pdf_bytes = create_pdf_summary(st.session_state.mcqs, st.session_state.user_answers)
                    st.download_button("Download as PDF", pdf_bytes, file_name="mcq_results.pdf", mime="application/pdf")
                    
                    if st.button("New Test"):
                        for key in ["mcqs", "current_q", "user_answers", "score", "done"]:
                            st.session_state.pop(key, None)
                        st.experimental_rerun()

elif mode == "Chatbot":
    st.write("## Educational Chatbot")
    st.write("Ask any question or clarification about educational topics. The conversation is displayed below.")
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "You are a helpful educational assistant."}
        ]
    
    user_input = st.text_input("Your message:")
    if st.button("Send"):
        if user_input.strip():
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.spinner("Assistant is typing..."):
                response_content = query_chatbot(user_input)
            st.session_state.chat_history.append({"role": "assistant", "content": response_content})
    
    st.markdown("---")
    st.write("### Conversation:")
    for msg in st.session_state.chat_history:
        if msg["role"] == "assistant":
            st.markdown(
                f"<div class='chat-bubble assistant-bubble'>{msg['content']}</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"<div class='chat-bubble user-bubble'>{msg['content']}</div>",
                unsafe_allow_html=True
            )
