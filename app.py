import streamlit as st
import sqlite3
import json
import os
import asyncio
import nest_asyncio
from pypdf import PdfReader
import chromadb
from chromadb.config import Settings
from langchain_groq import ChatGroq
from langchain.embeddings import HuggingFaceEmbeddings
from sentence_transformers import SentenceTransformer

# ----------------------------------------------------------------------
# Allow asyncio in Streamlit
nest_asyncio.apply()

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")

# Initialize local Chroma in-memory DB (for demonstration)
# In production, you might use a persistent store
CHROMA_SETTINGS = Settings(chroma_db_impl="duckdb+parquet", persist_directory=None)
chroma_client = chromadb.Client(CHROMA_SETTINGS)

# Create a collection to store document chunks
# If you re-run the app, it may re-initialize each time
collection_name = "uploaded_docs"
try:
    collection = chroma_client.get_collection(collection_name)
except:
    collection = chroma_client.create_collection(collection_name)

# Embeddings (using SentenceTransformers model)
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
embedding_fn = lambda texts: embedding_model.encode(texts).tolist()

# ----------------------------------------------------------------------
# SQLITE DATABASE INIT
# ----------------------------------------------------------------------
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

# ----------------------------------------------------------------------
# UTILS: PDF/TXT PARSING & CHUNKING
# ----------------------------------------------------------------------
def parse_pdf(file) -> str:
    """
    Extract text from a PDF file using pypdf.
    """
    pdf = PdfReader(file)
    all_text = []
    for page in pdf.pages:
        all_text.append(page.extract_text() or "")
    return "\n".join(all_text)

def parse_txt(file) -> str:
    """
    Extract text from a TXT file.
    """
    return file.read().decode("utf-8", errors="ignore")

def chunk_text(text, chunk_size=800, overlap=100):
    """
    Split text into overlapping chunks of `chunk_size` with `overlap`.
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = words[start:end]
        chunks.append(" ".join(chunk))
        start += (chunk_size - overlap)
    return chunks

# ----------------------------------------------------------------------
# STORE CHUNKS IN VECTOR DB
# ----------------------------------------------------------------------
def store_document_in_vector_db(doc_name, text):
    """
    Chunk the text, embed, and store in the Chroma vector DB.
    Each chunk is stored as a separate document with metadata.
    """
    # Clear old data in the collection for this doc name
    # to avoid duplication each time you upload
    try:
        collection.delete(where={"doc_name": doc_name})
    except:
        pass

    chunks = chunk_text(text, chunk_size=800, overlap=100)
    embeddings = embedding_fn(chunks)

    # Add to Chroma
    ids = [f"{doc_name}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"doc_name": doc_name} for _ in range(len(chunks))]
    collection.add(documents=chunks, embeddings=embeddings, ids=ids, metadatas=metadatas)

# ----------------------------------------------------------------------
# RETRIEVAL FOR CHATBOT
# ----------------------------------------------------------------------
def retrieve_relevant_chunks(query, top_k=3):
    """
    Given a user query, embed it, and retrieve top_k chunks from Chroma.
    """
    query_embedding = embedding_fn([query])[0]
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
    retrieved_docs = results["documents"][0]
    # Combine them into a single context
    return "\n".join(retrieved_docs)

# ----------------------------------------------------------------------
# MCQ GENERATION
# ----------------------------------------------------------------------
async def async_generate_mcqs_from_text(doc_text, subject, difficulty, num_questions):
    """
    Generate MCQs from the provided doc_text using the Groq model.
    We'll request a set of MCQs in a single call.
    """
    # Because doc_text can be large, keep in mind token limits.
    # For demonstration, we pass it directly. If doc is huge, consider summarizing or partial retrieval.
    prompt = f"""
You are a helpful AI that creates multiple-choice questions from a given text.

Subject: {subject}
Difficulty: {difficulty}
Number of Questions: {num_questions}

Text to use for question generation:

INSTRUCTIONS:
1. Generate exactly {num_questions} multiple-choice questions covering the main ideas of the text.
2. Each question should have four options: A, B, C, D.
3. Label the correct answer with a line like "Answer: X" where X is one of A, B, C, D.
4. Provide a short explanation after each answer, e.g. "Explanation: ..."

OUTPUT FORMAT:
Question 1: <question text>
A. <option A>
B. <option B>
C. <option C>
D. <option D>
Answer: <letter>
Explanation: <explanation>

Question 2: ...
...
Please output ONLY the questions in the specified format. No extra commentary.
"""
    llm = ChatGroq(
        temperature=0.7,
        groq_api_key=GROQ_API_KEY,
        model_name="mixtral-8x7b-32768"
    )
    messages = [{"role": "user", "content": prompt}]
    response = await llm.ainvoke(messages)
    return response.content.strip()

def parse_mcq_response(mcq_response):
    lines = mcq_response.splitlines()
    questions_data = []
    current_q = {}
    for line in lines:
        line = line.strip()
        if line.lower().startswith("question "):
            if current_q:
                questions_data.append(current_q)
            current_q = {"question": "", "options": [], "correct_answer": "", "explanation": ""}
            parts = line.split(":", 1)
            if len(parts) == 2:
                current_q["question"] = parts[1].strip()
        elif line.startswith("A.") or line.startswith("B.") or line.startswith("C.") or line.startswith("D."):
            current_q["options"].append(line[2:].strip())
        elif line.lower().startswith("answer:"):
            current_q["correct_answer"] = line.split(":", 1)[1].strip()
        elif line.lower().startswith("explanation:"):
            current_q["explanation"] = line.split(":", 1)[1].strip()
    if current_q:
        questions_data.append(current_q)
    valid_mcqs = [q for q in questions_data if q.get("question") and len(q.get("options", [])) == 4]
    return valid_mcqs

# ----------------------------------------------------------------------
# SAVE RESULTS & PERFORMANCE TRACKING
# ----------------------------------------------------------------------
def save_result(topic, difficulty, question, options, correct_answer, explanation, user_answer):
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

# ----------------------------------------------------------------------
# CHATBOT WITH CONTEXTUAL RETRIEVAL
# ----------------------------------------------------------------------
def generate_chat_response(user_query, chat_history):
    context = retrieve_relevant_chunks(user_query, top_k=3)
    prompt = f"""
You are a helpful educational assistant. You have the following context from an uploaded document:

{context}

Answer the user's question in a clear and concise manner. If the context doesn't provide enough information, say so.

User's question: {user_query}
"""
    llm = ChatGroq(
        temperature=0.7,
        groq_api_key=GROQ_API_KEY,
        model_name="mixtral-8x7b-32768"
    )
    messages = [
        {"role": "system", "content": "You are a helpful educational assistant."},
        {"role": "user", "content": prompt}
    ]
    try:
        response = asyncio.run(llm.ainvoke(messages))
        return response.content.strip()
    except Exception as e:
        return f"Error generating response: {e}"

# ----------------------------------------------------------------------
# MAIN STREAMLIT APP
# ----------------------------------------------------------------------
init_db()
st.set_page_config(page_title="Adaptive Educational Assessment System", layout="centered")

# Custom CSS for styling
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

# Session State Initialization
if "uploaded_text" not in st.session_state:
    st.session_state.uploaded_text = ""
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
if "subject" not in st.session_state:
    st.session_state.subject = ""
if "difficulty" not in st.session_state:
    st.session_state.difficulty = "Easy"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Create Tabs for different functionalities
tabs = st.tabs(["Document Upload & MCQ", "Chatbot"])

# ============================================================================
# TAB 1: Document Upload & MCQ Generation
# ============================================================================
with tabs[0]:
    st.title("Upload Document & Generate MCQs")
    st.write("Upload a **PDF** or **TXT** file. The text will be extracted and used to generate MCQs.")
    uploaded_file = st.file_uploader("Choose a file (PDF or TXT)", type=["pdf", "txt"])

    if uploaded_file is not None:
        if uploaded_file.name.lower().endswith(".pdf"):
            text_data = parse_pdf(uploaded_file)
        else:
            text_data = parse_txt(uploaded_file)
        st.session_state.uploaded_text = text_data
        store_document_in_vector_db(uploaded_file.name, text_data)
        st.success(f"Uploaded and processed: {uploaded_file.name}")

    if st.session_state.uploaded_text:
        with st.form("mcq_form"):
            st.session_state.subject = st.text_input("Subject (e.g. Biology, History, etc.)", value=st.session_state.subject)
            st.session_state.difficulty = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"], index=0)
            st.session_state.num_questions = st.number_input("Number of MCQs to generate", min_value=1, max_value=20, value=5)
            generate_btn = st.form_submit_button("Generate MCQs")
        
        if generate_btn:
            with st.spinner("Generating MCQs..."):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result_str = loop.run_until_complete(
                    async_generate_mcqs_from_text(
                        st.session_state.uploaded_text,
                        st.session_state.subject,
                        st.session_state.difficulty,
                        st.session_state.num_questions
                    )
                )
                loop.close()
            mcqs = parse_mcq_response(result_str)
            st.session_state.mcqs = mcqs
            st.session_state.current_q_idx = 0
            st.session_state.user_answers = [None] * len(mcqs)
            st.session_state.submitted = False
            if mcqs:
                st.success(f"Generated {len(mcqs)} MCQ(s). Scroll down to attempt them!")
            else:
                st.warning("No valid MCQs were generated. Check the document content and prompt.")

    if st.session_state.mcqs:
        idx = st.session_state.current_q_idx
        total_q = len(st.session_state.mcqs)
        if idx < total_q:
            mcq = st.session_state.mcqs[idx]
            st.subheader(f"Question {idx+1} of {total_q}")
            st.write(mcq["question"])
            if st.session_state.user_answers[idx] is None:
                st.session_state.user_answers[idx] = ""
            with st.form(f"question_form_{idx}"):
                user_answer = st.radio(
                    "Select your answer:",
                    mcq["options"],
                    index=0 if st.session_state.user_answers[idx] == "" else mcq["options"].index(st.session_state.user_answers[idx]),
                    key=f"user_answer_radio_{idx}"
                )
                submit_q_btn = st.form_submit_button("Submit Answer")
            if submit_q_btn:
                st.session_state.user_answers[idx] = user_answer
                correct_flag = save_result(
                    st.session_state.subject,
                    st.session_state.difficulty,
                    mcq["question"],
                    mcq["options"],
                    mcq["correct_answer"],
                    mcq["explanation"],
                    user_answer
                )
                if correct_flag == 1:
                    st.success("Correct Answer! 🎉")
                else:
                    st.error(f"Incorrect. The correct answer is: {mcq['correct_answer']}")
                st.info(f"Explanation: {mcq['explanation']}")
                st.session_state.submitted = True
            if st.session_state.submitted:
                if idx < total_q - 1:
                    if st.button("Next Question"):
                        st.session_state.current_q_idx += 1
                        st.session_state.submitted = False
                else:
                    st.write("You have reached the end of the MCQ set!")
    
    st.subheader("Performance Analytics")
    total_attempts, correct_count, accuracy = get_performance()
    st.write(f"**Total Attempts:** {total_attempts}")
    st.write(f"**Correct Answers:** {correct_count if correct_count else 0}")
    st.write(f"**Accuracy:** {accuracy:.2f}%")
    if total_attempts >= 5:
        if accuracy < 50:
            st.info("Consider reviewing the material or trying easier questions.")
        elif accuracy >= 80:
            st.success("Excellent! Try harder questions for more challenge.")
        else:
            st.info("Keep practicing to improve your skills!")

# ============================================================================
# TAB 2: Chatbot
# ============================================================================
with tabs[1]:
    st.title("Educational Assistant Chatbot")
    st.write("Ask questions related to your uploaded document. The chatbot uses the stored document context for better answers.")
    with st.form("chat_form"):
        user_input = st.text_input("Your question:")
        send_button = st.form_submit_button("Send")
    if send_button and user_input.strip():
        st.session_state.chat_history.append(("user", user_input))
        with st.spinner("Assistant is thinking..."):
            response = generate_chat_response(user_input, st.session_state.chat_history)
        st.session_state.chat_history.append(("assistant", response))
    st.markdown("---")
    st.subheader("Conversation:")
    for role, content in st.session_state.chat_history:
        if role == "assistant":
            st.markdown(f"<div class='chat-container chat-assistant'><strong>Assistant:</strong> {content}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-container chat-user'><strong>You:</strong> {content}</div>", unsafe_allow_html=True)

