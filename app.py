import streamlit as st
import os
import logging
from dotenv import load_dotenv

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()
logging.info(".env file loaded (if exists).")

# --- Check for Critical Environment Variables ---
# Do essential checks early, before trying to render complex tabs
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME") # Needed by rag_util

if not OPENAI_API_KEY:
    st.error("FATAL: OPENAI_API_KEY environment variable is not set. Please check your .env file or environment.")
    logging.critical("OPENAI_API_KEY environment variable is not set.")
    st.stop()
if not S3_BUCKET_NAME:
    st.error("FATAL: S3_BUCKET_NAME environment variable is not set. Please check your .env file or environment.")
    logging.critical("S3_BUCKET_NAME environment variable is not set.")
    st.stop()

# --- Import Tab Rendering Functions ---
# Assuming db_connection, rag_utils etc. are available in the python path
try:
    from tabs import student_report, shortlist_users, college_explorer, ai_tools, koda_chats
except ImportError as e:
    st.error(f"Failed to import tab modules: {e}. Ensure the 'tabs' directory and files exist and are structured correctly.")
    logging.critical(f"Tab module import error: {e}", exc_info=True)
    st.stop()
except Exception as e:
     st.error(f"Error during initial imports: {e}")
     logging.critical(f"Initial import error: {e}", exc_info=True)
     st.stop()


# --- Initialize Session State ---
# Central place to initialize all keys used across tabs helps avoid errors
def initialize_session_state():
    # Student Report Tab State
    if "current_user_data" not in st.session_state: st.session_state["current_user_data"] = None
    if "current_shortlists" not in st.session_state: st.session_state["current_shortlists"] = None
    if "generated_report_text" not in st.session_state: st.session_state["generated_report_text"] = ""
    if "rag_answer" not in st.session_state: st.session_state["rag_answer"] = ""
    if "shortlist_selected_date" not in st.session_state: st.session_state["shortlist_selected_date"] = None
    if "shortlisted_users_list" not in st.session_state: st.session_state["shortlisted_users_list"] = []
    if "shortlist_selected_user_id" not in st.session_state: st.session_state["shortlist_selected_user_id"] = None
    if "shortlist_generated_messages" not in st.session_state: st.session_state["shortlist_generated_messages"] = []
    if "college_explorer_interactions" not in st.session_state: st.session_state["college_explorer_interactions"] = {}
    if "college_explorer_selected_interaction_index" not in st.session_state: st.session_state["college_explorer_selected_interaction_index"] = None
    if "college_explorer_fetched_data" not in st.session_state: st.session_state["college_explorer_fetched_data"] = {}
    if "college_explorer_target_selection" not in st.session_state: st.session_state["college_explorer_target_selection"] = None
    if "college_explorer_generated_messages" not in st.session_state: st.session_state["college_explorer_generated_messages"] = {}
    if "college_explorer_loaded_date" not in st.session_state: st.session_state["college_explorer_loaded_date"] = None

    # Add new keys for AI Tools tab
    if "ai_tools_users_list" not in st.session_state: st.session_state["ai_tools_users_list"] = None
    if "ai_tools_selected_userid" not in st.session_state: st.session_state["ai_tools_selected_userid"] = None
    if "ai_tools_generated_messages" not in st.session_state: st.session_state["ai_tools_generated_messages"] = {} # Cache per userid
    # Add keys for Koda Chats tab later if needed
    if "koda_chats_loaded_date" not in st.session_state: st.session_state["koda_chats_loaded_date"] = None
    if "koda_chats_user_list" not in st.session_state: st.session_state["koda_chats_user_list"] = {} # Cache per date
    if "koda_chats_selected_user_index" not in st.session_state: st.session_state["koda_chats_selected_user_index"] = None
    if "koda_chats_ielts_profile" not in st.session_state: st.session_state["koda_chats_ielts_profile"] = {} # Cache per user index
    if "koda_chats_summary" not in st.session_state: st.session_state["koda_chats_summary"] = {} # Cache per user index


# --- Main Streamlit App Logic ---
def main():
    st.set_page_config(page_title="Kandor AI Tools", layout="wide")
    st.title("Kandor AI Assistant & Sales Tools")

    # Initialize session state keys if they don't exist
    initialize_session_state()

    # --- Define Tabs ---
    tab_titles = ["Student Report", "Shortlist Users", "College Explorer", "AI Tools", "Koda Chats"]
    tab1, tab2, tab3, tab4, tab5 = st.tabs(tab_titles)

    # --- Render Tabs by Calling Functions from Imported Modules ---
    with tab1:
        student_report.render() # Call the render function from student_report.py

    with tab2:
        shortlist_users.render() # Call the render function from shortlist_users.py

    with tab3:
        college_explorer.render() # Call the render function from college_explorer.py

    with tab4:
        ai_tools.render() # Call the render function from deadline_approaching.py

    with tab5:
        koda_chats.render() # Call the render function from followup_dashboard.py

# --- Main Execution ---
if __name__ == "__main__":
    try:
         main()
    except Exception as main_e:
         logging.critical(f"Critical error during Streamlit app execution: {main_e}", exc_info=True)
         st.error(f"A critical error occurred in the application structure: {main_e}")