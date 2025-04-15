#!/usr/bin/env python3

import os
import json
from dotenv import load_dotenv
import logging
from typing import List, Dict, Any, Optional, Tuple
import tempfile
import time 
import re # For parsing router output

import boto3
from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_random_exponential
# import numpy as np # No longer needed for reranking
# from sklearn.metrics.pairwise import cosine_similarity # No longer needed for reranking

# LangChain Imports
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS as LCFAISS
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda, RunnableParallel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()
logging.info(".env file loaded (if exists).")

# --- Constants ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("FATAL: OPENAI_API_KEY environment variable is not set.")

EMBEDDING_MODEL = "text-embedding-3-small"
ANSWERING_LLM_MODEL = os.getenv('LLM_MODEL', 'gpt-4o-mini') # LLM for final answer generation
ROUTING_LLM_MODEL = 'gpt-4o-mini' # Explicitly use gpt-4o-mini for routing
logging.info(f"Using Answering LLM: {ANSWERING_LLM_MODEL}, Routing LLM: {ROUTING_LLM_MODEL}")

DEFAULT_TOP_K = 5 # How many docs to retrieve and pass to LLM

# --- Vector Store Definitions ---
# Map descriptive names to S3 prefixes/local IDs
VECTOR_STORE_IDS = {
    "course_details_source1": "vs_course_details_with_outcomes", # From univ_course_desc.csv
    "professions_immigration": "vs_professions_data_immigration",
    "professions_jobs": "vs_professions_data_with_jobs",
    "university_details": "vs_processed_data_university",
    "course_details_source2": "vs_course_details_with_outcomes_second_source" # From courses_data_set_02.csv
}
# Create descriptions for the router prompt
VECTOR_STORE_DESCRIPTIONS = {
    "course_details_source1": "Contains detailed information about specific university courses from source 1, including subjects, descriptions, admissions criteria, career paths, and linked professions.",
    "professions_immigration": "Contains information about immigration pathways, permanent residency difficulty, post-study work visas, ideal regions, and PR programs for specific professions in various countries (Australia, NZ, Ireland, UK, Germany, Canada, USA).",
    "professions_jobs": "Contains general information about specific professions, including descriptions, salary ranges, prospects, required attributes, and approximate job numbers in various countries.",
    "university_details": "Contains general information about universities, including location, establishment date, descriptions, overall admission requirements (exams, fees), rankings, and intake sessions.",
    "course_details_source2": "Contains information about specific university courses from source 2, primarily focused on admissions criteria like fees, deadlines, entry requirements, and test scores (IELTS, TOEFL, etc.)."
}

# --- AWS S3 Configuration ---
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION") # Optional: Specify region if needed
if not S3_BUCKET_NAME:
    raise ValueError("FATAL: S3_BUCKET_NAME environment variable is not set.")

# --- Global Variables / Caching ---
_embedding_model_instance: Optional[OpenAIEmbeddings] = None
# Cache for loaded vector stores {vector_store_id: LCFAISS}
_vector_stores: Dict[str, Optional[LCFAISS]] = {}
# Cache for retrievers {vector_store_id_k_K: Retriever}
_retriever_cache: Dict[str, VectorStoreRetriever] = {}
_answering_llm: Optional[ChatOpenAI] = None
_routing_llm: Optional[ChatOpenAI] = None

# --- Initialization Functions ---

def get_embedding_model() -> OpenAIEmbeddings:
    global _embedding_model_instance
    if _embedding_model_instance is None:
        logging.info(f"Initializing OpenAI Embeddings with model: {EMBEDDING_MODEL}")
        _embedding_model_instance = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            openai_api_key=OPENAI_API_KEY
        )
    return _embedding_model_instance

def load_faiss_vector_store(vector_store_id: str) -> LCFAISS:
    """Loads a specific FAISS vector store from S3 or cache."""
    global _vector_stores
    if vector_store_id in _vector_stores and _vector_stores[vector_store_id] is not None:
        logging.debug(f"Using cached vector store: {vector_store_id}")
        return _vector_stores[vector_store_id]
        
    if vector_store_id not in VECTOR_STORE_IDS:
         raise ValueError(f"Unknown vector_store_id: {vector_store_id}. Available IDs: {list(VECTOR_STORE_IDS.keys())}")

    s3_vector_prefix = VECTOR_STORE_IDS[vector_store_id] # Get S3 prefix from ID map
    embeddings = get_embedding_model()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        local_faiss_path = os.path.join(tmpdir, "index.faiss")
        local_pkl_path = os.path.join(tmpdir, "index.pkl")
        s3_faiss_key = f"{s3_vector_prefix}/index.faiss"
        s3_pkl_key = f"{s3_vector_prefix}/index.pkl"
        logging.info(f"Attempting to download FAISS index '{vector_store_id}' from s3://{S3_BUCKET_NAME}/{s3_vector_prefix}/ to {tmpdir}")
        
        try:
            # Initialize S3 client
            s3_client_args = {}
            if AWS_REGION: s3_client_args['region_name'] = AWS_REGION
            # Consider using default credentials provider chain (IAM role, env vars, etc.)
            # instead of explicitly passing keys if running in AWS environment
            session = boto3.Session(
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"), # Prefer env var check here too
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
            )
            s3_client = session.client('s3', **s3_client_args)

            logging.info(f"Downloading {s3_faiss_key}...")
            s3_client.download_file(S3_BUCKET_NAME, s3_faiss_key, local_faiss_path)
            logging.info(f"Downloading {s3_pkl_key}...")
            s3_client.download_file(S3_BUCKET_NAME, s3_pkl_key, local_pkl_path)
            logging.info("Downloads complete.")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            logging.error(f"S3 Download Error for '{vector_store_id}' (Code: {error_code}): {e}", exc_info=True)
            if error_code == 'NoSuchKey' or 'NotFound' in str(e): raise FileNotFoundError(f"FAISS files not found for '{vector_store_id}' at s3://{S3_BUCKET_NAME}/{s3_vector_prefix}/") from e
            # Other error handling...
            raise ConnectionError(f"Failed S3 connect/download for '{vector_store_id}': {e}") from e
        except Exception as e:
            logging.error(f"Unexpected S3 Error for '{vector_store_id}': {e}", exc_info=True); raise

        logging.info(f"Loading FAISS index '{vector_store_id}' from {tmpdir}")
        try:
            # Load the vector store
            vs = LCFAISS.load_local(tmpdir, embeddings, allow_dangerous_deserialization=True)
            _vector_stores[vector_store_id] = vs # Cache it
            logging.info(f"FAISS index '{vector_store_id}' loaded successfully.")
            return vs
        except Exception as e:
            logging.error(f"FAISS Load Error for '{vector_store_id}': {e}", exc_info=True); raise
            _vector_stores[vector_store_id] = None # Mark as failed in cache
            raise # Re-raise the exception

def get_faiss_retriever(
    vector_store_id: str,
    k: int = DEFAULT_TOP_K
) -> VectorStoreRetriever:
    """
    Gets a retriever instance for a specific vector store.
    Args:
        vector_store_id: The identifier for the vector store (e.g., "university_details").
        k: Number of documents to retrieve.
    """
    global _retriever_cache
    cache_key = f"{vector_store_id}_k{k}" # Include vs_id in cache key

    if cache_key not in _retriever_cache:
        logging.info(f"Creating FAISS retriever for '{vector_store_id}', k={k}")
        vs = load_faiss_vector_store(vector_store_id) # Load the specific store
        
        # Simple similarity search retriever
        _retriever_cache[cache_key] = vs.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k}
        )
    else:
        logging.debug(f"Using cached FAISS retriever: {cache_key}")

    return _retriever_cache[cache_key]

def get_llm(model_name: str) -> ChatOpenAI:
    """Initializes and returns a specific ChatOpenAI model instance."""
    # Slightly modified to handle multiple LLM instances if needed, although only one used now
    global _answering_llm, _routing_llm
    
    if model_name == ANSWERING_LLM_MODEL:
        if _answering_llm is None:
            logging.info(f"Initializing Answering OpenAI LLM: {model_name}")
            _answering_llm = ChatOpenAI(
                model_name=model_name,
                temperature=0.3,
                openai_api_key=OPENAI_API_KEY,
                request_timeout=90 
            )
        return _answering_llm
    elif model_name == ROUTING_LLM_MODEL:
         if _routing_llm is None:
            logging.info(f"Initializing Routing OpenAI LLM: {model_name}")
            _routing_llm = ChatOpenAI(
                model_name=model_name,
                temperature=0.0, # Use low temperature for deterministic routing
                openai_api_key=OPENAI_API_KEY,
                request_timeout=45 # Routing should be faster
            )
         return _routing_llm
    else:
         # Fallback or error for unknown model request
         logging.warning(f"Requested unknown LLM model '{model_name}', returning default answering LLM.")
         return get_llm(ANSWERING_LLM_MODEL)


# --- LLM Router ---
@retry(stop=stop_after_attempt(2), wait=wait_random_exponential(multiplier=1, max=10)) # Retry routing once on failure
def route_query_to_store(user_query: str) -> Optional[str]:
    """
    Uses an LLM to determine the most relevant vector store ID (descriptive key) 
    for a given query. Returns one of the keys from VECTOR_STORE_IDS or None 
    if routing fails or response is invalid.
    """
    routing_llm = get_llm(ROUTING_LLM_MODEL)
    
    # Prepare descriptions string for the prompt
    descriptions_str = ""
    # IMPORTANT: Give the LLM the DESCRIPTIVE KEYS to choose from
    valid_keys = list(VECTOR_STORE_IDS.keys()) 
    for key in valid_keys:
        descriptions_str += f"- {key}: {VECTOR_STORE_DESCRIPTIONS.get(key, 'No description')}\n"
        
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert query router for a study abroad knowledge base. "
                "Your task is to determine the single most relevant knowledge base for a given user query. "
                "Choose from the following available knowledge base IDs:\n\n"
                f"{descriptions_str}\n"
                f"Based on the user's query, identify the knowledge base ID from the list above that is most likely to contain the answer. "
                f"Respond ONLY with the chosen knowledge base ID (e.g., '{valid_keys[0]}', '{valid_keys[1]}') and nothing else." # Provide examples
            ),
            ("human", "{query}"),
        ]
    )

    chain = prompt | routing_llm | StrOutputParser()
    
    logging.info(f"Routing query: '{user_query}'")
    try:
        llm_response = chain.invoke({"query": user_query})
        # Basic cleaning: remove potential quotes or extra whitespace
        chosen_key = llm_response.strip().replace("'", "").replace('"', '') 
        
        # --- CORRECTED VALIDATION ---
        # Check if the LLM returned a valid DESCRIPTIVE KEY
        if chosen_key in VECTOR_STORE_IDS: 
             logging.info(f"Routing decision: Chose key '{chosen_key}' for query: '{user_query}'")
             return chosen_key # Return the KEY
        else:
             # Optional: Check if it mistakenly returned the value (S3 prefix)
             # This is less ideal as the prompt asks for the key, but provides a fallback
             matching_key = next((key for key, val in VECTOR_STORE_IDS.items() if val == chosen_key), None)
             if matching_key:
                  logging.warning(f"Router LLM returned value '{chosen_key}' instead of key. Mapping to key: '{matching_key}'")
                  return matching_key # Return the KEY
             else:
                  logging.warning(f"Router LLM returned an invalid/unknown response: '{llm_response}'. Could not map to a valid key. Falling back.")
                  return None # Indicate routing failure 

    except Exception as e:
        logging.error(f"Error during query routing: {e}", exc_info=True)
        return None # Indicate routing failure
# --- RAG Query Logic ---

def format_retrieved_docs(docs: List[Document]) -> str:
    """Formats retrieved documents for insertion into the LLM prompt context."""
    formatted_strings = []
    if not docs:
        return "No relevant documents found in the specified knowledge base."
        
    for i, doc in enumerate(docs):
        # Extract metadata - use blurb_text if available, else page_content
        content = doc.metadata.get("blurb_text", doc.page_content) 
        source_id_keys = ['university_id', 'profession_id', 'course_id', 'serial_no', 'source_file']
        source_id = "N/A"
        for key in source_id_keys:
             if key in doc.metadata and doc.metadata[key]:
                  source_id = f"{key}: {doc.metadata[key]}"
                  break
             elif key == 'source_file' and 'source_file' in doc.metadata:
                  source_id = f"source: {doc.metadata['source_file']}"


        # Maybe include a snippet of the blurb instead of the whole thing if too long?
        content_snippet = (content[:500] + '...') if len(content) > 503 else content

        formatted_strings.append(
            f"--- Document {i+1} ---\n"
            f"Source Info: {source_id}\n\n" # More generic source info
            # Using blurb_text (which *is* the content chunk now)
            f"Content Chunk:\n{content}\n" 
            # f"Content Snippet:\n{content_snippet}\n" # Alternative: Use snippet
            f"--- End Document {i+1} ---"
        )
    return "\n\n".join(formatted_strings)

# Removed _rerank_docs_by_summary function

def do_rag_query(
    user_query: str,
    user_profile: Optional[Dict[str, Any]] = None,
    top_k: int = DEFAULT_TOP_K,
    # Removed use_mmr and use_rerank parameters
) -> str:
    """
    Performs RAG using specific FAISS stores selected by an LLM router.

    Args:
        user_query: The user's question.
        user_profile: Optional user profile dictionary.
        top_k: Final number of documents to retrieve and use for context.

    Returns:
        The generated answer string.
    """
    try:
        answering_llm = get_llm(ANSWERING_LLM_MODEL)
        
        # --- Routing Step ---
        routing_start_time = time.time()
        chosen_vector_store_id = route_query_to_store(user_query)
        routing_end_time = time.time()
        logging.info(f"Routing took {routing_end_time - routing_start_time:.2f} seconds.")

        if not chosen_vector_store_id:
            # Fallback strategy: Could search a default store, multiple stores, or just inform user
            logging.warning("Query routing failed or returned invalid ID. Cannot proceed with retrieval.")
            # You could try searching a default store here, e.g.:
            # chosen_vector_store_id = VECTOR_STORE_IDS["course_details_source1"] 
            # logging.info(f"Falling back to default store: {chosen_vector_store_id}")
            # Or simply return:
            return "Sorry, I could not determine the relevant knowledge base for your query."
            
        # --- Retrieval Step ---
        retrieval_start_time = time.time()
        logging.info(f"Retrieval phase: Retrieving top {top_k} documents from store '{chosen_vector_store_id}'")

        # Get the specific retriever
        retriever = get_faiss_retriever(
            vector_store_id=chosen_vector_store_id,
            k=top_k 
        )

        # Invoke the retriever
        # Handle potential errors during retrieval from a specific store
        try:
             final_docs = retriever.invoke(user_query)
        except FileNotFoundError:
             logging.error(f"Vector store '{chosen_vector_store_id}' not found locally or on S3.")
             return f"Error: The knowledge base '{chosen_vector_store_id}' is currently unavailable."
        except Exception as e:
             logging.error(f"Error retrieving documents from store '{chosen_vector_store_id}': {e}", exc_info=True)
             return f"Error: Could not retrieve information from the '{chosen_vector_store_id}' knowledge base."

        retrieval_end_time = time.time()
        logging.info(f"Retrieved {len(final_docs)} documents from '{chosen_vector_store_id}' in {retrieval_end_time - retrieval_start_time:.2f} seconds.")

        # --- Formatting & LLM Call Step ---
        logging.info(f"Formatting {len(final_docs)} final documents for LLM.")
        context_str = format_retrieved_docs(final_docs)

        template = """
You are an AI counselor providing study-abroad guidance. Answer the user's query based *only* on the provided context documents below, which were retrieved from the relevant knowledge base section.
Do not make up information or use external knowledge.
If the context does not contain the necessary information to answer the query, clearly state that the information is not available in the retrieved documents.
When possible, reference the source information provided for the document(s) used (e.g., "According to document [N] (Source: ...)").

User Profile:
{user_profile_json}

Retrieved Context Documents:
{context}

User Query: {question}

Answer:
        """.strip()
        prompt_template = ChatPromptTemplate.from_template(template)

        user_profile_str = json.dumps(user_profile or {}, indent=2, default=str)

        # Prepare inputs for the prompt
        prompt_inputs = {
            "context": context_str,
            "question": user_query,
            "user_profile_json": user_profile_str
        }

        # Build and invoke the generation part of the chain
        generation_chain = prompt_template | answering_llm | StrOutputParser()

        logging.info(f"Invoking Answering LLM ({ANSWERING_LLM_MODEL}) with formatted context...")
        llm_start_time = time.time()
        response = generation_chain.invoke(prompt_inputs)
        llm_end_time = time.time()
        logging.info(f"LLM invocation successful in {llm_end_time - llm_start_time:.2f} seconds.")

        return response

    except (FileNotFoundError, PermissionError, ConnectionError) as e:
        # Catch errors related to loading vector stores if they weren't caught earlier
        logging.error(f"Failed RAG setup/connection: {e}", exc_info=True)
        return f"Error: Could not load/access required knowledge base files. Details: {e}"
    except Exception as e:
        logging.error(f"An unexpected error occurred during RAG query execution: {e}", exc_info=True)
        return f"Sorry, an unexpected error occurred processing your request. Details: {e}"

