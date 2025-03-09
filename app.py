import streamlit as st
import sqlite3
import openai
import os
import json
import random

# ----------------------------
# Configuration & API Key Setup
# ----------------------------
# Set your OpenAI API key as an environment variable named 'OPENAI_API_KEY'
openai.api_key = os.getenv("OPENAI_API_KEY")

# ----------------------------
# Database Initialization
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
# MCQ Generation Function
# ----------------------------
def generate_mcq(topic, difficulty):
    """
    Generates an MCQ for the given topic and difficulty.
    If an OpenAI API key is set, uses GPT-4 to generate the question.
    Otherwise, falls back to dummy questions.
    """
    # Dummy content if no API key is available
    dummy_questions = {
        "math": {
            "easy": {
                "question": "What is 2 + 2?",
                "options": ["3", "4", "5", "6"],
                "correct_answer": "4"
            },
            "medium": {
                "question": "Solve for x: 2x + 3 = 7.",
                "options": ["1", "2", "3", "4"],
                "correct_answer": "2"
            },
            "hard": {
                "question": "What is the derivative of x²?",
                "options": ["x", "2x", "x²", "2"],
                "correct_answer": "2x"
            }
        },
        "science": {
            "easy": {
                "question": "Which planet is known as the Red Planet?",
                "options": ["Earth", "Mars", "Jupiter", "Venus"],
                "correct_answer": "Mars"
            },
            "medium": {
                "question": "What is H₂O commonly known as?",
                "options": ["Hydrogen Peroxide", "Water", "Oxygen", "Helium"],
                "correct_answer": "Water"
            },
            "hard": {
                "question": "Which organelle is known as the powerhouse of the cell?",
                "options": ["Nucleus", "Mitochondria", "Ribosome", "Endoplasmic Reticulum"],
                "correct_answer": "Mitochondria"
            }
        }
    }
    topic_lower = topic.lower()
    diff_lower = difficulty.lower()
    
    if not openai.api_key:
        if topic_lower in dummy_questions and diff_lower in dummy_questions[topic_lower]:
            return dummy_questions[topic_lower][diff_lower]
        else:
            return {
                "question": "No dummy question available for this topic/difficulty.",
                "options": [],
                "correct_answer": ""
            }
    else:
        prompt = (
            f"Generate a {difficulty} level multiple-choice question on the topic '{topic}'. "
            "Provide a question, four options labeled A, B, C, D, and indicate the correct answer on a separate line in the format 'Answer: <option>'."
        )
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=200
            )
            content = response.choices[0].message.content.strip()
            # A simple parser (adjust as needed based on the output format)
            lines = content.split("\n")
            question = lines[0].strip()
            options = []
            correct_answer = ""
            for line in lines[1:]:
                if line.strip().startswith(("A.", "B.", "C.", "D.")):
                    # Remove the option label (e.g., "A.")
                    options.append(line.strip()[2:].strip())
                elif "Answer:" in line:
                    correct_answer = line.split("Answer:")[-1].strip()
            return {"question": question, "options": options, "correct_answer": correct_answer}
        except Exception as e:
            return {"question": f"Error generating MCQ: {e}", "options": [], "correct_answer": ""}

# ----------------------------
# Save User Result Function
# ----------------------------
def save_result(topic, difficulty, question, options, correct_answer, user_answer):
    result = 1 if user_answer.strip() == correct_answer.strip() else 0
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
# Retrieve Performance Analytics
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
# Initialize Database
# ----------------------------
init_db()

# ----------------------------
# Streamlit UI Setup
# ----------------------------
st.set_page_config(page_title="Personalized MCQ Generator", layout="wide")

st.title("Personalized MCQ Generator for Diagnostic Tests")
st.markdown("---")

# Sidebar: Key Concepts & Resources
st.sidebar.header("Key Concepts & Resources")
st.sidebar.markdown(
    """
**Data Collection:** Gathering data from multiple sources.  
**Data Diversity:** Sourcing different data formats (text, video, audio).  
**Knowledge Base:** A structured repository for efficient retrieval.

**Useful Tools & Links:**  
- **LangChain File Loaders:** [Learn More](https://python.langchain.com/docs/modules/indexes/file)  
- **Unstructured.io:** [Learn More](https://unstructured.io/)  
- **ScrapeGraph-AI:** Ethical web scraping for diverse data.  
- **PyPDF:** Extract text from PDFs.
    """
)

# Main: MCQ Generation
st.header("Generate Your MCQ")
with st.form(key='mcq_form'):
    topic = st.text_input("Enter Topic (e.g., Math, Science)", value="Math")
    difficulty = st.selectbox("Select Difficulty", ["Easy", "Medium", "Hard"])
    submit_button = st.form_submit_button(label='Generate MCQ')

if submit_button:
    with st.spinner("Generating your MCQ..."):
        mcq = generate_mcq(topic, difficulty)
    st.subheader("Question:")
    st.write(mcq["question"])
    if mcq["options"]:
        # Display answer options using radio buttons
        user_answer = st.radio("Select your answer:", mcq["options"])
        if st.button("Submit Answer"):
            res = save_result(topic, difficulty, mcq["question"], mcq["options"], mcq["correct_answer"], user_answer)
            if res == 1:
                st.success("Correct Answer! 🎉")
            else:
                st.error(f"Incorrect. The correct answer is: {mcq['correct_answer']}")
    else:
        st.info("No options available. Please try generating again.")

st.markdown("---")
st.header("Performance Analytics")
total, correct, accuracy = get_performance()
st.write(f"**Total Attempts:** {total}")
st.write(f"**Correct Answers:** {correct}")
st.write(f"**Accuracy:** {accuracy:.2f}%")

st.markdown("---")
st.header("Adaptive Learning Insights")
if total >= 5:
    if accuracy < 50:
        st.warning("It looks like you're facing challenges. Consider reviewing the material or trying easier questions.")
    elif accuracy >= 80:
        st.success("Great job! You might be ready for more challenging questions.")
    else:
        st.info("Keep practicing to improve your skills!")
else:
    st.info("Attempt more questions to get adaptive insights.")

st.markdown("---")
st.caption("Developed using Streamlit. Push your code to GitHub and deploy on Streamlit Cloud for production use.")
