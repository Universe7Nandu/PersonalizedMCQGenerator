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
# CONFIGURATION
# ============================
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")

# ============================
# DATABASE INIT
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
            explanation TEXT,
            user_answer TEXT,
            result INTEGER
        )
        """
    )
    conn.commit()
    conn.close()

# ============================
# MCQ GENERATION (GROQ)
# ============================
def generate_mcq(topic, difficulty):
    prompt = (
        f"You are a helpful AI specialized in generating educational multiple-choice questions with detailed explanations.\n\n"
        f"TOPIC: {topic}\n"
        f"DIFFICULTY: {difficulty}\n\n"
        "INSTRUCTIONS:\n"
        "1. Provide a single question.\n"
        "2. Provide four options, labeled A, B, C, and D.\n"
        "3. Indicate the correct answer on a separate line, e.g. 'Answer: B'\n"
        "4. Provide a detailed explanation for the correct answer on a new line, e.g. 'Explanation: ...'\n"
        "5. Output ONLY in this format:\n\n"
        "Question: <question text>\n"
        "A. <option A>\n"
        "B. <option B>\n"
        "C. <option C>\n"
        "D. <option D>\n"
        "Answer: <letter>\n"
        "Explanation: <detailed explanation>\n"
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

        lines = content.split("\n")
        question = ""
        options = []
        correct_answer = ""
        explanation = ""

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
            elif line.startswith("Explanation:"):
                explanation = line.replace("Explanation:", "").strip()

        if not question or len(options) != 4 or not correct_answer or not explanation:
            return {"question": "No valid question generated. (Parsing error)", "options": [], "correct_answer": "", "explanation": ""}
        
        return {
            "question": question,
            "options": options,
            "correct_answer": correct_answer,
            "explanation": explanation
        }

    except Exception as e:
        return {
            "question": f"Error generating MCQ: {str(e)}",
            "options": [],
            "correct_answer": "",
            "explanation": ""
        }

# ============================
# SAVE & ANALYTICS
# ============================
def save_result(topic, difficulty, question, options, correct_answer, explanation, user_answer):
    result = 1 if user_answer.strip().lower() == correct_answer.strip().lower() else 0
    conn = sqlite3.connect("mcq_results.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO results (topic, difficulty, question, options, correct_answer, explanation, user_answer, result) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (topic, difficulty, question, json.dumps(options), correct_answer, explanation, user_answer, result)
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
# CHATBOT FUNCTIONALITY (GROQ)
# ============================
def generate_chat_response(history):
    try:
        llm = ChatGroq(
            temperature=0.7,
            groq_api_key=GROQ_API_KEY,
            model_name="mixtral-8x7b-32768"
        )
        response = asyncio.run(llm.ainvoke(history))
        return response.content.strip()
    except Exception as e:
        return f"Error generating response: {e}"

# ============================
# APP UI
# ============================
init_db()
st.set_page_config(page_title="Adaptive Educational Assessment System", layout="centered")

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
.chat-container {
    background-color: #ffffff;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 1rem;
}
.chat-user {
    text-align: right;
    color: #007bff;
}
.chat-assistant {
    text-align: left;
    color: #28a745;
}
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown("### Adaptive Educational Assessment System")
st.sidebar.write("""
**Features**:
- Generate contextually relevant MCQs with adaptive difficulty.
- Detailed explanations for each question.
- Chatbot for interactive educational assistance.
- Performance analytics to track improvement.
""")

tabs = st.tabs(["MCQ Generator", "Chatbot"])

# -----------------------------
# MCQ Generator Tab
# -----------------------------
with tabs[0]:
    st.title("MCQ Generator 🌟")
    st.write("Generate multiple-choice questions tailored to your chosen topic and difficulty.")
    
    topic = st.text_input("Enter Topic (e.g., Math, Science)")
    difficulty = st.selectbox("Select Difficulty", ["Easy", "Medium", "Hard"])
    
    if st.button("Generate MCQ"):
        with st.spinner("Generating question..."):
            mcq = generate_mcq(topic, difficulty)
        
        st.subheader("Question:")
        st.write(mcq["question"])
        
        if mcq["options"]:
            user_answer = st.radio("Select your answer:", mcq["options"], key="user_answer_radio")
            if st.button("Submit Answer"):
                res = save_result(topic, difficulty, mcq["question"], mcq["options"], mcq["correct_answer"], mcq["explanation"], user_answer)
                if res == 1:
                    st.success("Correct Answer! 🎉")
                else:
                    st.error(f"Incorrect. The correct answer is: {mcq['correct_answer']}")
                st.info(f"Explanation: {mcq['explanation']}")
        else:
            st.warning("No options available. Try generating again or check your API key.")
    
    st.subheader("Performance Analytics")
    total, correct, accuracy = get_performance()
    st.write(f"**Total Attempts:** {total}")
    st.write(f"**Correct Answers:** {correct}")
    st.write(f"**Accuracy:** {accuracy:.2f}%")
    
    if total >= 5:
        if accuracy < 50:
            st.info("Consider reviewing the material or trying easier questions.")
        elif accuracy >= 80:
            st.success("Excellent! Try harder questions for more challenge.")
        else:
            st.info("Keep practicing to improve your skills!")

# -----------------------------
# Chatbot Tab
# -----------------------------
with tabs[1]:
    st.title("Educational Assistant Chatbot 🤖")
    st.write("Ask any questions or seek further clarification on educational topics.")
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "system", "content": "You are a helpful educational assistant. Provide clear explanations and guidance on educational topics."}
        ]
    
    chat_input = st.text_input("Your message:", key="chat_input")
    if st.button("Send"):
        if chat_input:
            st.session_state.chat_history.append({"role": "user", "content": chat_input})
            with st.spinner("Assistant is typing..."):
                response = generate_chat_response(st.session_state.chat_history)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.experimental_rerun()  # Refresh to display updated conversation
    
    st.markdown("---")
    st.subheader("Conversation:")
    for msg in st.session_state.chat_history:
        if msg["role"] == "assistant":
            st.markdown(f"<div class='chat-container chat-assistant'><strong>Assistant:</strong> {msg['content']}</div>", unsafe_allow_html=True)
        elif msg["role"] == "user":
            st.markdown(f"<div class='chat-container chat-user'><strong>You:</strong> {msg['content']}</div>", unsafe_allow_html=True)
