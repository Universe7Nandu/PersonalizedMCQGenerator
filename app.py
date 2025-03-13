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

# Fallback import for older langchain versions
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

# Hardcode your Groq API key (for demo). In production, store it securely.
os.environ["GROQ_API_KEY"] = "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"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Chat Model + Memory
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
chat = ChatGroq(temperature=0.7, model_name="llama3-70b-8192", groq_api_key=GROQ_API_KEY)

###############################################################################
# UTILITY FUNCTIONS
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

def chat_to_txt(chat_history):
    """Convert chat history to plain text."""
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
    """Convert chat history to PDF bytes."""
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

def create_pdf_summary(mcqs, user_answers):
    """Generate a PDF summary of MCQ results."""
    score = 0
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "MCQ Test Results", ln=True, align="C")
    pdf.ln(5)

    for i, (mcq, ans) in enumerate(zip(mcqs, user_answers)):
        # MCQ => [Q, A, B, C, D, Ans, Explanation] or [Q, True, False, Ans, Explanation]
        question = mcq[0]
        correct_letter = mcq[-2].strip().upper()
        explanation = mcq[-1]
        selected = ans.strip().upper()
        if selected == correct_letter:
            score += 1

        pdf.multi_cell(0, 10, f"Q{i+1}: {question}")
        if len(mcq) == 7:
            # 4-option
            letters = ["A", "B", "C", "D"]
            for idx, opt in enumerate(mcq[1:5]):
                pdf.multi_cell(0, 10, f"{letters[idx]}) {opt}")
        elif len(mcq) == 5:
            # T/F
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
        else:
            lines.append(f"   True) {mcq[1]}")
            lines.append(f"   False) {mcq[2]}")

        lines.append(f"Your Answer: {selected} | Correct: {correct_letter}")
        lines.append(f"Explanation: {explanation}")
        lines.append("--------------------------------------")
    lines.insert(0, f"Final Score: {score} / {len(mcqs)}\n")
    return "\n".join(lines)

def query_chatbot(user_query):
    system_prompt = """
System Prompt: You are an expert educational assistant. Provide clear, concise, and helpful answers to educational queries.
"""
    if "memory" in st.session_state:
        past = st.session_state.memory.load_memory_variables({}).get("chat_history", [])
    else:
        past = []
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
System Prompt: You are an advanced educational assessment generator for an enterprise-level adaptive learning system.
Your tasks:
1. Analyze the provided text to generate relevant MCQs at {difficulty} difficulty.
2. For each question:
   - If it's a 4-option question, output [Question, A, B, C, D, Ans, Explanation] => 7 elements
   - If it's a True/False question, output [Question, True, False, Ans, Explanation] => 5 elements
3. 'Ans' is the correct letter (A/B/C/D) or 'True'/'False'
4. Explanation is a short reasoning or detail for the correct answer.
5. Output only a Python list. No commentary.
"""
    user_prompt = f"""
Generate exactly {num_questions} MCQs from this text:

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

###############################################################################
# CUSTOM CSS
###############################################################################
st.markdown("""
<style>
body {
    background: linear-gradient(135deg, #FF8C00, #FF0080);
    color: #E0E0E0 !important;
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
# MAIN APP
###############################################################################
st.title("Adaptive MCQ Generator & Chatbot")
st.write("A **scalable AI system** that transforms educational content into MCQs with difficulty levels & a dynamic chatbot.")

mode_selection = st.sidebar.radio("Select Mode", ["MCQ Generator", "Chatbot"])

if mode_selection == "MCQ Generator":
    uploaded_file = st.file_uploader("Upload Document (PDF, DOCX, or TXT)", type=["pdf","docx","txt"])
    if uploaded_file:
        # Extract text
        file_bytes = uploaded_file.read()
        file_obj = BytesIO(file_bytes)
        doc_text = extract_text(file_obj, uploaded_file.name)
        if doc_text:
            st.success("Document processed successfully!")
            st.write("**Document Preview** (first 500 characters):")
            st.write(doc_text[:500] + "...")

            difficulty = st.selectbox("Select Difficulty", ["Easy", "Moderate", "Hard"])
            num_questions = st.number_input("Number of MCQs to generate", min_value=1, max_value=20, value=5)

            if "mcqs" not in st.session_state:
                st.session_state.mcqs = []
            if "current_q" not in st.session_state:
                st.session_state.current_q = 0
            if "user_answers" not in st.session_state:
                st.session_state.user_answers = []
            if "done" not in st.session_state:
                st.session_state.done = False
            if "score" not in st.session_state:
                st.session_state.score = 0

            # Generate MCQs
            if st.button("Generate MCQs"):
                st.session_state.mcqs = generate_mcqs(doc_text, difficulty, num_questions)
                st.session_state.current_q = 0
                st.session_state.user_answers = ["" for _ in range(len(st.session_state.mcqs))]
                st.session_state.done = False
                st.session_state.score = 0
                if st.session_state.mcqs:
                    st.success(f"Generated {len(st.session_state.mcqs)} MCQs. Scroll down to begin!")
                else:
                    st.warning("No MCQs generated. Try adjusting your content or question count.")

            # Show MCQs
            if st.session_state.mcqs and not st.session_state.done:
                idx = st.session_state.current_q
                total = len(st.session_state.mcqs)

                if idx < total:
                    mcq = st.session_state.mcqs[idx]
                    st.markdown(f"### Question {idx+1} of {total}")
                    st.markdown(f"**{mcq[0]}**")

                    # Distinguish 4-option (7 elements) vs T/F (5 elements)
                    if len(mcq) == 7:
                        letters = ["A", "B", "C", "D"]
                        opts = [f"{letters[i]}) {mcq[i+1]}" for i in range(4)]
                    elif len(mcq) == 5:
                        opts = [f"True) {mcq[1]}", f"False) {mcq[2]}"]
                    else:
                        st.warning("Invalid MCQ format. Skipping this question.")
                        st.session_state.current_q += 1
                        st.stop()

                    # If user hasn't answered yet, default to ""
                    if st.session_state.user_answers[idx] == "":
                        st.session_state.user_answers[idx] = ""

                    user_choice = st.radio("Select your answer:", opts, key=f"radio_{idx}")

                    # Callback: Submit
                    def submit_callback():
                        selected_letter = user_choice.split(")")[0].strip().upper()
                        st.session_state.user_answers[idx] = selected_letter
                        correct_letter = mcq[-2].strip().upper()
                        explanation = mcq[-1]

                        if selected_letter == correct_letter:
                            st.success("Correct Answer! 🎉")
                            st.session_state.score += 1
                        else:
                            st.error(f"Incorrect! The correct answer is {correct_letter}.")
                            st.info(f"Explanation: {explanation}")

                    st.button("Submit Answer", key=f"submit_{idx}", on_click=submit_callback)

                    # Callback: Next
                    def next_callback():
                        st.session_state.current_q += 1
                        st.experimental_rerun()

                    # If not last question, show Next
                    if idx < total - 1:
                        st.button("Next Question", key=f"next_{idx}", on_click=next_callback)
                    else:
                        # Finish
                        def finish_callback():
                            st.session_state.done = True
                            st.experimental_rerun()

                        st.button("Finish", on_click=finish_callback)

            # Final summary
            if st.session_state.mcqs and st.session_state.done:
                st.markdown("## Test Completed!")
                total_q = len(st.session_state.mcqs)
                st.write(f"**Final Score:** {st.session_state.score} / {total_q}")

                summary_txt = create_txt_summary(st.session_state.mcqs, st.session_state.user_answers)
                st.text_area("Test Summary", summary_txt, height=300)
                st.download_button("Download Summary as TXT", summary_txt, file_name="mcq_results.txt", mime="text/plain")
                pdf_bytes = create_pdf_summary(st.session_state.mcqs, st.session_state.user_answers)
                st.download_button("Download Summary as PDF", pdf_bytes, file_name="mcq_results.pdf", mime="application/pdf")

                def new_test_callback():
                    for key in ["mcqs", "current_q", "user_answers", "done", "score"]:
                        st.session_state.pop(key, None)
                    st.experimental_rerun()

                st.button("New Test", on_click=new_test_callback)

else:
    # Chatbot
    st.write("## Educational Chatbot")
    st.write("Ask or discuss anything about educational topics. Chat history is displayed in the sidebar.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "You are a helpful educational assistant."}
        ]

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
        def reset_chat_callback():
            st.session_state.chat_history = [
                {"role": "assistant", "content": "You are a helpful educational assistant."}
            ]
            st.experimental_rerun()

        st.button("Reset Chat", on_click=reset_chat_callback)
