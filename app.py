import os
import ast
import asyncio
import nest_asyncio
import streamlit as st
import pdfplumber
import docx
from io import BytesIO
from fpdf import FPDF
from langchain_groq import ChatGroq

# Import langchain modules (ensure langchain>=0.3.20 is installed)
from langchain.schema import HumanMessage, SystemMessage
from langchain.memory import ConversationBufferMemory

# Allow asyncio to run in Streamlit
nest_asyncio.apply()

###############################################################################
# HELPER: Rerun the app
###############################################################################
def rerun_app():
    # Use experimental_rerun if available, else stop the script (which in some cases triggers a rerun)
    if hasattr(st, "experimental_rerun"):
        st.experimental_rerun()
    else:
        st.stop()

###############################################################################
# CONFIGURATION & SETUP
###############################################################################
st.set_page_config(page_title="Adaptive MCQ & Chatbot", layout="wide")

# Set your Groq API key (for demo purposes; use secure methods in production)
os.environ["GROQ_API_KEY"] = "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"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize conversation memory and chat model
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
chat = ChatGroq(temperature=0.7, model_name="llama3-70b-8192", groq_api_key=GROQ_API_KEY)

###############################################################################
# UTILITY FUNCTIONS
###############################################################################
def extract_text(file_obj, filename):
    """Extract text from PDF, DOCX, or TXT files."""
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
    score = 0
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "MCQ Test Results", ln=True, align="C")
    pdf.ln(5)
    for i, (mcq, ans) in enumerate(zip(mcqs, user_answers)):
        question = mcq[0]
        correct_letter = mcq[-2].strip().upper()  # correct answer is second-to-last element
        explanation = mcq[-1]
        selected = ans.strip().upper()
        if selected == correct_letter:
            score += 1
        pdf.multi_cell(0, 10, f"Q{i+1}: {question}")
        if len(mcq) == 7:
            letters = ["A", "B", "C", "D"]
            for idx, opt in enumerate(mcq[1:5]):
                pdf.multi_cell(0, 10, f"{letters[idx]}) {opt}")
        elif len(mcq) == 5:
            pdf.multi_cell(0, 10, f"True) {mcq[1]}")
            pdf.multi_cell(0, 10, f"False) {mcq[2]}")
        pdf.multi_cell(0, 10, f"Your Answer: {selected} | Correct: {correct_letter}")
        pdf.multi_cell(0, 10, f"Explanation: {explanation}")
        pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
    pdf.set_font("Arial", size=14)
    pdf.cell(0, 10, f"Final Score: {score} / {len(mcqs)}", ln=True, align="C")
    return pdf.output(dest="S").encode("latin1")

def create_txt_summary(mcqs, user_answers):
    lines = []
    score = 0
    for i, (mcq, ans) in enumerate(zip(mcqs, user_answers)):
        question = mcq[0]
        correct_letter = mcq[-2].strip().upper()
        explanation = mcq[-1]
        selected = ans.strip().upper()
        if selected == correct_letter:
            score += 1
        lines.append(f"Q{i+1}: {question}")
        if len(mcq) == 7:
            letters = ["A", "B", "C", "D"]
            for idx, opt in enumerate(mcq[1:5]):
                lines.append(f"   {letters[idx]}) {opt}")
        elif len(mcq) == 5:
            lines.append(f"   True) {mcq[1]}")
            lines.append(f"   False) {mcq[2]}")
        lines.append(f"Your Answer: {selected} | Correct: {correct_letter}")
        lines.append(f"Explanation: {explanation}")
        lines.append("--------------------------------------")
    lines.insert(0, f"Final Score: {score} / {len(mcqs)}\n")
    return "\n".join(lines)

def query_chatbot(user_query):
    system_prompt = """
System Prompt: You are an expert educational assistant. Provide clear and concise answers.
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

async def async_generate_mcqs(doc_text, difficulty, num_questions):
    system_prompt = f"""
System Prompt: You are an advanced educational assessment generator.
Your tasks:
1. Analyze the provided text to generate relevant MCQs at {difficulty} difficulty.
2. For each question, output in one of these formats:
   - 4-option: [Question, A, B, C, D, Ans, Explanation]
   - True/False: [Question, True, False, Ans, Explanation]
3. 'Ans' is the correct answer.
4. Output only a Python list with no extra commentary.
"""
    user_prompt = f"""
Generate exactly {num_questions} MCQs from the text below:

\"\"\"{doc_text}\"\"\"

Follow the above format strictly.
"""
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]
    response = await chat.ainvoke(messages)
    return response.content

def generate_mcqs(doc_text, difficulty, num_questions):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(async_generate_mcqs(doc_text, difficulty, num_questions))
    loop.close()
    try:
        data = ast.literal_eval(result)
        return data
    except Exception as e:
        st.error(f"Error parsing MCQ output: {e}")
        return []

def chat_to_txt(chat_history):
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
# CUSTOM CSS FOR DARK, PROFESSIONAL UI
###############################################################################
st.markdown("""
<style>
body {
    background: #121212;
    color: #E0E0E0;
    font-family: 'Segoe UI', sans-serif;
}
.block-container {
    padding: 2rem;
}
.sidebar .sidebar-content {
    background: #1F1F2E;
    color: #E0E0E0;
    border-radius: 8px;
    padding: 1rem;
}
.stButton>button {
    background: #FF5C5C;
    color: #fff;
    border-radius: 8px;
    border: none;
    padding: 0.6rem 1.2rem;
    transition: background-color 0.3s ease;
}
.stButton>button:hover {
    background: #FF1C1C !important;
}
h1, h2, h3, h4, h5, label {
    color: #fff !important;
}
.chat-bubble {
    padding: 12px 18px;
    border-radius: 15px;
    margin-bottom: 10px;
    max-width: 90%;
    line-height: 1.5;
    font-size: 16px;
}
.user-bubble {
    background-color: #3944BC;
    color: #fff;
    margin-left: auto;
    text-align: right;
}
.assistant-bubble {
    background-color: #333333;
    color: #E0E0E0;
    margin-right: auto;
    text-align: left;
}
.option-box {
    background: #3C3C3C;
    padding: 10px;
    border-radius: 6px;
    margin: 5px 0;
}
.option-box:hover {
    background: #505050;
}
</style>
""", unsafe_allow_html=True)

###############################################################################
# SIDEBAR - Chat History
###############################################################################
st.sidebar.title("Chat History")
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [{"role": "assistant", "content": "You are a helpful educational assistant."}]
for msg in st.session_state.chat_history:
    if msg["role"] == "assistant":
        st.sidebar.markdown(f"<div class='chat-bubble assistant-bubble'>{msg['content']}</div>", unsafe_allow_html=True)
    else:
        st.sidebar.markdown(f"<div class='chat-bubble user-bubble'>{msg['content']}</div>", unsafe_allow_html=True)

###############################################################################
# MAIN APP: Mode Selection
###############################################################################
mode_selection = st.sidebar.radio("Select Mode", ["MCQ Generator", "Chatbot"])

###############################################################################
# MCQ GENERATOR MODE
###############################################################################
if mode_selection == "MCQ Generator":
    st.title("Adaptive MCQ Generator")
    # Topic input and generate button (only if not already generated)
    if "topic" not in st.session_state or st.session_state.topic == "":
        topic_input = st.text_input("Enter Topic:")
        if st.button("Generate MCQs") and topic_input:
            st.session_state.topic = topic_input
            try:
                questions_str = query_llama3(topic_input)
                st.session_state.questions = ast.literal_eval(questions_str)
            except Exception as e:
                st.error("Error generating questions: " + str(e))
            if st.session_state.questions:
                st.success(f"Generated {len(st.session_state.questions)} MCQs. Please answer them below.")
            else:
                st.warning("No questions generated.")
            rerun_app()
    else:
        # Initialize test session state if not already
        if "current_question" not in st.session_state:
            st.session_state.current_question = 0
        if "score" not in st.session_state:
            st.session_state.score = 0
        if "answers" not in st.session_state:
            st.session_state.answers = [""] * len(st.session_state.questions)
        if "done" not in st.session_state:
            st.session_state.done = False

        # If test is not completed, show the current question
        if not st.session_state.done:
            idx = st.session_state.current_question
            total = len(st.session_state.questions)
            if idx < total:
                mcq = st.session_state.questions[idx]
                st.markdown(f"### Question {idx+1} of {total}")
                st.markdown(f"**{mcq[0]}**")
                # Assume MCQs are either 4-option ([Q, A, B, C, D, Ans, Explanation]) or True/False ([Q, True, False, Ans, Explanation])
                if len(mcq) == 7:
                    letters = ["A", "B", "C", "D"]
                    options = [f"{letters[i]}) {mcq[i+1]}" for i in range(4)]
                elif len(mcq) == 5:
                    options = [f"True) {mcq[1]}", f"False) {mcq[2]}"]
                else:
                    st.error("Invalid question format.")
                    st.session_state.current_question += 1
                    rerun_app()
                
                # Display options
                selected = st.radio("Select your answer:", options, key=f"q_{idx}")
                
                if st.button("Submit Answer", key=f"submit_{idx}"):
                    # Record answer and check
                    ans = selected.split(")")[0].strip().upper()
                    st.session_state.answers[idx] = ans
                    correct = mcq[-2].strip().upper()
                    if ans == correct:
                        st.success("Correct Answer! 🎉")
                        st.session_state.score += 1
                    else:
                        st.error(f"Incorrect. Correct answer: {correct}")
                        st.info(f"Explanation: {mcq[-1]}")
                    # Automatically move to next question after submission
                    st.session_state.current_question += 1
                    rerun_app()
            else:
                st.session_state.done = True
                rerun_app()
        
        # When test is completed, show summary
        if st.session_state.done:
            st.markdown("## Test Completed!")
            total_q = len(st.session_state.questions)
            st.write(f"**Final Score:** {st.session_state.score} / {total_q}")
            summary = create_txt_summary(st.session_state.questions, st.session_state.answers)
            st.text_area("Test Summary", summary, height=300)
            st.download_button("Download Summary as TXT", summary, file_name="mcq_results.txt", mime="text/plain")
            pdf_summary = create_pdf_summary(st.session_state.questions, st.session_state.answers)
            st.download_button("Download Summary as PDF", pdf_summary, file_name="mcq_results.pdf", mime="application/pdf")
            if st.button("New Test"):
                for key in ["topic", "questions", "current_question", "score", "answers", "done"]:
                    st.session_state.pop(key, None)
                rerun_app()

###############################################################################
# CHATBOT MODE
###############################################################################
else:
    st.title("Educational Chatbot")
    st.write("Ask any educational questions. Your chat history appears in the sidebar.")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [{"role": "assistant", "content": "You are a helpful educational assistant."}]
    with st.form("chat_form"):
        user_msg = st.text_input("Your message:")
        send = st.form_submit_button("Send")
    if send and user_msg.strip():
        st.session_state.chat_history.append({"role": "user", "content": user_msg})
        with st.spinner("Assistant is typing..."):
            reply = query_chatbot(user_msg)
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
    st.markdown("---")
    st.write("### Conversation:")
    for m in st.session_state.chat_history:
        if m["role"] == "assistant":
            st.markdown(f"<div class='chat-bubble assistant-bubble'>{m['content']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-bubble user-bubble'>{m['content']}</div>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Download Chat as TXT"):
            chat_txt = chat_to_txt(st.session_state.chat_history)
            st.download_button("Save Chat (TXT)", chat_txt, file_name="chat_history.txt", mime="text/plain", key="chat_txt")
    with col2:
        if st.button("Download Chat as PDF"):
            chat_pdf = chat_to_pdf(st.session_state.chat_history)
            st.download_button("Save Chat (PDF)", chat_pdf, file_name="chat_history.pdf", mime="application/pdf", key="chat_pdf")
    with col3:
        reset_chk = st.checkbox("Confirm Reset Chat")
        if st.button("Reset Chat", key="reset_chat") and reset_chk:
            st.session_state.chat_history = [{"role": "assistant", "content": "You are a helpful educational assistant."}]
            rerun_app()
