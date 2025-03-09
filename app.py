import streamlit as st
import sqlite3
import json
import os
import asyncio
import nest_asyncio
from langchain_groq import ChatGroq

# Allow asyncio to run in Streamlit
nest_asyncio.apply()

# ============================
#  CONFIGURATION
# ============================
# Make sure to set your GROQ_API_KEY as an environment variable
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")

# ============================
#  DATABASE INIT
# ============================
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

# ============================
#  MCQ GENERATION (GROQ)
# ============================
def generate_mcq(topic, difficulty):
    """
    Generate a multiple-choice question with four options (A-D) using Groq's ChatGroq.
    The prompt enforces a specific format for consistent parsing.
    """
    prompt = (
        f"You are a helpful AI specialized in generating educational multiple-choice questions.\n\n"
        f"TOPIC: {topic}\n"
        f"DIFFICULTY: {difficulty}\n\n"
        "INSTRUCTIONS:\n"
        "1. Provide a single question.\n"
        "2. Provide four options, labeled A, B, C, and D.\n"
        "3. Indicate the correct answer on a separate line, e.g. 'Answer: B'\n"
        "4. Output ONLY in this format:\n\n"
        "Question: <question text>\n"
        "A. <option A>\n"
        "B. <option B>\n"
        "C. <option C>\n"
        "D. <option D>\n"
        "Answer: <letter>\n"
        "Please do not include any other commentary.\n"
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

        # Parse the response
        lines = content.split("\n")
        question = ""
        options = []
        correct_answer = ""

        for line in lines:
            if line.startswith("Question:"):
                question = line.replace("Question:", "").strip()
            elif line.startswith("A."):
                options.append(line[2:].strip())
            elif line.startswith("B."):
                options.append(line[2:].strip())
            elif line.startswith("C."):
                options.append(line[2:].strip())
            elif line.startswith("D."):
                options.append(line[2:].strip())
            elif line.startswith("Answer:"):
                correct_answer = line.replace("Answer:", "").strip()

        # If parsing fails or we don't have 4 options, fallback
        if not question or len(options) != 4 or not correct_answer:
            return {"question": "No valid question generated. (Parsing error)", "options": [], "correct_answer": ""}

        return {
            "question": question,
            "options": options,
            "correct_answer": correct_answer
        }

    except Exception as e:
        return {
            "question": f"Error generating MCQ: {str(e)}",
            "options": [],
            "correct_answer": ""
        }

# ============================
#  SAVE & ANALYTICS
# ============================
def save_result(topic, difficulty, question, options, correct_answer, user_answer):
    result = 1 if user_answer.strip().lower() == correct_answer.strip().lower() else 0
    conn = sqlite3.connect("mcq_results.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO results (topic, difficulty, question, options, correct_answer, user_answer, result) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (topic, difficulty, question, json.dumps(options), correct_answer, user_answer, result)
    )
    conn.commit()
    conn.close()
    return result

def get_performance():
    conn = sqlite3.connect("mcq_results.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(result) FROM results")
    total, correct = c.fetchone()
    conn.close()
    if total and total > 0:
        accuracy = (correct / total) * 100
    else:
        accuracy = 0
    return total, correct, accuracy

# ============================
#  APP UI
# ============================
init_db()
st.set_page_config(page_title="MCQ Generator", layout="centered")

# Custom CSS for a simpler, colorful look
st.markdown("""
<style>
html, body {
    background: linear-gradient(to right, #74ABE2, #5563DE);
    font-family: 'Segoe UI', sans-serif;
}
h1, h2, h3, label {
    color: #ffffff !important;
}
.block-container {
    background-color: rgba(255, 255, 255, 0.9);
    border-radius: 12px;
    padding: 2rem;
}
.sidebar .sidebar-content {
    background-color: #fefefe;
    border-radius: 8px;
    padding: 1rem;
}
.stButton>button {
    background-color: #ff5c5c;
    color: #fff;
    border-radius: 8px;
    border: none;
    font-size: 1rem;
    padding: 0.5rem 1rem;
}
.stButton>button:hover {
    background-color: #ff3c3c;
}
</style>
""", unsafe_allow_html=True)

# Sidebar info
st.sidebar.markdown("### Project: Personalized MCQ Generator")
st.sidebar.write(
    """
    **How to Use**:
    1. Enter a Topic (e.g., Math, Biology).
    2. Select a Difficulty.
    3. Click "Generate MCQ."
    4. Choose your answer & Submit.
    """
)
st.sidebar.write(
    """
    **Key Tools**:
    - Groq AI (langchain_groq)
    - SQLite for storing results
    - Streamlit for UI
    """
)

st.title("Adaptive MCQ Generator 🌟")
st.write("Generate multiple-choice questions tailored to your chosen topic and difficulty. Answer them to track your performance!")

# Form for question generation
topic = st.text_input("Enter Topic (e.g., Math, Science)")
difficulty = st.selectbox("Select Difficulty", ["Easy", "Medium", "Hard"])

if st.button("Generate MCQ"):
    with st.spinner("Thinking..."):
        mcq = generate_mcq(topic, difficulty)

    st.subheader("Question:")
    st.write(mcq["question"])

    if mcq["options"]:
        user_answer = st.radio("Select your answer:", mcq["options"], key="user_answer_radio")
        if st.button("Submit Answer"):
            res = save_result(
                topic,
                difficulty,
                mcq["question"],
                mcq["options"],
                mcq["correct_answer"],
                user_answer
            )
            if res == 1:
                st.success("Correct Answer! 🎉")
            else:
                st.error(f"Incorrect. The correct answer is: {mcq['correct_answer']}")
    else:
        st.warning("No options available. Try generating again or check your API key.")

# Performance
st.subheader("Performance Analytics")
total, correct, accuracy = get_performance()
st.write(f"**Total Attempts:** {total}")
st.write(f"**Correct Answers:** {correct}")
st.write(f"**Accuracy:** {accuracy:.2f}%")

# Adaptive feedback
if total >= 5:
    if accuracy < 50:
        st.info("Consider reviewing the material or trying easier questions.")
    elif accuracy >= 80:
        st.success("Excellent! Try harder questions for more challenge.")
    else:
        st.info("Keep practicing to improve your skills!")
