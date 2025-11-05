from flask import Flask, render_template, jsonify, request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from src.helper import download_hugging_face_embeddings
from langchain_pinecone import PineconeVectorStore
from langchain_openai import ChatOpenAI
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from src.prompt import *
import os
import logging
from functools import wraps
import hashlib


app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# Configure caching
cache = Cache(app, config={
    'CACHE_TYPE': 'SimpleCache',
    'CACHE_DEFAULT_TIMEOUT': 300
})

# Configure rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('medical_chatbot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

PINECONE_API_KEY=os.environ.get('PINECONE_API_KEY')
OPENAI_API_KEY=os.environ.get('OPENAI_API_KEY')

os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY


embeddings = download_hugging_face_embeddings()

index_name = "medical-chatbot" 
# Embed each chunk and upsert the embeddings into your Pinecone index.
docsearch = PineconeVectorStore.from_existing_index(
    index_name=index_name,
    embedding=embeddings
)




retriever = docsearch.as_retriever(
    search_type="mmr",  # Use MMR for diversity in retrieved documents
    search_kwargs={
        "k": 4,  # Increased from 3 for more context
        "fetch_k": 10,  # Fetch more candidates for MMR
        "lambda_mult": 0.7  # Balance between relevance (1.0) and diversity (0.0)
    }
)

chatModel = ChatOpenAI(model="gpt-4o")
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("human", "{input}"),
    ]
)

question_answer_chain = create_stuff_documents_chain(chatModel, prompt)
rag_chain = create_retrieval_chain(retriever, question_answer_chain)



@app.route("/")
def index():
    return render_template('chat.html')


@app.route("/health")
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Medical Chatbot",
        "version": "1.0.0"
    }), 200


@app.route("/ready")
def ready():
    """Readiness check endpoint"""
    try:
        # Check if critical services are available
        if docsearch and rag_chain:
            return jsonify({
                "status": "ready",
                "pinecone": "connected",
                "llm": "initialized"
            }), 200
        else:
            return jsonify({"status": "not ready"}), 503
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        return jsonify({"status": "not ready", "error": str(e)}), 503



@app.route("/get", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def chat():
    try:
        # Initialize session history if not exists
        if 'chat_history' not in session:
            session['chat_history'] = []

        # Validate request
        if not request.form.get("msg"):
            logger.warning("Empty message received")
            return jsonify({"error": "Message cannot be empty"}), 400

        msg = request.form["msg"].strip()

        # Input validation
        if len(msg) > 1000:
            logger.warning(f"Message too long: {len(msg)} characters")
            return jsonify({"error": "Message is too long. Please keep it under 1000 characters."}), 400

        if len(msg) < 3:
            logger.warning(f"Message too short: {len(msg)} characters")
            return jsonify({"error": "Message is too short. Please provide more details."}), 400

        logger.info(f"User query: {msg}")

        # Check cache first
        cache_key = f"query:{hashlib.md5(msg.lower().encode()).hexdigest()}"
        cached_response = cache.get(cache_key)

        if cached_response:
            logger.info("Returning cached response")
            # Still add to history even if cached
            session['chat_history'].append({
                'question': msg,
                'answer': cached_response,
                'timestamp': str(__import__('datetime').datetime.now())
            })
            session.modified = True
            return str(cached_response)

        # Invoke RAG chain
        response = rag_chain.invoke({"input": msg})
        answer = response["answer"]

        # Store in conversation history
        session['chat_history'].append({
            'question': msg,
            'answer': answer,
            'timestamp': str(__import__('datetime').datetime.now())
        })
        session.modified = True

        # Keep only last 20 conversations in session
        if len(session['chat_history']) > 20:
            session['chat_history'] = session['chat_history'][-20:]

        # Cache the response
        cache.set(cache_key, answer, timeout=300)

        logger.info(f"Response generated successfully")
        return str(answer)

    except KeyError as e:
        logger.error(f"KeyError in chat endpoint: {str(e)}")
        return jsonify({"error": "Invalid request format"}), 400

    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        return jsonify({"error": "An error occurred while processing your request. Please try again."}), 500


@app.route("/history", methods=["GET"])
def get_history():
    """Get conversation history"""
    try:
        history = session.get('chat_history', [])
        return jsonify({"history": history}), 200
    except Exception as e:
        logger.error(f"Error retrieving history: {str(e)}")
        return jsonify({"error": "Could not retrieve history"}), 500


@app.route("/clear", methods=["POST"])
def clear_history():
    """Clear conversation history"""
    try:
        session['chat_history'] = []
        session.modified = True
        return jsonify({"message": "History cleared successfully"}), 200
    except Exception as e:
        logger.error(f"Error clearing history: {str(e)}")
        return jsonify({"error": "Could not clear history"}), 500


@app.route("/feedback", methods=["POST"])
def feedback():
    """Store user feedback"""
    try:
        feedback_type = request.form.get("feedback")
        timestamp = request.form.get("timestamp")

        if 'feedback_data' not in session:
            session['feedback_data'] = []

        session['feedback_data'].append({
            'type': feedback_type,
            'timestamp': timestamp
        })
        session.modified = True

        logger.info(f"Feedback received: {feedback_type}")
        return jsonify({"message": "Feedback received"}), 200
    except Exception as e:
        logger.error(f"Error storing feedback: {str(e)}")
        return jsonify({"error": "Could not store feedback"}), 500



if __name__ == '__main__':
    app.run(host="0.0.0.0", port= 8080, debug= True)
