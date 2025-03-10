import streamlit as st
import sqlite3
import json
import os
import asyncio
import nest_asyncio
from langchain_groq import ChatGroq

###############################################################################
# ALLOW ASYNCIO IN STREAMLIT
###############################################################################
nest_asyncio.apply()

###############################################################################
# CONFIG
###############################################################################
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")

###############################################################################
# INITIALIZE DATABASE
###############################################################################
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

###############################################################################
# MCQ GENERATION (ASYNC)
###############################################################################
async def async_generate_single_mcq(topic, difficulty):
    """
    Generates a single MCQ with the Groq model.
    """
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

    llm = ChatGroq(
        temperature=0.7,
        groq_api_key=GROQ_API_KEY,
        model_name="mixtral-8x7b-32768"
    )

    messages = [{"role": "user", "content": prompt}]
    response = await llm.ainvoke(messages)
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
        return {
            "question": "No valid question generated. (Parsing error)",
            "options": [],
            "correct_answer": "",
            "explanation": ""
        }

    return {
        "question": question,
        "options": options,
        "correct_answer": correct_answer,
        "explanation": explanation
    }

def generate_multiple_mcqs(topic, difficulty, num_questions):
    """
    Runs multiple MCQ generations asynchronously.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tasks = [async_generate_single_mcq(topic, difficulty) for _ in range(num_questions)]
    mcqs = loop.run_until_complete(asyncio.gather(*tasks))
    loop.close()
    return mcqs

###############################################################################
# SAVE & ANALYTICS
###############################################################################
def save_result(topic, difficulty, question, options, correct_answer, explanation, user_answer):
    """
    Stores the user's attempt in SQLite DB. Returns 1 if correct, 0 if incorrect.
    """
    is_correct = 1 if user_answer.strip().lower() == correct_answer.strip().lower() else 0
    conn = sqlite3.connect("mcq_results.db")
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO results (topic, difficulty, question, options, correct_answer, explanation, user_answer, result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (topic, difficulty, question, json.dumps(options), correct_answer, explanation, user_answer, is_correct)
    )
    conn.commit()
    conn.close()
    return is_correct

def get_performance():
    """
    Calculates overall performance stats from the DB.
    """
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

###############################################################################
# CHATBOT
###############################################################################
def generate_chat_response(history):
    """
    Uses the Groq model to generate a chatbot response.
    """
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

###############################################################################
# STREAMLIT APP
###############################################################################
init_db()
st.set_page_config(page_title="Adaptive Educational Assessment System", layout="centered")

# -----------------------------
# Custom CSS
# -----------------------------
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
    margin: 0.25rem 0;
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

# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.markdown("### Adaptive Educational Assessment System")
st.sidebar.write("""
**Features**:
- Generate multiple MCQs (with explanations).
- Track performance & see results in a local DB.
- Chatbot for additional educational help.
""")

# -----------------------------
# Session State Initialization
# -----------------------------
if "mcqs" not in st.session_state:
    st.session_state.mcqs = []
if "current_q_idx" not in st.session_state:
    st.session_state.current_q_idx = 0
if "user_answers" not in st.session_state:
    st.session_state.user_answers = []
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "num_questions" not in st.session_state:
    st.session_state.num_questions = 0
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {"role": "system", "content": "You are a helpful educational assistant. Provide clear explanations and guidance on educational topics."}
    ]

# -----------------------------
# Create Tabs
# -----------------------------
tabs = st.tabs(["MCQ Generator", "Chatbot"])

# ============================================================================
# TAB 1: MCQ GENERATOR
# ============================================================================
with tabs[0]:
    st.title("MCQ Generator 🌟")

    # --- MCQ Generation Form ---
    with st.form("generate_mcq_form", clear_on_submit=False):
        topic = st.text_input("Enter Topic (e.g., Math, Science, History)", key="topic_input")
        difficulty = st.selectbox("Select Difficulty", ["Easy", "Medium", "Hard"], key="difficulty_select")
        num_questions = st.number_input(
            "How many MCQs would you like to generate?",
            min_value=1, max_value=50, value=5, step=1,
            key="num_q_input"
        )
        generate_button = st.form_submit_button("Generate MCQs")

    if generate_button:
        # Clear old data
        st.session_state.mcqs = generate_multiple_mcqs(topic, difficulty, num_questions)
        st.session_state.current_q_idx = 0
        st.session_state.user_answers = [None] * num_questions
        st.session_state.submitted = False
        st.session_state.num_questions = num_questions
        st.success(f"Generated {num_questions} MCQ(s) for topic '{topic}' at {difficulty} difficulty!")

    # If MCQs exist, display the current question
    if st.session_state.mcqs:
        idx = st.session_state.current_q_idx
        total_q = st.session_state.num_questions

        if idx < total_q:
            mcq = st.session_state.mcqs[idx]

            st.subheader(f"Question {idx+1} of {total_q}")
            st.write(mcq["question"])

            # --- Question Form ---
            with st.form(f"question_form_{idx}", clear_on_submit=False):
                # If the user has not chosen an answer yet, default to None
                if st.session_state.user_answers[idx] is None:
                    st.session_state.user_answers[idx] = ""

                # Radio to select answer
                user_answer = st.radio(
                    "Select your answer:",
                    mcq["options"],
                    index=0 if st.session_state.user_answers[idx] == "" else mcq["options"].index(st.session_state.user_answers[idx]),
                    key=f"user_answer_radio_{idx}"
                )

                submit_answer_btn = st.form_submit_button("Submit Answer")

            # If the user submitted the answer
            if submit_answer_btn:
                # Save user answer in session
                st.session_state.user_answers[idx] = user_answer
                # Save to DB
                correct = save_result(
                    topic,
                    difficulty,
                    mcq["question"],
                    mcq["options"],
                    mcq["correct_answer"],
                    mcq["explanation"],
                    user_answer
                )
                # Show feedback
                if correct == 1:
                    st.success("Correct Answer! 🎉")
                else:
                    st.error(f"Incorrect. The correct answer is: {mcq['correct_answer']}")
                st.info(f"Explanation: {mcq['explanation']}")
                st.session_state.submitted = True

            # If user has submitted, show next button
            if st.session_state.submitted:
                if idx < total_q - 1:
                    if st.button("Next Question"):
                        st.session_state.current_q_idx += 1
                        st.session_state.submitted = False
                else:
                    st.write("You have reached the end of the MCQ set!")

    # Show performance stats
    st.subheader("Performance Analytics")
    total, correct, accuracy = get_performance()
    st.write(f"**Total Attempts:** {total}")
    st.write(f"**Correct Answers:** {correct if correct else 0}")
    st.write(f"**Accuracy:** {accuracy:.2f}%")

    # Adaptive suggestions
    if total >= 5:
        if accuracy < 50:
            st.info("Consider reviewing the material or trying easier questions.")
        elif accuracy >= 80:
            st.success("Excellent! Try harder questions for more challenge.")
        else:
            st.info("Keep practicing to improve your skills!")

# ============================================================================
# TAB 2: CHATBOT
# ============================================================================
with tabs[1]:
    st.title("Educational Assistant Chatbot 🤖")
    st.write("Ask any questions or seek further clarification on educational topics.")

    with st.form("chat_form"):
        user_input = st.text_input("Your message:", key="chat_input")
        send_button = st.form_submit_button("Send")

    if send_button and user_input.strip():
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.spinner("Assistant is typing..."):
            response = generate_chat_response(st.session_state.chat_history)
        st.session_state.chat_history.append({"role": "assistant", "content": response})

    st.markdown("---")
    st.subheader("Conversation:")
    for msg in st.session_state.chat_history:
        if msg["role"] == "assistant":
            st.markdown(
                f"<div class='chat-container chat-assistant'><strong>Assistant:</strong> {msg['content']}</div>",
                unsafe_allow_html=True
            )
        elif msg["role"] == "user":
            st.markdown(
                f"<div class='chat-container chat-user'><strong>You:</strong> {msg['content']}</div>",
                unsafe_allow_html=True
            )
