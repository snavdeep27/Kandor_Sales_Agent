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
# === LLM Model Change for Accuracy ===
# Switched default ANSWERING_LLM_MODEL to gpt-4o for potentially better accuracy
ANSWERING_LLM_MODEL = os.getenv('LLM_MODEL', 'gpt-4o') # <<< CHANGED DEFAULT
# Keep router as mini for speed/cost unless routing proves inaccurate
ROUTING_LLM_MODEL = 'gpt-4o-mini'
# =====================================
logging.info(f"Using Answering LLM: {ANSWERING_LLM_MODEL}, Routing LLM: {ROUTING_LLM_MODEL}")

DEFAULT_TOP_K = 5

# --- Vector Store Definitions ---
# (Keep VECTOR_STORE_IDS and VECTOR_STORE_DESCRIPTIONS as they were)
VECTOR_STORE_IDS = {
    "course_details_source1": "vs_course_details_with_outcomes",
    "professions_immigration": "vs_professions_data_immigration",
    "professions_jobs": "vs_professions_data_with_jobs",
    "university_details": "vs_processed_data_university",
    "course_details_source2": "vs_course_details_with_outcomes_second_source"
}
VECTOR_STORE_DESCRIPTIONS = {
    "course_details_source1": "Contains detailed information about specific university courses from source 1, including subjects, descriptions, admissions criteria, career paths, and linked professions.",
    "professions_immigration": "Contains information about immigration pathways, permanent residency difficulty, post-study work visas, ideal regions, and PR programs for specific professions in various countries (Australia, NZ, Ireland, UK, Germany, Canada, USA).",
    "professions_jobs": "Contains general information about specific professions, including descriptions, salary ranges, prospects, required attributes, and approximate job numbers in various countries.",
    "university_details": "Contains general information about universities, including location, establishment date, descriptions, overall admission requirements (exams, fees), rankings, and intake sessions.",
    "course_details_source2": "Contains information about specific university courses from source 2, primarily focused on admissions criteria like fees, deadlines, entry requirements, and test scores (IELTS, TOEFL, etc.)."
}

# --- AWS S3 Configuration ---
# (Keep as is)
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION")
if not S3_BUCKET_NAME:
    raise ValueError("FATAL: S3_BUCKET_NAME environment variable is not set.")

# --- Global Variables / Caching ---
# (Keep as is)
_embedding_model_instance: Optional[OpenAIEmbeddings] = None
_vector_stores: Dict[str, Optional[LCFAISS]] = {}
_retriever_cache: Dict[str, VectorStoreRetriever] = {}
_answering_llm: Optional[ChatOpenAI] = None
_routing_llm: Optional[ChatOpenAI] = None

# --- Initialization Functions ---
# (Keep get_embedding_model, load_faiss_vector_store, get_faiss_retriever as they were)
def get_embedding_model() -> OpenAIEmbeddings:
    # ... (no changes needed) ...
    global _embedding_model_instance
    if _embedding_model_instance is None:
        logging.info(f"Initializing OpenAI Embeddings with model: {EMBEDDING_MODEL}")
        _embedding_model_instance = OpenAIEmbeddings(model=EMBEDDING_MODEL, openai_api_key=OPENAI_API_KEY)
    return _embedding_model_instance

def load_faiss_vector_store(vector_store_id: str) -> LCFAISS:
    # ... (no changes needed) ...
    global _vector_stores
    if vector_store_id in _vector_stores and _vector_stores[vector_store_id] is not None: return _vector_stores[vector_store_id]
    if vector_store_id not in VECTOR_STORE_IDS: raise ValueError(f"Unknown vector_store_id: {vector_store_id}.")
    s3_vector_prefix = VECTOR_STORE_IDS[vector_store_id]
    embeddings = get_embedding_model()
    with tempfile.TemporaryDirectory() as tmpdir:
        # ... (S3 download logic remains the same) ...
        try:
            s3_client_args = {}
            if AWS_REGION: s3_client_args['region_name'] = AWS_REGION
            session = boto3.Session(aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"), aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
            s3_client = session.client('s3', **s3_client_args)
            local_faiss_path = os.path.join(tmpdir, "index.faiss"); local_pkl_path = os.path.join(tmpdir, "index.pkl")
            s3_faiss_key = f"{s3_vector_prefix}/index.faiss"; s3_pkl_key = f"{s3_vector_prefix}/index.pkl"
            logging.info(f"Downloading {s3_faiss_key}..."); s3_client.download_file(S3_BUCKET_NAME, s3_faiss_key, local_faiss_path)
            logging.info(f"Downloading {s3_pkl_key}..."); s3_client.download_file(S3_BUCKET_NAME, s3_pkl_key, local_pkl_path)
        except ClientError as e: logging.error(f"S3 Download Error for '{vector_store_id}': {e}", exc_info=True); raise FileNotFoundError(f"FAISS files not found for '{vector_store_id}'.") from e
        except Exception as e: logging.error(f"Unexpected S3 Error for '{vector_store_id}': {e}", exc_info=True); raise
        # ... (FAISS load logic remains the same) ...
        try:
            vs = LCFAISS.load_local(tmpdir, embeddings, allow_dangerous_deserialization=True)
            _vector_stores[vector_store_id] = vs
            logging.info(f"FAISS index '{vector_store_id}' loaded successfully.")
            return vs
        except Exception as e: logging.error(f"FAISS Load Error for '{vector_store_id}': {e}", exc_info=True); _vector_stores[vector_store_id] = None; raise

def get_faiss_retriever(vector_store_id: str, k: int = DEFAULT_TOP_K) -> VectorStoreRetriever:
    # ... (no changes needed) ...
    global _retriever_cache
    cache_key = f"{vector_store_id}_k{k}"
    if cache_key not in _retriever_cache:
        logging.info(f"Creating FAISS retriever for '{vector_store_id}', k={k}")
        vs = load_faiss_vector_store(vector_store_id)
        _retriever_cache[cache_key] = vs.as_retriever(search_type="similarity", search_kwargs={"k": k})
    return _retriever_cache[cache_key]

# Updated get_llm to handle potentially different timeout/settings for gpt-4o
def get_llm(model_name: str) -> ChatOpenAI:
    """Initializes and returns a specific ChatOpenAI model instance."""
    global _answering_llm, _routing_llm

    if model_name == ANSWERING_LLM_MODEL:
        if _answering_llm is None or _answering_llm.model_name != model_name: # Re-init if model changes
            logging.info(f"Initializing Answering OpenAI LLM: {model_name}")
            # Use longer timeout for potentially more complex answers from gpt-4o
            request_timeout = 120 if 'gpt-4' in model_name else 90
            _answering_llm = ChatOpenAI(
                model_name=model_name,
                temperature=0.2, # Slightly lower temp for more factual focus
                openai_api_key=OPENAI_API_KEY,
                request_timeout=request_timeout
            )
        return _answering_llm
    elif model_name == ROUTING_LLM_MODEL:
         if _routing_llm is None or _routing_llm.model_name != model_name: # Re-init if model changes
            logging.info(f"Initializing Routing OpenAI LLM: {model_name}")
            _routing_llm = ChatOpenAI(
                model_name=model_name,
                temperature=0.0,
                openai_api_key=OPENAI_API_KEY,
                request_timeout=45
            )
         return _routing_llm
    else:
         logging.warning(f"Requested unknown LLM model '{model_name}', returning default answering LLM.")
         return get_llm(ANSWERING_LLM_MODEL)


# --- LLM Router ---
# (Keep route_query_to_store as is - uses ROUTING_LLM_MODEL)
@retry(stop=stop_after_attempt(2), wait=wait_random_exponential(multiplier=1, max=10))
def route_query_to_store(user_query: str) -> Optional[str]:
    # ... (no changes needed) ...
    routing_llm = get_llm(ROUTING_LLM_MODEL)
    descriptions_str = ""; valid_keys = list(VECTOR_STORE_IDS.keys())
    for key in valid_keys: descriptions_str += f"- {key}: {VECTOR_STORE_DESCRIPTIONS.get(key, 'No description')}\n"
    prompt = ChatPromptTemplate.from_messages([("system", "..."), ("human", "{query}")]) # Keep prompt structure
    # Simplified prompt content for brevity
    system_prompt = (
        "You are an expert query router for a study abroad knowledge base. "
        "Your task is to determine the single most relevant knowledge base for a given user query. "
        "Choose from the following available knowledge base IDs:\n\n"
        f"{descriptions_str}\n"
        f"Based on the user's query, identify the knowledge base ID from the list above that is most likely to contain the answer. "
        f"Respond ONLY with the chosen knowledge base ID (e.g., '{valid_keys[0]}', '{valid_keys[1]}') and nothing else."
    )
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", "{query}")])
    chain = prompt | routing_llm | StrOutputParser()
    logging.info(f"Routing query: '{user_query}'")
    try:
        llm_response = chain.invoke({"query": user_query})
        chosen_key = llm_response.strip().replace("'", "").replace('"', '')
        if chosen_key in VECTOR_STORE_IDS:
             logging.info(f"Routing decision: Chose key '{chosen_key}' for query: '{user_query}'")
             return chosen_key
        else: # Fallback logic remains the same
             matching_key = next((key for key, val in VECTOR_STORE_IDS.items() if val == chosen_key), None)
             if matching_key: logging.warning(f"Router LLM returned value '{chosen_key}'. Mapping to key: '{matching_key}'"); return matching_key
             else: logging.warning(f"Router LLM returned invalid response: '{llm_response}'. Falling back."); return None
    except Exception as e: logging.error(f"Error during query routing: {e}", exc_info=True); return None

# --- RAG Query Logic ---

# (Keep format_retrieved_docs as is)
def format_retrieved_docs(docs: List[Document]) -> str:
    # ... (no changes needed) ...
    formatted_strings = []
    if not docs: return "No relevant documents found in the specified knowledge base."
    for i, doc in enumerate(docs):
        content = doc.metadata.get("blurb_text", doc.page_content)
        source_id_keys = ['university_id', 'profession_id', 'course_id', 'serial_no', 'source_file']
        source_id = next((f"{key}: {doc.metadata[key]}" for key in source_id_keys if key in doc.metadata and doc.metadata[key]), f"source: {doc.metadata.get('source_file', 'N/A')}")
        formatted_strings.append(f"--- Document {i+1} ---\nSource Info: {source_id}\n\nContent Chunk:\n{content}\n--- End Document {i+1} ---")
    return "\n\n".join(formatted_strings)


def do_rag_query(
    user_query: str,
    user_profile: Optional[Dict[str, Any]] = None, # MUST contain data like highestLevel, DreamCountry etc.
    top_k: int = DEFAULT_TOP_K,
) -> str:
    """
    Performs RAG using specific FAISS stores selected by an LLM router.
    Uses potentially enhanced LLM and prompt for answering.
    """
    try:
        # Use the potentially updated ANSWERING_LLM_MODEL (e.g., gpt-4o)
        answering_llm = get_llm(ANSWERING_LLM_MODEL)

        # --- Routing Step --- (No changes needed) ---
        routing_start_time = time.time()
        chosen_vector_store_id = route_query_to_store(user_query)
        routing_end_time = time.time(); logging.info(f"Routing took {routing_end_time - routing_start_time:.2f} seconds.")
        if not chosen_vector_store_id: return "Sorry, I could not determine the relevant knowledge base for your query."

        # --- Retrieval Step --- (No changes needed) ---
        retrieval_start_time = time.time()
        logging.info(f"Retrieval phase: Retrieving top {top_k} documents from store '{chosen_vector_store_id}'")
        retriever = get_faiss_retriever(vector_store_id=chosen_vector_store_id, k=top_k)
        try: final_docs = retriever.invoke(user_query)
        except FileNotFoundError: return f"Error: The knowledge base '{chosen_vector_store_id}' is currently unavailable."
        except Exception as e: logging.error(f"Error retrieving documents from store '{chosen_vector_store_id}': {e}", exc_info=True); return f"Error: Could not retrieve information from the '{chosen_vector_store_id}' knowledge base."
        retrieval_end_time = time.time(); logging.info(f"Retrieved {len(final_docs)} documents from '{chosen_vector_store_id}' in {retrieval_end_time - retrieval_start_time:.2f} seconds.")

        # --- Formatting & LLM Call Step ---
        logging.info(f"Formatting {len(final_docs)} final documents for LLM.")
        context_str = format_retrieved_docs(final_docs)

        # === ENHANCED Answering Prompt Template ===
        template = """
You are an expert AI counselor providing study-abroad guidance. Your goal is to answer the user's query accurately and relevantly based *only* on the provided context documents and the user's profile.

**CRITICAL INSTRUCTIONS:**
1.  **Prioritize User Profile:** Carefully review the provided 'User Profile'. Tailor your answer to match the user's specific details like 'highestLevel' (e.g., Bachelors, Masters), 'DreamCountry', 'category'/'subCategory' (their field of interest), 'career' goals, and 'Funds'/'selectedPlan' (budget).
2.  **Filter Context:** Answer the query using *only* information from the 'Retrieved Context Documents' that aligns with the User Profile details (especially desired education level, country, and field).
3.  **Acknowledge Mismatches:** If the context documents discuss options that *do not* match the user's profile (e.g., documents mention Bachelor's degrees but the user profile indicates 'Masters' level), explicitly state that the available information might not be for the correct level/field/country based on the user's profile. Do NOT present mismatched information as suitable.
4.  **Cite Sources:** When possible, reference the source information for the document(s) used (e.g., "According to Document [N] (Source: ...)").
5.  **No External Knowledge:** Do not make up information or use knowledge outside the provided context and profile.
6.  **Handle Missing Info:** If the context documents do not contain information to answer the query, even considering the profile, clearly state that the specific information is not available in the retrieved documents.

**User Profile:**
```json
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

