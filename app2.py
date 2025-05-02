# app2.py - MVP RAG Bot Tester

import streamlit as st
import os
import logging
from dotenv import load_dotenv
import json # For displaying user profile nicely

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()
logging.info("app2.py: .env file loaded (if exists).")

# --- Check for Critical Environment Variables ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME") 

if not OPENAI_API_KEY or not S3_BUCKET_NAME:
    st.error("FATAL: OPENAI_API_KEY or S3_BUCKET_NAME environment variables not set. Please check your .env file or environment.")
    logging.critical("OPENAI_API_KEY or S3_BUCKET_NAME environment variable not set.")
    st.stop()

# --- Import Core Logic ---
try:
    # Assuming db_connection.py is in the same directory or accessible via PYTHONPATH
    from db_connection import get_user_by_phone
    # rag_utils should contain the latest do_rag_query with multi-store routing
    from rag_utils import do_rag_query 
except ImportError as e:
    st.error(f"Failed to import required modules: {e}. Ensure db_connection.py and rag_utils.py are present and correct.")
    logging.critical(f"Module import error: {e}", exc_info=True)
    st.stop()
except Exception as e:
     st.error(f"Error during initial imports: {e}")
     logging.critical(f"Initial import error: {e}", exc_info=True)
     st.stop()

# --- Main Streamlit App Logic ---
def main():
    st.set_page_config(page_title="Koda MVP Tester (app2.py)", layout="wide")
    st.title("Koda MVP - RAG Tester")
    st.markdown("Testing Multi-Vector Store RAG with LLM Routing")

    # --- Initialize Session State ---
    # Store chat history for display
    if "messages" not in st.session_state:
        st.session_state.messages = []
    # Store loaded user data
    if "current_user_data" not in st.session_state:
        st.session_state["current_user_data"] = None
    # Store current query to prevent re-running on interaction
    if "current_query" not in st.session_state:
        st.session_state.current_query = ""
    if "last_answer" not in st.session_state:
        st.session_state.last_answer = ""

    # --- Sidebar for User Input ---
    with st.sidebar:
        st.header("User Selection")
        default_phone = os.getenv("DEFAULT_PHONE", "+919999999999") # Use same default
        phone_number = st.text_input("Enter Phone (with country code)", value=default_phone, key="phone_input")

        if st.button("Load User Data", key="load_user_btn"):
            st.session_state.current_query = "" # Reset query/answer on new user load
            st.session_state.last_answer = ""
            st.session_state.messages = [] # Clear chat history
            if not phone_number:
                st.warning("Please enter a phone number.")
                st.session_state["current_user_data"] = None
            else:
                with st.spinner("Fetching user data..."):
                    try:
                        user_data = get_user_by_phone(phone_number)
                        if not user_data:
                            st.error(f"No user found with phone: {phone_number}")
                            st.session_state["current_user_data"] = None
                        else:
                            st.session_state["current_user_data"] = user_data
                            st.success("User data loaded!")
                            logging.info(f"Loaded data for user: {phone_number}")
                            # Add initial greeting to chat
                            st.session_state.messages.append({"role": "assistant", "content": f"Hi {user_data.get('username', 'there')}! I'm Koda MVP. How can I help you with study abroad today?"})
                    except Exception as e:
                        st.error(f"Error loading user data: {e}")
                        logging.error(f"Database connection/query error for {phone_number}: {e}", exc_info=True)
                        st.session_state["current_user_data"] = None
        
        # Display loaded user data in sidebar
        if st.session_state.current_user_data:
             st.subheader("Loaded User Profile")
             # Display cleaned profile data relevant for context
             profile_display = {
                  "Username": st.session_state.current_user_data.get('username', 'N/A'),
                  "Email": st.session_state.current_user_data.get('usermail', 'N/A'),
                  "Target Country": st.session_state.current_user_data.get('DreamCountry', 'N/A'),
                  "Phone": st.session_state.current_user_data.get('phone', 'N/A'),
                  "Premium": st.session_state.current_user_data.get('isPremium', False),
                  # Add other relevant fields if needed by rag_utils user_profile context
             }
             st.json(profile_display, expanded=False)
        else:
             st.info("Load user data to begin.")


    # --- Main Chat Area ---
    st.header("Chat with Koda MVP")

    # Display chat messages from history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Accept user input
    if prompt := st.chat_input("Ask about courses, universities, immigration, jobs..."):
        st.session_state.current_query = prompt # Store the query
        
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        # Display user message immediately
        with st.chat_message("user"):
            st.markdown(prompt)

        # Check if user data is loaded before proceeding
        if not st.session_state.current_user_data:
             st.warning("Please load user data using the sidebar first.")
             st.stop()

        # Get response from RAG function
        with st.spinner("Koda is thinking... (Querying knowledge base & LLM)"):
            try:
                top_k_value = 5 # Or use st.number_input if you want it changeable per query
                logging.info(f"Calling do_rag_query with: query='{prompt}', top_k={top_k_value}")
                
                # --- Call the updated RAG function ---
                response = do_rag_query(
                    user_query=prompt,
                    user_profile=st.session_state.current_user_data, # Pass loaded user data
                    top_k=top_k_value
                )
                st.session_state.last_answer = response # Store the answer
                logging.info(f"Received response from do_rag_query.")

            except Exception as e:
                st.error(f"An error occurred while getting the answer: {e}")
                logging.error(f"Error calling do_rag_query from app2.py: {e}", exc_info=True)
                st.session_state.last_answer = f"Sorry, an internal error occurred. Details: {e}"

        # Add assistant response to chat history
        st.session_state.messages.append({"role": "assistant", "content": st.session_state.last_answer})
        # Display assistant response
        with st.chat_message("assistant"):
            st.markdown(st.session_state.last_answer)
            
        # Clear the query state after processing
        st.session_state.current_query = "" 

    elif not st.session_state.current_user_data:
         st.info("Load a user from the sidebar to start chatting.")

if __name__ == "__main__":
    # Ensure rag_utils is properly initialized (e.g., loads models)
    # No explicit init needed here as rag_utils uses lazy loading / caching
    try:
        main()
    except Exception as main_e:
        logging.critical(f"Critical error during Streamlit app execution: {main_e}", exc_info=True)
        st.error(f"A critical error occurred running the app: {main_e}")