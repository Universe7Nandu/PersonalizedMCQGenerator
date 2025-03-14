import streamlit as st
import ast
from langchain_groq import ChatGroq
from langchain.schema import HumanMessage, SystemMessage
from langchain.memory import ConversationBufferMemory

# =============================================================================
# Session State Initialization for Both Modes
# =============================================================================
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# Common variables for Educational Chatbot
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# =============================================================================
# Session State Initialization for MCQ Generator
# =============================================================================
if "topic" not in st.session_state:
    st.session_state.topic = ""
if "generate_button" not in st.session_state:
    st.session_state.generate_button = False
if "once" not in st.session_state:
    st.session_state.once = True
if "questions" not in st.session_state:
    st.session_state.questions = []
if "total" not in st.session_state:
    st.session_state.total = 0
if "done" not in st.session_state:
    st.session_state.done = False
if "current_question" not in st.session_state:
    st.session_state.current_question = 0
if "score" not in st.session_state:
    st.session_state.score = 0
if "answers" not in st.session_state:
    st.session_state.answers = []

# =============================================================================
# Initialize Chat Model (for both chatbot & MCQ generation)
# =============================================================================
chat = ChatGroq(
    temperature=0.7,
    model_name="llama3-70b-8192",
    groq_api_key="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"
)

# =============================================================================
# LLM Query Function for MCQ Generation
# =============================================================================
def query_llama3(user_query):
    # You can update the topic string here if needed.
    topic = "Integration"
    system_prompt = f"""
System Prompt: You are an expert educational assessment generator trained to provide engaging multiple-choice questions (MCQs) for enterprise-level adaptive learning systems on the topic {topic}. Your task is to:

• Analyze given educational content and generate MCQs that are relevant to the topic and appropriate in difficulty.
• The questions should be accurate and not based on your imagination.
• Generate four answer choices for each question (A, B, C, D), ensuring that only one is correct and the others are plausible distractors.
• Mark the correct answer clearly using the format: [Que, A, B, C, D, Ans], where Que is the question, A, B, C, D are the options, and Ans is the correct answer.
• Adapt content dynamically – make questions easier or harder based on user performance.
• Ensure quality – questions must be clear, grammatically correct, and intuitive for users.
• Maintain a UI-friendly structure – the format should be clean and suitable for integration into frontend interfaces.
• Give the output in the form of a Python list, and only a list, nothing more.
• Ensure that every nested list has exactly 6 elements.
• For True/False questions, only give 2 options (e.g., [Que, True, False, Ans]).
"""
    past_chat = st.session_state.memory.load_memory_variables({}).get("chat_history", [])
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Past Chat: {past_chat}\n\nUser: {user_query}")
    ]
    try:
        response = chat.invoke(messages)
        st.session_state.memory.save_context({"input": user_query}, {"output": response.content})
        return response.content if response else "⚠️ No response."
    except Exception as e:
        return f"⚠️ Error: {str(e)}"

# =============================================================================
# Page Configuration & Styling
# =============================================================================
st.set_page_config(page_title="EduMind AI: MCQ Generator & Chatbot", page_icon="🧠", layout="wide")
st.markdown("""
<style>
body {
    background-color: #121212;
    color: #E0E0E0;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
.title-container {
    text-align: center;
    font-size: 64px;
    font-weight: bold;
    margin-top: 10px;
}
.sidebar {
    padding: 20px;
}
</style>
""", unsafe_allow_html=True)
st.markdown("<div class='title-container'>🤖 <b>EduMind AI</b></div>", unsafe_allow_html=True)

# =============================================================================
# Sidebar: Mode Selection
# =============================================================================
mode = st.sidebar.radio("Select Mode:", ["MCQ Generator", "Educational Chatbot"])

# =============================================================================
# MCQ Generator Section (Revised per Reference Code)
# =============================================================================
def render_mcq_generator():
    st.markdown("## MCQ Generator")
    # If no test in progress, show topic input and generate button
    if st.session_state.current_question == 0 and not st.session_state.questions:
        st.session_state.topic = st.text_input("Enter Topic:", key="topic_input")
        if st.button("Generate MCQ"):
            st.session_state.generate_button = True

    # When the "Generate MCQ" button is pressed for the first time, call the LLM
    if st.session_state.once and st.session_state.topic and st.session_state.generate_button:
        response_content = query_llama3(st.session_state.topic)
        try:
            # Expecting a string representation of a Python list
            st.session_state.questions = ast.literal_eval(response_content)
        except Exception as e:
            st.error("Error parsing MCQ response: " + str(e))
            st.stop()
        st.session_state.total = len(st.session_state.questions)
        st.session_state.once = False
        st.session_state.done = False
        st.session_state.current_question = 0
        st.session_state.score = 0
        st.session_state.answers = []

    # Display current MCQ and handle answer selection
    if st.session_state.questions and not st.session_state.done:
        idx = st.session_state.current_question
        current_question_data = st.session_state.questions[idx]
        question_text = current_question_data[0]
        options = current_question_data[1:-1]
        correct_answer = current_question_data[-1]
        
        st.markdown(f"**Question {idx+1}: {question_text}**")
        answer = None
        for i, option in enumerate(options):
            if st.button(option, key=f"answer_{i}_{idx}"):
                answer = option
        
        if answer is not None:
            st.session_state.answers.append(answer)
            if answer == correct_answer:
                st.session_state.score += 1
            if st.session_state.current_question < st.session_state.total - 1:
                st.session_state.current_question += 1
                st.experimental_rerun()
            else:
                st.session_state.done = True
                st.experimental_rerun()

    # When test is complete, show summary and option to start a new test
    if st.session_state.done:
        st.markdown("### You've completed the test! Here's your summary:")
        st.write(f"Your score is **{st.session_state.score}** out of **{st.session_state.total}**.")
        if st.button("New Test"):
            # Clear all session state keys and reload
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.experimental_rerun()

# =============================================================================
# Educational Chatbot Section
# =============================================================================
def render_chatbot():
    st.markdown("## Educational Chatbot")
    user_input = st.text_input("Your question:")
    if st.button("Send"):
        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            messages = [HumanMessage(content=user_input)]
            try:
                response = chat.invoke(messages)
                st.session_state.chat_history.append({"role": "assistant", "content": response.content})
            except Exception as e:
                st.error("Error: " + str(e))
    for message in st.session_state.chat_history:
        if message["role"] == "user":
            st.markdown(f"**User:** {message['content']}")
        else:
            st.markdown(f"**Assistant:** {message['content']}")

# =============================================================================
# Main App Function: Render Mode Based UI
# =============================================================================
def main():
    if mode == "MCQ Generator":
        render_mcq_generator()
    elif mode == "Educational Chatbot":
        render_chatbot()

if __name__ == "__main__":
    main()
