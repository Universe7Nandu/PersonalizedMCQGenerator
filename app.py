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
# Fallback import for older langchain versions:
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
st.set_page_config(page_title="Adaptive MCQ & Chatbot", layout="wide")

# Hardcode your Groq API key (not recommended for production)
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
    """Generate a TXT summary from the MCQ results."""
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
    A normal chatbot query function.
    We store the conversation in st.session_state.memory
    """
    # Your specified system prompt
    system_prompt = """
System Prompt: You are an expert educational assessment generator trained to provide engaging multiple-choice questions (MCQs) for enterprise-level adaptive learning systems. 
You can also answer general educational queries. 
Remember to keep your answers clear, concise, and helpful.
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
    Enforce your specified format:
    - A python list, with each nested list:
      For 4-option Q: [Que, A, B, C, D, Ans] => 6 elements
      For T/F Q: [Que, True, False, Ans] => 3 elements
    - Only a python list is returned
    """
    system_prompt = f"""
System Prompt: You are an expert educational assessment generator trained provide engaging multiple-choice questions (MCQs) for enterprise-level adaptive learning systems on the given text. 
Your task is to:
1. Analyze the text to generate relevant MCQs.
2. The questions should be accurate and not based on your imagination.
3. Generate four answer choices for each question (A, B, C, D) ensuring only one is correct, or for True/False, just two options [True, False].
4. Mark the correct answer clearly using the format: [Que, A, B, C, D, Ans] or [Que, True, False, Ans].
5. Output only a python list with each nested list having either 6 or 3 elements.
6. Provide only a python list, nothing more.
"""

    user_prompt = f"""
Generate exactly {num_questions} MCQs from the following text. 
Text:
\"\"\"{doc_text}\"\"\"
Remember the required format:
- [Question, A, B, C, D, Ans] for 4-option questions 
- [Question, True, False, Ans] for True/False questions
Output only a python list, with no extra commentary.
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]

    response = await chat.ainvoke(messages)
    return response.content

def generate_mcqs(doc_text, num_questions):
    """Wrapper to run the async MCQ generation in a blocking way."""
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
# CUSTOM CSS FOR A MODERN, ATTRACTIVE UI
###############################################################################
st.markdown("""
<style>
/* Overall background gradient */
body {
    background: linear-gradient(120deg, #2F2FA2, #FF5C5C) !important;
    color: #E0E0E0 !important;
}
/* Container spacing */
.block-container {
    padding: 2rem;
}
/* Sidebar styling */
.sidebar .sidebar-content {
    background-color: #1E1E2F !important;
    color: #E0E0E0 !important;
    padding: 1rem;
    border-radius: 8px;
}
/* Buttons with hover effect */
.stButton>button {
    background-color: #ff5c5c;
    color: #fff;
    border-radius: 8px;
    border: none;
    padding: 0.6rem 1.2rem;
    transition: background-color 0.3s ease;
}
.stButton>button:hover {
    background-color: #ff3c3c !important;
}
/* Headings color override */
h1, h2, h3, h4, h5, label {
    color: #fff !important;
}
/* Chat bubble style */
.chat-bubble {
    padding: 12px 18px;
    border-radius: 15px;
    margin-bottom: 10px;
    max-width: 75%;
    line-height: 1.5;
    font-size: 16px;
}
/* User bubble */
.user-bubble {
    background-color: #3944BC;
    color: #fff;
    margin-left: auto;
    text-align: right;
    border-top-right-radius: 0px;
}
/* Assistant bubble */
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
st.write("**A scalable AI system** that transforms educational content into engaging assessment tools with detailed insights.")

if mode == "MCQ Generator":
    # 1) Document Upload
    uploaded_file = st.file_uploader("Upload a Document (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])
    if uploaded_file:
        file_bytes = uploaded_file.read()
        file_obj = BytesIO(file_bytes)
        doc_text = extract_text(file_obj, uploaded_file.name)
        if doc_text:
            st.success("Document processed successfully!")
            st.write("**Preview** (first 500 characters):")
            st.write(doc_text[:500] + "...")
            
            # 2) Number of MCQs
            num_questions = st.number_input("Number of MCQs to generate", min_value=1, max_value=20, value=5)
            
            # Session states for MCQs
            if "mcqs" not in st.session_state:
                st.session_state.mcqs = []
            if "current_q" not in st.session_state:
                st.session_state.current_q = 0
            if "user_answers" not in st.session_state:
                st.session_state.user_answers = []
            if "done" not in st.session_state:
                st.session_state.done = False
            
            # 3) Generate MCQs
            with st.form("mcq_form"):
                submitted = st.form_submit_button("Generate MCQs")  # pressing Enter or button triggers
                if submitted:
                    st.session_state.mcqs = generate_mcqs(doc_text, num_questions)
                    st.session_state.current_q = 0
                    st.session_state.user_answers = ["" for _ in range(len(st.session_state.mcqs))]
                    st.session_state.done = False
                    if st.session_state.mcqs:
                        st.success(f"Generated {len(st.session_state.mcqs)} MCQs. Scroll down to begin answering!")
                    else:
                        st.warning("No MCQs generated. Try adjusting your content or question count.")
            
            # 4) Display MCQs if available
            if st.session_state.mcqs and not st.session_state.done:
                idx = st.session_state.current_q
                total = len(st.session_state.mcqs)
                if idx < total:
                    mcq = st.session_state.mcqs[idx]
                    st.write(f"**Question {idx+1} of {total}**")
                    st.write(mcq[0])
                    
                    # Distinguish between 4-option or T/F
                    if len(mcq) == 6:
                        # 4-option question
                        letters = ["A", "B", "C", "D"]
                        options = [f"{letters[i]}) {mcq[i+1]}" for i in range(4)]
                    elif len(mcq) == 3:
                        # T/F question
                        options = [f"True) {mcq[1]}", f"False) {mcq[2]}"]
                    else:
                        st.warning("Invalid MCQ format. Skipping this question.")
                        st.session_state.current_q += 1
                        st.experimental_rerun()
                    
                    # If user hasn't chosen an answer, default to ""
                    if st.session_state.user_answers[idx] == "":
                        st.session_state.user_answers[idx] = ""
                    
                    user_choice = st.radio("Select an answer:", options, key=f"mcq_{idx}")
                    
                    if st.button("Submit Answer", key=f"submit_{idx}"):
                        # Extract selected letter from the user's choice
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
                
                # 5) Final summary
                if st.session_state.done:
                    st.write("## Test Completed!")
                    score = 0
                    for i, ans in enumerate(st.session_state.user_answers):
                        correct = st.session_state.mcqs[i][-1].strip().upper()
                        if ans.strip().upper() == correct:
                            score += 1
                    total_q = len(st.session_state.mcqs)
                    st.write(f"**Final Score:** {score}/{total_q}")
                    
                    summary_txt = create_txt_summary(st.session_state.mcqs, st.session_state.user_answers)
                    st.text_area("Test Summary", summary_txt, height=300)
                    
                    st.download_button("Download Summary as TXT", summary_txt, file_name="mcq_results.txt", mime="text/plain")
                    pdf_bytes = create_pdf_summary(st.session_state.mcqs, st.session_state.user_answers)
                    st.download_button("Download Summary as PDF", pdf_bytes, file_name="mcq_results.pdf", mime="application/pdf")
                    
                    if st.button("New Test"):
                        for key in ["mcqs", "current_q", "user_answers", "done"]:
                            st.session_state.pop(key, None)
                        st.experimental_rerun()

elif mode == "Chatbot":
    st.write("## Educational Chatbot")
    st.write("Ask questions or clarifications about educational topics. Press **Enter** or click **Send** to submit.")
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "You are a helpful educational assistant."}
        ]
    
    # Use a form so pressing Enter also submits
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
