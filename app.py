import os
import ast
import asyncio
import nest_asyncio
import streamlit as st
import pdfplumber
import docx
import pandas as pd
import matplotlib.pyplot as plt
import time
import random
import uuid
from datetime import datetime
from io import BytesIO, StringIO
from fpdf import FPDF
from langchain_groq import ChatGroq
from langchain.schema import HumanMessage, SystemMessage
from langchain.memory import ConversationBufferMemory

# Allow asyncio to run in Streamlit
nest_asyncio.apply()

###############################################################################
# CONFIGURATION & SETUP
###############################################################################
st.set_page_config(
    page_title="EduMind AI: MCQ Generator & Chatbot",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state variables
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.chat_history = []
    st.session_state.all_chats = {}
    st.session_state.current_chat_id = str(uuid.uuid4())
    st.session_state.all_chats[st.session_state.current_chat_id] = {
        "title": "New Chat",
        "messages": [],
        "created_at": datetime.now()
    }
    st.session_state.mcq_history = {}
    st.session_state.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    st.session_state.show_welcome = True
    st.session_state.default_num_questions = 10
    st.session_state.default_difficulty = "Medium"
    st.session_state.mcq_topic = ""
    st.session_state.mcq_questions = []
    st.session_state.mcq_current_question = 0
    st.session_state.mcq_answers = []
    st.session_state.mcq_test_completed = False
    st.session_state.mcq_test_id = None
    st.session_state.file_text = ""
    st.session_state.topics = []
    st.session_state.timer_duration = 300  # example: 5 minutes
    st.session_state.test_start_time = time.time()

# Set your Groq API key
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
os.environ["GROQ_API_KEY"] = GROQ_API_KEY

# Initialize chat model
chat = ChatGroq(temperature=0.7, model_name="llama3-70b-8192", groq_api_key=GROQ_API_KEY)

def load_css():
    return """
    <style>
    /* Global Styles */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    :root {
        --primary-color: #4A56E2;
        --secondary-color: #6E7CE6;
        --accent-color: #8B5CF6;
        --background-dark: #111827;
        --card-bg: #1F2937;
        --sidebar-bg: #111827;
        --text-color: #E5E7EB;
        --text-secondary: #9CA3AF;
        --success-color: #10B981;
        --warning-color: #F59E0B;
        --error-color: #EF4444;
        --border-color: #374151;
    }
    
    body {
        font-family: 'Inter', sans-serif;
        background-color: var(--background-dark);
        color: var(--text-color);
    }
    
    /* Chat message styling */
    .chat-message {
        padding: 1rem;
        border-radius: 0.7rem;
        margin-bottom: 1rem;
        display: flex;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
    }
    
    .chat-message.user {
        background-color: var(--primary-color);
        border-bottom-right-radius: 0.2rem;
        margin-left: 2rem;
    }
    
    .chat-message.assistant {
        background-color: var(--card-bg);
        border-bottom-left-radius: 0.2rem;
        margin-right: 2rem;
    }
    </style>
    """

def extract_text(uploaded_file, filename):
    """Extract text from PDF, DOCX, or TXT files."""
    if filename.endswith('.pdf'):
        text = ""
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
        return text
    elif filename.endswith('.docx'):
        doc = docx.Document(uploaded_file)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    elif filename.endswith('.txt'):
        return uploaded_file.getvalue().decode("utf-8")
    else:
        return ""

def format_time(seconds):
    """Format seconds as MM:SS."""
    minutes, sec = divmod(int(seconds), 60)
    return f"{minutes:02d}:{sec:02d}"

def render_sidebar():
    with st.sidebar:
        st.image("https://img.icons8.com/clouds/100/000000/brain.png", width=80)
        st.title("EduMind AI")
        
        # New Chat button
        if st.button("New Chat", key="new_chat"):
            st.session_state.chat_history = []
            st.session_state.current_chat_id = str(uuid.uuid4())
            st.session_state.all_chats[st.session_state.current_chat_id] = {
                "title": "New Chat",
                "messages": [],
                "created_at": datetime.now()
            }
            st.session_state.memory.clear()
            st.session_state.show_welcome = True
            st.experimental_rerun()
        
        # Mode selection
        st.markdown("### Mode")
        mode = st.radio(
            "Select Mode:",
            ["MCQ Generator", "Educational Chatbot"],
            key="mode_selection"
        )
        
        # Chat history section (basic implementation)
        st.markdown("### Chat History")
        if st.session_state.all_chats:
            for chat_id, chat_data in sorted(
                st.session_state.all_chats.items(), 
                key=lambda x: x[1]["created_at"], 
                reverse=True
            ):
                st.write(f"{chat_data['created_at'].strftime('%Y-%m-%d %H:%M:%S')} - {chat_data['title']}")

def generate_mcqs(content, difficulty, num_questions):
    """Generate MCQs synchronously by wrapping the async function."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(async_generate_mcqs(content, difficulty, num_questions))
    loop.close()
    
    try:
        # Extract and validate the Python list of questions
        if "```python" in result:
            code_block = result.split("```python")[1].split("```")[0]
            data = ast.literal_eval(code_block)
        else:
            data = ast.literal_eval(result)
        
        if not isinstance(data, list):
            raise ValueError("Output is not a list")
        
        # Validate question format
        validated_questions = []
        for q in data:
            if not isinstance(q, list):
                continue
                
            # Check for 4-option MCQ (list length 7) or True/False (list length 5)
            if len(q) == 7 or len(q) == 5:
                validated_questions.append(q)
        
        return validated_questions[:num_questions]
    except Exception as e:
        st.error(f"Error parsing MCQ output: {e}")
        return []

async def async_generate_mcqs(content, difficulty, num_questions):
    """Placeholder async function to simulate MCQ generation via an LLM."""
    await asyncio.sleep(1)  # Simulate processing time
    # For demonstration, return a dummy list of questions as a string.
    dummy_questions = [
        ["What is the capital of France?", "Berlin", "London", "Paris", "Rome", "C", "Paris is the capital of France."],
        ["Which planet is known as the Red Planet?", "Earth", "Mars", "Jupiter", "Saturn", "B", "Mars is known as the Red Planet."]
    ]
    # Multiply the list to ensure we have enough questions
    questions = dummy_questions * ((num_questions // len(dummy_questions)) + 1)
    return str(questions)

def render_mcq_generator():
    st.title("MCQ Generator")
    
    st.write("Create a new MCQ test by entering a topic, uploading a document, or pasting text.")
    
    method_tabs = st.tabs(["Enter Topic", "Upload Document", "Paste Text"])
    
    topic = ""
    text_content = ""
    
    with method_tabs[0]:
        topic = st.text_input(
            "Enter a topic for your MCQ test:", 
            placeholder="e.g., Python Programming, World War II, Organic Chemistry"
        )
        if topic:
            st.session_state.mcq_topic = topic
    
    with method_tabs[1]:
        uploaded_file = st.file_uploader("Upload a document:", type=["pdf", "docx", "txt"])
        if uploaded_file:
            with st.spinner("Extracting text..."):
                extracted = extract_text(uploaded_file, uploaded_file.name)
                st.session_state.file_text = extracted
                st.success(f"Successfully extracted {len(extracted)} characters.")
            
            with st.expander("Preview extracted text"):
                preview = extracted if len(extracted) < 1000 else extracted[:1000] + "..."
                st.text(preview)
    
    with method_tabs[2]:
        text_content = st.text_area(
            "Paste your text content:", 
            height=200, 
            placeholder="Paste educational content here..."
        )
        if text_content:
            st.session_state.file_text = text_content
            st.write(f"Character count: {len(text_content)}")
    
    if st.button("Generate MCQs"):
        content = st.session_state.mcq_topic if st.session_state.mcq_topic else st.session_state.file_text
        if not content:
            st.error("Please enter a topic or provide text content.")
        else:
            with st.spinner("Generating MCQs..."):
                mcqs = generate_mcqs(content, st.session_state.default_difficulty, st.session_state.default_num_questions)
                st.session_state.mcq_questions = mcqs
                st.session_state.mcq_answers = [""] * len(mcqs)
            st.success("MCQs generated successfully!")
            
            # Render each MCQ question and options using radio buttons
            for idx, mcq in enumerate(st.session_state.mcq_questions):
                st.markdown(f"### Question {idx+1}: {mcq[0]}")
                options = list(zip(["A", "B", "C", "D"], mcq[1:5]))
                selected = st.radio("Select an option:", options=[opt[0] for opt in options], key=f"q_{idx}")
                st.write(f"Selected Option: {selected}")
            
            # Placeholder button for submitting answers
            if st.button("Submit Answers"):
                st.write("Results processing would occur here.")
                # You could call create_interactive_mcq_results() and display the output

def suggest_topics(text):
    """Use LLM to suggest topics from text content."""
    system_prompt = """
    You are an educational content analyzer. Given a text, identify 5-7 key topics that would make good 
    MCQ test subjects. Return only a Python list of topic strings without any additional text.
    """
    
    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Analyze this text and suggest MCQ topics:\n\n{text[:30000]}")
        ]
        response = chat.invoke(messages)
        topics = ast.literal_eval(response.content)
        return topics[:7]  # Limit to 7 topics
    except Exception as e:
        st.error(f"Error suggesting topics: {e}")
        return ["General Knowledge"]

def create_interactive_mcq_results(mcqs, user_answers, topic, time_taken=None):
    """Generate HTML-formatted interactive MCQ results for display in Streamlit."""
    score = 0
    html_content = f"""
    <div class="card" style="padding: 1.5rem; margin-bottom: 2rem;">
        <h2 style="margin-top: 0; color: #4A56E2;">MCQ Test Results</h2>
        <p><strong>Topic:</strong> {topic}</p>
        <p><strong>Date:</strong> {datetime.now().strftime('%B %d, %Y, %H:%M')}</p>
        <p><strong>Time Taken:</strong> {time_taken if time_taken else "N/A"}</p>
    </div>
    """
    
    for i, (mcq, ans) in enumerate(zip(mcqs, user_answers)):
        correct_ans = mcq[5]
        explanation = mcq[6]
        if ans == correct_ans:
            score += 1
            result = f"<span style='color: green;'>Correct</span>"
        else:
            result = f"<span style='color: red;'>Incorrect (Correct: {correct_ans})</span>"
        html_content += f"""
        <div style="margin-bottom: 1rem;">
            <h4>Question {i+1}: {mcq[0]}</h4>
            <p>Your answer: {ans} - {result}</p>
            <p>Explanation: {explanation}</p>
        </div>
        """
        
    percentage = round((score / len(mcqs)) * 100)
    html_content += f"""
        <div class="final-score" style="margin-top: 2rem; text-align: center;">
            <h2 style="color: #E5E7EB;">Final Score: {score} / {len(mcqs)} ({percentage}%)</h2>
        </div>
    """
    
    return html_content

def create_pdf_summary(mcqs, user_answers, topic, time_taken=None):
    """Generate a PDF with MCQ test results and explanations."""
    score = 0
    pdf = FPDF()
    pdf.add_page()
    
    # Set up PDF styling
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "MCQ Test Results", ln=True, align="C")
    
    # Add metadata
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Topic: {topic}", ln=True)
    pdf.cell(0, 10, f"Date: {datetime.now().strftime('%B %d, %Y, %H:%M')}", ln=True)
    if time_taken:
        pdf.cell(0, 10, f"Time Taken: {time_taken}", ln=True)
    
    # Process each question and create formatted PDF content
    for i, (mcq, ans) in enumerate(zip(mcqs, user_answers)):
        correct_ans = mcq[5]
        explanation = mcq[6]
        if ans == correct_ans:
            score += 1
            result = "Correct"
        else:
            result = f"Incorrect (Correct: {correct_ans})"
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, f"Question {i+1}: {mcq[0]}", ln=True)
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"Your answer: {ans} - {result}", ln=True)
        pdf.multi_cell(0, 10, f"Explanation: {explanation}")
    
    percentage = round((score / len(mcqs)) * 100)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"Final Score: {score} / {len(mcqs)} ({percentage}%)", ln=True, align="C")
    
    return pdf.output(dest="S").encode("latin1")

def render_chatbot():
    st.title("Educational Chatbot")
    
    # Welcome screen for new chats
    if st.session_state.show_welcome:
        st.markdown("""
        <div class="welcome-card">
            <h1 class="welcome-title">Welcome to EduMind AI! 👋</h1>
            <p class="welcome-subtitle">I'm your educational assistant, ready to help you learn and understand any topic.</p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            <div class="feature-card">
                <h3 class="feature-title">✨ Ask Anything</h3>
                <p>Get detailed explanations on complex topics from math to literature.</p>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("### Try asking me:")
        example_questions = [
            "Explain the theory of relativity simply",
            "What are the key themes in Hamlet?",
            "How do I solve quadratic equations?"
        ]
        for q in example_questions:
            st.write(f"- {q}")
    
    # Chat input
    user_input = st.text_input("Your question:")
    if st.button("Send"):
        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            messages = [HumanMessage(content=user_input)]
            with st.spinner("Thinking..."):
                response = chat.invoke(messages)
                st.session_state.chat_history.append({"role": "assistant", "content": response.content})
    
    # Display chat messages
    for message in st.session_state.chat_history:
        if message["role"] == "user":
            st.markdown(f"""
            <div class="chat-message user">
                <div class="chat-avatar">👤</div>
                <div class="chat-content">{message["content"]}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="chat-message assistant">
                <div class="chat-avatar">🤖</div>
                <div class="chat-content">{message["content"]}</div>
            </div>
            """, unsafe_allow_html=True)

def generate_performance_chart(mcq_history):
    """Generate a performance chart based on MCQ history."""
    if not mcq_history:
        return None
    
    dates = []
    scores = []
    topics = []
    
    for test_id, test_data in mcq_history.items():
        if 'date' in test_data and 'score' in test_data and 'total' in test_data:
            dates.append(test_data['date'])
            scores.append((test_data['score'] / test_data['total']) * 100)
            topics.append(test_data['topic'])
    
    df = pd.DataFrame({
        'Date': dates,
        'Score (%)': scores,
        'Topic': topics
    })
    
    fig, ax = plt.subplots()
    ax.plot(df['Date'], df['Score (%)'], marker='o')
    ax.set_title("MCQ Performance Over Time")
    ax.set_xlabel("Date")
    ax.set_ylabel("Score (%)")
    plt.xticks(rotation=45)
    st.pyplot(fig)

def main():
    st.markdown(load_css(), unsafe_allow_html=True)
    render_sidebar()
    
    if st.session_state.get("mode_selection") == "MCQ Generator":
        render_mcq_generator()
    else:
        render_chatbot()

if __name__ == "__main__":
    main()
