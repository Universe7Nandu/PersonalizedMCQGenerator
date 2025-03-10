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
