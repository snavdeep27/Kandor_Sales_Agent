import streamlit as st
import json
import os # Import os for getenv
from dotenv import load_dotenv
from io import BytesIO
from fpdf import FPDF
import logging

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Load .env file BEFORE accessing environment variables
load_dotenv()
logging.info(".env file loaded (if exists).")

# --- Check for Critical Environment Variables ---
# These need to be set in your .env file or system environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME") # Needed by rag_util

if not OPENAI_API_KEY:
    # Use st.error for Streamlit UI, but also log and maybe stop?
    st.error("FATAL: OPENAI_API_KEY environment variable is not set. Please check your .env file or environment.")
    logging.critical("OPENAI_API_KEY environment variable is not set.")
    st.stop() # Stop the Streamlit app execution
if not S3_BUCKET_NAME:
    st.error("FATAL: S3_BUCKET_NAME environment variable is not set. Please check your .env file or environment.")
    logging.critical("S3_BUCKET_NAME environment variable is not set.")
    st.stop() # Stop the Streamlit app execution

# Import your modules AFTER loading .env and checking critical vars
# Ensure these modules also use os.getenv if they need env vars
try:
    # Make sure these python files exist in the same directory or PYTHONPATH
    from db_connection import (
        get_user_by_phone,
        get_shortlists_by_user
    )
    from usecase_templates import generate_all_use_cases
    # rag_utils will use the env vars loaded by load_dotenv() here
    from rag_utils import do_rag_query
except ImportError as e:
    st.error(f"Failed to import required modules: {e}. Ensure db_connection.py, usecase_templates.py, and rag_utils.py are present.")
    logging.critical(f"Module import error: {e}", exc_info=True)
    st.stop()
except ValueError as e: # Catch ValueErrors raised by rag_util if its checks fail
     st.error(f"Configuration Error in imported module: {e}")
     logging.critical(f"Configuration Error from module: {e}")
     st.stop()


# --- PDF Generation Function ---
def generate_pdf_report(report_text: str) -> bytes:
    """
    Converts report text into a multi-page PDF, returning as bytes.
    Handles Unicode characters using a TTF font.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # --- Font Setup for Unicode ---
    try:
        # Define the path to your font file relative to the script location
        # Adjust 'fonts/DejaVuSans.ttf' or 'DejaVuSans.ttf' as needed
        font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf") 
        # If the font is in the same directory as app.py, just use "DejaVuSans.ttf"
        # If it's in a 'fonts' subdirectory, use "fonts/DejaVuSans.ttf"
        
        if not os.path.exists(font_path):
             # Try finding it in the current working directory as a fallback
             font_path = "DejaVuSans.ttf" 
             if not os.path.exists(font_path):
                  raise FileNotFoundError("DejaVuSans.ttf font file not found.")

        # Add the Unicode font. The 'uni=True' is crucial!
        pdf.add_font("DejaVu", "", font_path, uni=True) 
        pdf.set_font("DejaVu", size=12)
        logging.info("Using DejaVuSans font for PDF generation (Unicode enabled).")
        
    except (FileNotFoundError, RuntimeError) as font_error:
        logging.warning(f"DejaVuSans font failed to load ({font_error}). Falling back to Arial (limited Unicode support).")
        # Fallback if font file is missing or fails to load
        pdf.set_font("Arial", size=12)
        # Indicate in the PDF itself that encoding might be lossy
        pdf.set_text_color(255, 0, 0) # Red text
        pdf.cell(0, 10, txt="Warning: Using fallback font, some characters may not display correctly.", ln=1)
        pdf.set_text_color(0, 0, 0) # Back to black

    # --- Write Text Content ---
    lines = report_text.split("\n")
    for line in lines:
        try:
            # Pass the original Python string (UTF-8 decoded) directly.
            # FPDF handles encoding with uni=True font.
            pdf.multi_cell(0, 10, txt=line) 
        except Exception as e:
            # Log error if writing fails even with Unicode font setup
            logging.error(f"Could not add line to PDF: {line[:50]}... Error: {e}")
            try:
                # Try adding a placeholder using basic encoding
                pdf.multi_cell(0, 10, txt="[Error processing this line]".encode('latin-1', 'replace').decode('latin-1'))
            except: pass # Ignore if even error message fails


    # --- Output PDF Bytes ---
    try:
        # pdf.output returns bytes when dest='S'
        pdf_output = pdf.output(dest="S")
        # Ensure it's bytes (should be automatic with dest='S')
        if isinstance(pdf_output, str):
             # This case is unlikely now but kept as safeguard
             pdf_output = pdf_output.encode('utf-8') # Use utf-8 if needing to encode manually
        return pdf_output
    except Exception as e:
        logging.error(f"Error generating PDF output bytes: {e}")
        return b"Error generating PDF output"

# Replace the old generate_pdf_report function in your app.py with this one.
# --- Main Streamlit App Logic ---
def main():
    st.set_page_config(page_title="AI Study Abroad Counselor", layout="wide")
    st.title("AI Study Abroad Counselor - Demo")
    st.markdown("Utilizing FAISS Vector Store via S3 for RAG.")

    # --- Initialize Session State ---
    if "current_user_data" not in st.session_state:
        st.session_state["current_user_data"] = None
    if "current_shortlists" not in st.session_state:
        st.session_state["current_shortlists"] = None
    if "generated_report_text" not in st.session_state:
        st.session_state["generated_report_text"] = ""
    if "rag_answer" not in st.session_state:
        st.session_state["rag_answer"] = ""

    # --- Sidebar for User Input ---
    with st.sidebar:
        st.header("User Selection")
        default_phone = os.getenv("DEFAULT_PHONE", "+919999999999")
        phone_number = st.text_input("Enter Phone (with country code)", value=default_phone)

        if st.button("Load User Data"):
            if not phone_number:
                st.warning("Please enter a phone number.")
            else:
                with st.spinner("Fetching user data..."):
                    try:
                        user_data = get_user_by_phone(phone_number)
                        if not user_data:
                            st.error("No user found with that phone.")
                            st.session_state["current_user_data"] = None
                            st.session_state["current_shortlists"] = None
                        else:
                            st.session_state["current_user_data"] = user_data
                            user_id = user_data.get("id") or user_data.get("userid")
                            if user_id:
                                shortlists = get_shortlists_by_user(user_id)
                                st.session_state["current_shortlists"] = shortlists
                            else:
                                st.warning("User ID not found, cannot fetch shortlists.")
                                st.session_state["current_shortlists"] = None
                            st.success("User data loaded!")
                    except Exception as e:
                        st.error(f"Error loading data: {e}")
                        logging.error(f"Database connection/query error: {e}", exc_info=True)
                        st.session_state["current_user_data"] = None
                        st.session_state["current_shortlists"] = None

    # --- Main App Area ---
    if st.session_state.get("current_user_data"):
        user_data = st.session_state["current_user_data"]

        # --- Display User Info ---
        st.subheader("Loaded User Information")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Name:** {user_data.get('username', 'N/A').strip()}")
            st.markdown(f"**Email:** {user_data.get('usermail', 'N/A')}")
        with col2:
            st.markdown(f"**Target Country:** {user_data.get('DreamCountry', 'N/A')}")
            st.markdown(f"**Contact:** {user_data.get('phone', 'N/A')}")

        if st.session_state.get("current_shortlists"):
            with st.expander("Show/Hide Shortlists"):
                 st.write("Shortlists:")
                 st.json(st.session_state["current_shortlists"], expanded=False)
        else:
            st.info("No shortlists found or loaded for this user.")

        st.divider()

        # --- Generate Use Case Messages ---
        st.subheader("Generate Use Case Messages")
        if st.button("Generate Messages"):
            with st.spinner("Generating messages..."):
                try:
                    messages = generate_all_use_cases(user_data)
                    st.success("Generated Messages:")
                    for i, msg in enumerate(messages, start=1):
                        st.markdown(f"**{i}.** {msg}")
                except Exception as e:
                    st.error(f"Error generating messages: {e}")
                    logging.error(f"Usecase generation error: {e}", exc_info=True)

        st.divider()

        # --- RAG Query Section ---
        st.subheader("AI Research / Ask a Question")
        st.markdown("Ask the AI counselor about study abroad topics based on the knowledge base.")

        top_k = st.number_input("Number of relevant documents to retrieve (Top K)", min_value=1, max_value=10, value=3, key="rag_top_k")
        user_query = st.text_area("Your question:", key="rag_query", height=100)

        if st.button("Get Answer", key="rag_button"):
            if not user_query:
                st.warning("Please enter a question.")
            else:
                with st.spinner("Thinking..."):
                    try:
                        # Call the RAG function - it uses env vars internally via rag_util.py
                        logging.info(f"Calling RAG with query: '{user_query}', top_k: {top_k}")
                        answer = do_rag_query(
                            user_query=user_query,
                            user_profile=user_data,
                            top_k=top_k
                        )
                        st.session_state["rag_answer"] = answer
                    except Exception as e:
                        st.error(f"Error getting answer: {e}")
                        # Log the full error for debugging
                        logging.error(f"RAG query error in app.py: {e}", exc_info=True)
                        st.session_state["rag_answer"] = f"Sorry, an error occurred while getting the answer. Details: {e}"


        if st.session_state["rag_answer"]:
             st.markdown("**AI Counselor's Answer:**")
             st.info(st.session_state["rag_answer"])

        st.divider()

        # --- Personalized Report Section --- (UPDATED LOGIC) ---
        st.subheader("Generate Personalized Report")
        extra_notes = st.text_area(
            "Add any extra notes/information for the report:",
            key="report_notes",
            height=150,
            help="These notes will be appended to the report generation prompt."
        )

        if st.button("Generate Report Preview", key="report_button"):
            profile = {
                "username": user_data.get("username", "N/A").strip(),
                "usermail": user_data.get("usermail", "N/A"),
                "DreamCountry": user_data.get("DreamCountry", "N/A"),
                "phone": user_data.get("phone", "N/A")
            }
            username = profile['username']
            dream_country_report = profile.get("DreamCountry", "the target country")
            if not dream_country_report or dream_country_report == 'N/A':
                st.warning("Target country ('DreamCountry') not specified for the user. Report generation might be less effective.")
                dream_country_report = "the target country" # Provide a fallback

            # Define queries for each report section
            report_sections = {
                "Career Outlook": f"Discuss potential career options, typical salaries, and job market trends relevant for someone studying abroad in {dream_country_report}.",
                "Course Specializations": f"Detail various relevant course specializations available for study in {dream_country_report}. Mention specific course examples if possible.",
                "Potential Colleges": f"List 6-7 suitable colleges or universities in {dream_country_report}. Include brief notes on admission requirements and typical application deadlines if available.",
                "Visa Information": f"Summarize the student visa policies, requirements, and application processes for studying in {dream_country_report}.",
                "Permanent Residency Pathway": f"Briefly outline the common routes or possibilities for obtaining permanent residency in {dream_country_report} after completing studies.",
                "Cost Estimation": f"Provide an estimated range for the total cost of education in {dream_country_report}, considering both tuition fees and living expenses.",
                "Scholarship Opportunities": f"Mention types of scholarships available for international students studying in {dream_country_report} and suggest where to look for them."
            }

            # Include extra notes if provided
            if extra_notes:
                for key in report_sections:
                     report_sections[key] += f"\n\nAdditional context or notes to consider: {extra_notes}"

            report_texts = {}
            report_top_k = 5 # Documents to retrieve per section query
            generation_successful = True

            with st.spinner("Generating report content section by section... This may take a few minutes."):
                progress_bar = st.progress(0)
                total_sections = len(report_sections)

                for i, (section_title, section_query) in enumerate(report_sections.items()):
                    st.write(f"Generating section: {section_title}...") # Show progress in UI
                    logging.info(f"Calling RAG for report section '{section_title}', top_k: {report_top_k}")
                    try:
                        section_answer = do_rag_query(
                            user_query=section_query,
                            user_profile=profile, # Pass user profile for context
                            top_k=report_top_k
                        )
                        report_texts[section_title] = section_answer
                        logging.info(f"Successfully generated section: {section_title}")
                    except Exception as e:
                        error_message = f"Error generating section '{section_title}': {e}"
                        st.error(error_message)
                        logging.error(f"Report generation RAG error in app.py for section '{section_title}': {e}", exc_info=True)
                        report_texts[section_title] = f"Could not generate this section due to an error."
                        generation_successful = False # Mark as failed but continue

                    # Update progress bar
                    progress_bar.progress((i + 1) / total_sections)

            # Combine the generated sections into the final report
            final_report_text = f"Personalized Study Abroad Report for {username}\n"
            final_report_text += f"Target Country: {dream_country_report}\n"
            final_report_text += "=" * 40 + "\n\n"

            for title, text in report_texts.items():
                final_report_text += f"## {title}\n\n"
                final_report_text += f"{text}\n\n"
                final_report_text += "---\n\n" # Add a separator

            st.session_state["generated_report_text"] = final_report_text
            if generation_successful:
                st.success("Report content generated!")
            else:
                st.warning("Report generated, but some sections may have encountered errors.")


        # --- Display Report Preview and Download ---
        if st.session_state["generated_report_text"]:
            st.subheader("Report Preview")
            # Use markdown=True in disabled text_area if you want markdown rendering in preview
            st.text_area("Preview:", value=st.session_state["generated_report_text"], height=400, key="report_preview_area", disabled=True) 

            # Check for specific error messages before allowing download
            if "Error generating report content" not in st.session_state["generated_report_text"] and \
               "Could not generate this section" not in st.session_state["generated_report_text"]:
                try:
                    pdf_bytes = generate_pdf_report(st.session_state["generated_report_text"])
                    # Sanitize username for filename
                    safe_username = "".join(c if c.isalnum() else "_" for c in user_data.get('username', 'user'))
                    st.download_button(
                        label="Download Report as PDF",
                        data=pdf_bytes,
                        file_name=f"{safe_username}_study_abroad_report.pdf", 
                        mime="application/pdf",
                        key="pdf_download"
                    )
                except Exception as e:
                     st.error(f"Error preparing PDF for download: {e}")
                     logging.error(f"PDF generation/download button error: {e}", exc_info=True)

    else:
        st.info("⬅️ Please enter a phone number and click 'Load User Data' in the sidebar to begin.")


if __name__ == "__main__":
    main()