import streamlit as st
import sqlite3
import json
import os
import asyncio
import nest_asyncio
from langchain_groq import ChatGroq

# -------------------------------------------------------------------
# Allow asyncio to run in Streamlit
nest_asyncio.apply()

# -------------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")

# -------------------------------------------------------------------
# DATABASE INIT
# -------------------------------------------------------------------
def init_db():
    """
    Create or connect to an SQLite database to store MCQ results.
    """
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

# -------------------------------------------------------------------
# MCQ GENERATION (GROQ)
# -------------------------------------------------------------------
async def async_generate_single_mcq(topic, difficulty):
    """
    Generate a single MCQ with the Groq model, returning:
      - question
      - options
      - correct_answer
      - explanation
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

    # If parsing fails or we don't have a valid MCQ
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
    Generate multiple MCQs asynchronously, store them in a list, and return.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tasks = [async_generate_single_mcq(topic, difficulty) for _ in range(num_questions)]
    mcqs = loop.run_until_complete(asyncio.gather(*tasks))
    loop.close()
    return mcqs

# -------------------------------------------------------------------
# SAVE & ANALYTICS
# -------------------------------------------------------------------
def save_result(topic, difficulty, question, options, correct_answer, explanation, user_answer):
    """
    Save the user's result (correct or incorrect) to the SQLite database.
    Returns 1 if correct, 0 otherwise.
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
    Retrieve overall performance from the database.
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

# -------------------------------------------------------------------
# CHATBOT FUNCTIONALITY (GROQ)
# -------------------------------------------------------------------
def generate_chat_response(history):
    """
    Use the same Groq model to generate chatbot responses.
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

# -------------------------------------------------------------------
# APP UI
# -------------------------------------------------------------------
init_db()
st.set_page_config(page_title="Adaptive Educational Assessment System", layout="centered")

# Custom CSS
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

# Sidebar
st.sidebar.markdown("### Adaptive Educational Assessment System")
st.sidebar.write("""
**Features**:
- Generate multiple MCQs with a single click
- Track performance & see detailed explanations
- Chatbot for interactive educational help
- Professional UI with custom CSS
""")

# Initialize session state for MCQs
if "mcqs" not in st.session_state:
    st.session_state.mcqs = []
if "current_question_index" not in st.session_state:
    st.session_state.current_question_index = 0
if "user_answers" not in st.session_state:
    st.session_state.user_answers = []
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "num_questions" not in st.session_state:
    st.session_state.num_questions = 0

tabs = st.tabs(["MCQ Generator", "Chatbot"])

# -------------------------------------------------------------------
# TAB 1: MCQ Generator
# -------------------------------------------------------------------
with tabs[0]:
    st.title("MCQ Generator 🌟")

    # Input fields for MCQ generation
    topic = st.text_input("Enter Topic (e.g., Math, Science, History)", key="topic_input")
    difficulty = st.selectbox("Select Difficulty", ["Easy", "Medium", "Hard"], key="difficulty_select")
    num_questions = st.number_input("How many MCQs would you like to generate?", min_value=1, max_value=50, value=5, step=1, key="num_q_input")

    if st.button("Generate MCQs"):
        # Reset session state to start fresh
        st.session_state.mcqs = generate_multiple_mcqs(topic, difficulty, num_questions)
        st.session_state.current_question_index = 0
        st.session_state.user_answers = [None] * num_questions
        st.session_state.submitted = False
        st.session_state.num_questions = num_questions
        st.success(f"Generated {num_questions} MCQ(s) for topic '{topic}' at {difficulty} difficulty!")

    # If MCQs exist, show the current question
    if st.session_state.mcqs:
        idx = st.session_state.current_question_index
        total_q = st.session_state.num_questions
        if idx < total_q:
            mcq = st.session_state.mcqs[idx]
            
            st.subheader(f"Question {idx+1} of {total_q}")
            st.write(mcq["question"])

            # Display options
            if mcq["options"]:
                # If user hasn't answered this question, we create a radio
                if st.session_state.user_answers[idx] is None:
                    st.session_state.user_answers[idx] = st.radio(
                        "Select your answer:",
                        mcq["options"],
                        key=f"user_answer_radio_{idx}"
                    )
                else:
                    # If user has already selected an answer, we show that as pre-selected
                    st.radio(
                        "Select your answer:",
                        mcq["options"],
                        index=mcq["options"].index(st.session_state.user_answers[idx]),
                        key=f"user_answer_radio_{idx}",
                        disabled=True
                    )

                # Submit button
                if not st.session_state.submitted:
                    if st.button("Submit Answer"):
                        user_answer = st.session_state.user_answers[idx]
                        correct = save_result(
                            topic,
                            difficulty,
                            mcq["question"],
                            mcq["options"],
                            mcq["correct_answer"],
                            mcq["explanation"],
                            user_answer
                        )
                        st.session_state.submitted = True
                        if correct == 1:
                            st.success("Correct Answer! 🎉")
                        else:
                            st.error(f"Incorrect. The correct answer is: {mcq['correct_answer']}")
                        st.info(f"Explanation: {mcq['explanation']}")
                else:
                    # Already submitted => show correctness + explanation
                    user_answer = st.session_state.user_answers[idx]
                    if user_answer.strip().lower() == mcq["correct_answer"].strip().lower():
                        st.success("Correct Answer! 🎉")
                    else:
                        st.error(f"Incorrect. The correct answer is: {mcq['correct_answer']}")
                    st.info(f"Explanation: {mcq['explanation']}")

                # Next question button
                if st.session_state.submitted:
                    if idx < total_q - 1:
                        if st.button("Next Question"):
                            st.session_state.current_question_index += 1
                            st.session_state.submitted = False
                    else:
                        st.write("You have reached the end of the MCQ set!")
            else:
                st.warning("No options available. Try generating again or check your API key.")

    # Performance & Adaptive Feedback
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

# -------------------------------------------------------------------
# TAB 2: Chatbot
# -------------------------------------------------------------------
with tabs[1]:
    st.title("Educational Assistant Chatbot 🤖")
    st.write("Ask any questions or seek further clarification on educational topics.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "system", "content": "You are a helpful educational assistant. Provide clear explanations and guidance on educational topics."}
        ]

    user_input = st.text_input("Your message:", key="chat_input")
    if st.button("Send", key="chat_send"):
        if user_input.strip():
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.spinner("Assistant is typing..."):
                response = generate_chat_response(st.session_state.chat_history)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.experimental_rerun()

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
