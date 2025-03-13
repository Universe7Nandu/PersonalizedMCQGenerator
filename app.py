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

# For older versions of langchain, fallback import
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
# CONFIG & SETUP
###############################################################################
st.set_page_config(page_title="Adaptive MCQ & Chatbot", layout="wide")

# Hardcode your Groq API key
os.environ["GROQ_API_KEY"] = "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"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Chat Model
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

chat = ChatGroq(
    temperature=0.7,
    model_name="llama3-70b-8192",
    groq_api_key=GROQ_API_KEY
)

###############################################################################
# UTILITIES
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
    """Generate a PDF summary of MCQ results."""
    score = 0
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "MCQ Test Results", ln=True, align="C")
    pdf.ln(5)

    for i, (mcq, ans) in enumerate(zip(mcqs, user_answers)):
        question = mcq[0]
        correct = mcq[-1].strip().upper()
        selected = ans.strip().upper()
        is_correct = (selected == correct)

        if is_correct:
            score += 1

        pdf.multi_cell(0, 10, f"Q{i+1}: {question}")
        if len(mcq) == 6:
            # 4-option question
            letters = ["A", "B", "C", "D"]
            for idx, opt in enumerate(mcq[1:5]):
                pdf.multi_cell(0, 10, f"{letters[idx]}) {opt}")
        elif len(mcq) == 3:
            # T/F question
            pdf.multi_cell(0, 10, f"True) {mcq[1]}")
            pdf.multi_cell(0, 10, f"False) {mcq[2]}")

        pdf.multi_cell(0, 10, f"Your Answer: {selected} | Correct: {correct}")
        pdf.multi_cell(0, 10, "Explanation: (Not provided)")
        pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    pdf.set_font("Arial", size=14)
    pdf.cell(0, 10, f"Final Score: {score} / {len(mcqs)}", ln=True, align="C")
    return pdf.output(dest="S").encode("latin1")

def create_txt_summary(mcqs, user_answers):
    """Generate a TXT summary of MCQ results."""
    lines = []
    score = 0
    for i, (mcq, ans) in enumerate(zip(mcqs, user_answers)):
        question = mcq[0]
        correct = mcq[-1].strip().upper()
        selected = ans.strip().upper()
        is_correct = (selected == correct)

        if is_correct:
            score += 1

        lines.append(f"Q{i+1}: {question}")
        if len(mcq) == 6:
            # 4-option question
            letters = ["A", "B", "C", "D"]
            for idx, opt in enumerate(mcq[1:5]):
                lines.append(f"   {letters[idx]}) {opt}")
        elif len(mcq) == 3:
            # T/F question
            lines.append(f"   True) {mcq[1]}")
            lines.append(f"   False) {mcq[2]}")

        lines.append(f"Your Answer: {selected} | Correct: {correct}")
        lines.append("Explanation: (Not provided)")
        lines.append("--------------------------------------")
    lines.insert(0, f"Final Score: {score} / {len(mcqs)}\n")
    return "\n".join(lines)

def query_chatbot(user_query):
    """
    Chatbot query function, storing conversation in memory.
    """
    system_prompt = """
System Prompt: You are an expert educational assistant. You can answer general educational queries 
and also generate MCQs in the specified format if requested. 
Provide helpful, concise answers.
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

async def async_generate_mcqs(doc_text, num_questions):
    """
    MCQ format:
      - [Question, A, B, C, D, Ans] (6 elements) for 4-option
      - [Question, True, False, Ans] (3 elements) for T/F
    Output only a python list, nothing more.
    """
    system_prompt = """
System Prompt: You are an expert educational assessment generator trained to produce multiple-choice questions (MCQs) 
in the following format:
- [Question, A, B, C, D, Ans] if it's a 4-option question (6 elements total)
- [Question, True, False, Ans] if it's a True/False question (3 elements total)
Output only a python list, with no extra commentary or text.
    """

    user_prompt = f"""
Generate exactly {num_questions} MCQs from the text below:
\"\"\"{doc_text}\"\"\"
Remember:
- Only produce a Python list
- Each nested list must have 3 or 6 elements, depending on T/F or 4-option
"""
    msgs = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]
    response = await chat.ainvoke(msgs)
    return response.content

def generate_mcqs(doc_text, num_questions):
    """Blocking wrapper for async MCQ generation."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(async_generate_mcqs(doc_text, num_questions))
    loop.close()
    try:
        data = ast.literal_eval(result)
        return data
    except Exception as e:
        st.error(f"Error parsing MCQ output: {e}")
        return []

###############################################################################
# ADDITIONAL: Download Chat as PDF/TXT
###############################################################################
def chat_to_txt(chat_history):
    """Convert entire chat to text format."""
    lines = []
    for msg in chat_history:
        role = msg["role"]
        content = msg["content"]
        if role == "assistant":
            lines.append(f"Assistant: {content}")
        else:
            lines.append(f"You: {content}")
    return "\n".join(lines)

def chat_to_pdf(chat_history):
    """Convert entire chat to PDF bytes."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "Chat History", ln=True, align="C")
    pdf.ln(5)
    for msg in chat_history:
        role = msg["role"]
        content = msg["content"]
        if role == "assistant":
            pdf.multi_cell(0, 10, f"Assistant: {content}")
        else:
            pdf.multi_cell(0, 10, f"You: {content}")
        pdf.ln(2)
    return pdf.output(dest="S").encode("latin1")

###############################################################################
# CUSTOM CSS FOR COLORFUL THEME
###############################################################################
st.markdown("""
<style>
body {
    background: linear-gradient(135deg, #e09, #d0e);
    color: #E0E0E0 !important;
}
.block-container {
    padding: 2rem;
}
.sidebar .sidebar-content {
    background: #2E294E;
    color: #E0E0E0;
    border-radius: 8px;
    padding: 1rem;
}
.stButton>button {
    background: #ff5c5c;
    color: #fff;
    border-radius: 8px;
    border: none;
    padding: 0.5rem 1rem;
    transition: background-color 0.3s ease;
}
.stButton>button:hover {
    background: #ff1c1c !important;
}
h1, h2, h3, h4, h5, label {
    color: #fff !important;
}
.chat-bubble {
    padding: 12px 18px;
    border-radius: 15px;
    margin-bottom: 10px;
    max-width: 80%;
    line-height: 1.5;
    font-size: 16px;
}
.user-bubble {
    background-color: #3944BC;
    color: #fff;
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
.option-box {
    background: #3C3C3C;
    margin: 5px 0;
    padding: 10px;
    border-radius: 6px;
    transition: background 0.2s;
}
.option-box:hover {
    background: #505050;
}
</style>
""", unsafe_allow_html=True)

###############################################################################
# SIDEBAR
###############################################################################
st.sidebar.title("Adaptive MCQ & Chatbot")
mode = st.sidebar.radio("Select Mode:", ["MCQ Generator", "Chatbot"])

###############################################################################
# MAIN
###############################################################################
st.title("Adaptive MCQ Generator & Chatbot")
st.write("A **scalable AI system** that transforms educational content into engaging MCQs and provides a dynamic chatbot interface.")

if mode == "MCQ Generator":
    uploaded_file = st.file_uploader("Upload Document (PDF, DOCX, or TXT)", type=["pdf","docx","txt"])
    if uploaded_file:
        file_bytes = uploaded_file.read()
        file_obj = BytesIO(file_bytes)
        doc_text = extract_text(file_obj, uploaded_file.name)
        if doc_text:
            st.success("Document processed successfully!")
            st.write("**Document Preview** (first 500 characters):")
            st.write(doc_text[:500] + "...")

            # Setup states
            if "mcqs" not in st.session_state:
                st.session_state.mcqs = []
            if "current_q" not in st.session_state:
                st.session_state.current_q = 0
            if "user_answers" not in st.session_state:
                st.session_state.user_answers = []
            if "done" not in st.session_state:
                st.session_state.done = False

            num_questions = st.number_input("Number of MCQs to generate", min_value=1, max_value=20, value=5)

            # Generate MCQs
            if st.button("Generate MCQs"):
                st.session_state.mcqs = generate_mcqs(doc_text, num_questions)
                st.session_state.current_q = 0
                st.session_state.user_answers = ["" for _ in range(len(st.session_state.mcqs))]
                st.session_state.done = False
                if st.session_state.mcqs:
                    st.success(f"Generated {len(st.session_state.mcqs)} MCQs. Scroll down to begin!")
                else:
                    st.warning("No MCQs generated. Try adjusting your content or question count.")

            # Display MCQs
            if st.session_state.mcqs and not st.session_state.done:
                idx = st.session_state.current_q
                total = len(st.session_state.mcqs)
                if idx < total:
                    mcq = st.session_state.mcqs[idx]
                    st.markdown(f"### Question {idx+1} of {total}")
                    st.markdown(f"**{mcq[0]}**")

                    # Distinguish between 4-option or T/F
                    if len(mcq) == 6:
                        letters = ["A", "B", "C", "D"]
                        opts = [f"{letters[i]}) {mcq[i+1]}" for i in range(4)]
                    elif len(mcq) == 3:
                        # T/F
                        opts = [f"True) {mcq[1]}", f"False) {mcq[2]}"]
                    else:
                        st.warning("Invalid MCQ format. Skipping this question.")
                        st.session_state.current_q += 1
                        # Moved rerun to button callback, so no top-level rerun
                        st.stop()

                    if st.session_state.user_answers[idx] == "":
                        st.session_state.user_answers[idx] = ""

                    user_choice = st.radio("Select your answer:", opts, key=f"mcq_{idx}")

                    if st.button("Submit Answer", key=f"submit_{idx}"):
                        selected_letter = user_choice.split(")")[0].strip().upper()
                        st.session_state.user_answers[idx] = selected_letter
                        correct_letter = mcq[-1].strip().upper()

                        if selected_letter == correct_letter:
                            st.success("Correct Answer! 🎉")
                        else:
                            st.error(f"Incorrect! The correct answer is {correct_letter}.")
                            st.info("Explanation: (Not provided)")

                        # Move on or finalize
                        if idx < total - 1:
                            if st.button("Next Question", key=f"next_{idx}"):
                                st.session_state.current_q += 1
                                st.experimental_rerun()
                        else:
                            st.success("Test Completed!")
                            st.session_state.done = True
                            st.experimental_rerun()

                if st.session_state.done:
                    st.markdown("## Test Completed!")
                    # Score
                    score = 0
                    for i, ans in enumerate(st.session_state.user_answers):
                        correct = st.session_state.mcqs[i][-1].strip().upper()
                        if ans.strip().upper() == correct:
                            score += 1
                    total_q = len(st.session_state.mcqs)
                    st.write(f"**Final Score:** {score} / {total_q}")

                    summary_txt = create_txt_summary(st.session_state.mcqs, st.session_state.user_answers)
                    st.text_area("Test Summary", summary_txt, height=300)
                    st.download_button("Download Summary as TXT", summary_txt, file_name="mcq_results.txt", mime="text/plain")
                    pdf_bytes = create_pdf_summary(st.session_state.mcqs, st.session_state.user_answers)
                    st.download_button("Download Summary as PDF", pdf_bytes, file_name="mcq_results.pdf", mime="application/pdf")

                    if st.button("New Test"):
                        for key in ["mcqs", "current_q", "user_answers", "done"]:
                            st.session_state.pop(key, None)
                        st.experimental_rerun()

else:
    # Chatbot
    st.write("## Educational Chatbot")
    st.write("Ask or discuss anything about educational topics. Press **Enter** or **Send** to submit. You can also download or reset the chat below.")
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "You are a helpful educational assistant."}
        ]

    # Chat form
    with st.form("chat_form"):
        user_input = st.text_input("Your message:")
        send_submitted = st.form_submit_button("Send")
    
    if send_submitted and user_input.strip():
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.spinner("Assistant is typing..."):
            response_content = query_chatbot(user_input)
        st.session_state.chat_history.append({"role": "assistant", "content": response_content})

    st.markdown("---")
    st.write("### Conversation:")
    for msg in st.session_state.chat_history:
        if msg["role"] == "assistant":
            st.markdown(f"<div class='chat-bubble assistant-bubble'>{msg['content']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-bubble user-bubble'>{msg['content']}</div>", unsafe_allow_html=True)

    # Buttons to download or reset chat
    col1, col2, col3 = st.columns([1,1,1])
    with col1:
        if st.button("Download Chat as TXT"):
            txt_data = chat_to_txt(st.session_state.chat_history)
            st.download_button("Save Chat (TXT)", txt_data, file_name="chat_history.txt", mime="text/plain", key="download_txt")
    with col2:
        if st.button("Download Chat as PDF"):
            pdf_data = chat_to_pdf(st.session_state.chat_history)
            st.download_button("Save Chat (PDF)", pdf_data, file_name="chat_history.pdf", mime="application/pdf", key="download_pdf")
    with col3:
        if st.button("Reset Chat"):
            st.session_state.chat_history = [
                {"role": "assistant", "content": "You are a helpful educational assistant."}
            ]
            # Instead of top-level rerun, do it in button callback
            st.experimental_rerun()
