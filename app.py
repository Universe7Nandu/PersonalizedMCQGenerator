import streamlit as st
import sqlite3
import json
import os
import asyncio
import nest_asyncio
from langchain_groq import ChatGroq

# Allow asyncio within Streamlit
nest_asyncio.apply()

# ----------------------------
# CONFIGURATION
# ----------------------------
# Set your Groq API key as an environment variable (GROQ_API_KEY)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")

# ----------------------------
# DATABASE INITIALIZATION
# ----------------------------
def init_db():
    conn = sqlite3.connect("mcq_results.db")
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT,
            difficulty TEXT,
            question TEXT,
            options TEXT,
            correct_answer TEXT,
            user_answer TEXT,
            result INTEGER
        )
        """
    )
    conn.commit()
    conn.close()

# ----------------------------
# MCQ GENERATION USING GROQ
# ----------------------------
def generate_mcq(topic, difficulty):
    """
    Generate a multiple-choice question on the given topic and difficulty
    using Groq's ChatGroq API.
    """
    prompt = (
        f"Generate a {difficulty} level multiple-choice question on the topic '{topic}'. "
        "Provide a question, four options labeled A, B, C, D, and indicate the correct answer on a separate line in the format 'Answer: <option>'."
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        llm = ChatGroq(
            temperature=0.7,
            groq_api_key=GROQ_API_KEY,
            model_name="mixtral-8x7b-32768"
        )
        response = asyncio.run(llm.ainvoke(messages))
        content = response.content.strip()
        # Parse response into question, options, and correct answer.
        lines = content.split("\n")
        question = lines[0].strip() if lines else "No question generated."
        options = []
        correct_answer = ""
        for line in lines[1:]:
            line = line.strip()
            if line.startswith(("A.", "B.", "C.", "D.")):
                options.append(line[2:].strip())
            elif "Answer:" in line:
                correct_answer = line.split("Answer:")[-1].strip()
        return {"question": question, "options": options, "correct_answer": correct_answer}
    except Exception as e:
        return {"question": f"Error generating MCQ: {e}", "options": [], "correct_answer": ""}

# ----------------------------
# SAVE USER RESULT
# ----------------------------
def save_result(topic, difficulty, question, options, correct_answer, user_answer):
    result = 1 if user_answer.strip().lower() == correct_answer.strip().lower() else 0
    conn = sqlite3.connect("mcq_results.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO results (topic, difficulty, question, options, correct_answer, user_answer, result) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (topic, difficulty, question, json.dumps(options), correct_answer, user_answer, result)
    )
    conn.commit()
    conn.close()
    return result

# ----------------------------
# PERFORMANCE ANALYTICS
# ----------------------------
def get_performance():
    conn = sqlite3.connect("mcq_results.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(result) FROM results")
    total, correct = c.fetchone()
    conn.close()
    accuracy = (correct / total) * 100 if total and total > 0 else 0
    return total, correct, accuracy

# ----------------------------
# INITIALIZATION & UI SETUP
# ----------------------------
init_db()
st.set_page_config(page_title="Personalized MCQ Generator", layout="wide", page_icon="🧠")

# Custom CSS for an attractive, modern look
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');
    body {
        font-family: 'Roboto', sans-serif;
        background: linear-gradient(135deg, #f5f7fa, #c3cfe2);
    }
    .header {
        text-align: center;
        padding: 2rem;
    }
    .title {
        font-size: 3rem;
        color: #333;
        font-weight: 700;
    }
    .subtitle {
        font-size: 1.5rem;
        color: #555;
    }
    .sidebar .sidebar-content {
        background-color: #ffffff;
        padding: 1rem;
        border-radius: 12px;
        box-shadow: 0px 4px 12px rgba(0,0,0,0.1);
    }
    .card {
        background-color: #fff;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0px 4px 12px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    .btn-submit {
        background-color: #4CAF50;
        color: white;
        border: none;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        font-size: 1rem;
        cursor: pointer;
    }
    .btn-submit:hover {
        background-color: #45a049;
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar: Project description, key concepts, and resource links
st.sidebar.markdown("<div class='sidebar-content'>", unsafe_allow_html=True)
st.sidebar.header("Project Overview")
st.sidebar.markdown("""
**Personalized MCQ Generator for Diagnostic Tests**

- **Skills Gained:** NLP, educational content generation, adaptive learning algorithms, assessment design  
- **Industry:** Education  
- **Reward:** 100

**Key Concepts:**
- **Data Collection:** Gathering relevant data from diverse sources.
- **Data Diversity:** Utilizing multiple formats (text, images, logs) for comprehensive insights.
- **Knowledge Base:** Structured repository for efficient retrieval.

**Tools & Techniques:**
- LangChain File Loaders, Web Loaders, Doc Loaders  
- Unstructured.io, ScrapeGraph-AI, PyPDF  
- Various Text Splitters (Recursive, HTML, Markdown, Code, Token, Semantic)  
- Embeddings & Vector Databases (Chroma, FAISS)  
- Prompt Engineering and Adaptive AI Engines (Groq, Llama 3)

For more details, see the [Python AI Web Scraper Tutorial](https://python.langchain.com/docs/how_to/vectorstores/).
""", unsafe_allow_html=True)
st.sidebar.markdown("</div>", unsafe_allow_html=True)

# Main header
st.markdown("<div class='header'><h1 class='title'>Personalized MCQ Generator</h1><p class='subtitle'>Adaptive diagnostics for enhanced learning outcomes</p></div>", unsafe_allow_html=True)

# MCQ Generation Section
st.markdown("<div class='card'>", unsafe_allow_html=True)
st.header("Generate Your MCQ")
with st.form(key='mcq_form'):
    topic = st.text_input("Enter Topic (e.g., Math, Science)", value="Math")
    difficulty = st.selectbox("Select Difficulty", ["Easy", "Medium", "Hard"])
    submit_button = st.form_submit_button(label='Generate MCQ', help="Click to generate a question using Groq AI")
st.markdown("</div>", unsafe_allow_html=True)

if submit_button:
    with st.spinner("Generating your MCQ..."):
        mcq = generate_mcq(topic, difficulty)
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Question:")
    st.write(mcq["question"])
    if mcq["options"]:
        user_answer = st.radio("Select your answer:", mcq["options"])
        if st.button("Submit Answer", key="submit_answer", help="Submit your answer for evaluation"):
            res = save_result(topic, difficulty, mcq["question"], mcq["options"], mcq["correct_answer"], user_answer)
            if res == 1:
                st.success("Correct Answer! 🎉")
            else:
                st.error(f"Incorrect. The correct answer is: {mcq['correct_answer']}")
    else:
        st.info("No options available. Please try generating again.")
    st.markdown("</div>", unsafe_allow_html=True)

# Performance Analytics
st.markdown("<div class='card'>", unsafe_allow_html=True)
st.header("Performance Analytics")
total, correct, accuracy = get_performance()
st.write(f"**Total Attempts:** {total}")
st.write(f"**Correct Answers:** {correct}")
st.write(f"**Accuracy:** {accuracy:.2f}%")
st.markdown("</div>", unsafe_allow_html=True)

# Adaptive Learning Insights
st.markdown("<div class='card'>", unsafe_allow_html=True)
st.header("Adaptive Learning Insights")
if total >= 5:
    if accuracy < 50:
        st.warning("It seems you're facing challenges. Consider reviewing the material or trying easier questions.")
    elif accuracy >= 80:
        st.success("Great job! You might be ready for more challenging questions.")
    else:
        st.info("Keep practicing to improve your skills!")
else:
    st.info("Attempt more questions to gain adaptive insights.")
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='text-align:center; margin-top:2rem;'><em>Developed using Groq AI on a modern Streamlit platform. Push your code to GitHub and deploy on Streamlit Cloud for production use.</em></div>", unsafe_allow_html=True)
