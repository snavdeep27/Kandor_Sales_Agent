import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain_aws import AmazonKnowledgeBasesRetriever  # Using the AWS retriever
from langchain.chains import RetrievalQA

def init_openai():
    """
    Sets up OpenAI credentials from environment variables.
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("The OPENAI_API_KEY environment variable is not set.")
    # ChatOpenAI will pick up the API key from the environment automatically.
    # Alternatively, you can pass it explicitly via the openai_api_key parameter.

def create_bedrock_rag_chain(knowledge_base_id: str, top_k: int = 3):
    """
    Creates a RetrievalQA chain that uses:
      1. An Amazon Knowledge Bases Retriever to fetch relevant documents
      2. OpenAI's ChatGPT-4o (ChatOpenAI) for final answer generation.
    """
    # Initialize OpenAI credentials.
    init_openai()

    # Read AWS region from environment variables.
    region_name = os.getenv("AWS_REGION", "us-east-2")
    
    # Create the Amazon Knowledge Base retriever.
    # Note: If you use environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY),
    # you don't need to pass credentials_profile_name.
    retriever = AmazonKnowledgeBasesRetriever(
        region_name=region_name,
        knowledge_base_id=knowledge_base_id,
        top_k=top_k
    )

    # Create the OpenAI Chat model (ChatGPT-4o).
    llm = ChatOpenAI(model_name="gpt-4o", temperature=0.3)

    # Build the RetrievalQA chain.
    rag_chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        chain_type="stuff",  # You may change this type if needed.
        return_source_documents=True
    )
    return rag_chain



def do_rag_query(rag_chain, user_query: str, user_profile: dict = None):
    system_prompt = f"""
You are an AI counselor that provides study-abroad guidance.
You have access to a knowledge base for retrieving relevant information about courses, scholarships,
visa policies, etc.

User Profile:
{json.dumps(user_profile or {}, indent=2, default=str)}

Provide accurate, concise responses. If unsure, say so.
    """.strip()

    combined_prompt = f"{system_prompt}\n\nUser: {user_query}\nAnswer:"

    # Let's see the entire raw response
    response = rag_chain.invoke(combined_prompt)

    # Print to your console logs
    print("Full chain response:", response)

    # Also you can do st.write in Streamlit for debugging:
    import streamlit as st
    st.write("Full chain response:", response)

    # Check for various keys:
    if isinstance(response, dict):
        # Sometimes it might be 'result'
        if "text" in response:
            return response["text"]
        elif "result" in response:
            return response["result"]
        else:
            return "No recognized text key in chain response."
    else:
        return str(response)
