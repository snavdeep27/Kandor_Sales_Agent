import streamlit as st
import logging
import os

# --- Import Core Logic ---
# Assuming these modules are accessible from the main project directory
try:
    from db_connection import get_user_by_phone, get_shortlists_by_user
    from usecase_templates import generate_all_use_cases # If still needed
    from rag_utils import do_rag_query
except ImportError as e:
    st.error(f"(Student Report Tab) Failed to import required modules: {e}. Check file structure.")
    logging.error(f"(Student Report Tab) Module import error: {e}", exc_info=True)
    st.stop()


# --- Main Rendering Function for the Tab ---
def render():
    st.header("Student Profile & AI Report Generation")

    # Sidebar for User Input (Scoped to this tab visually)
    with st.sidebar:
        # Use a unique header or context to differentiate if sidebar is shared visually
        st.header("Load Profile (Report Tab)")
        default_phone = os.getenv("DEFAULT_PHONE", "+919999999999") # Example default
        phone_number = st.text_input("Enter Phone Number:", value=default_phone, key="report_phone_input") # Unique key

        if st.button("Load User Data", key="report_load_user_button"): # Unique key
            if not phone_number: st.warning("Please enter a phone number.")
            else:
                with st.spinner("Fetching user data..."):
                    try:
                        user_data = get_user_by_phone(phone_number)
                        if not user_data:
                            st.error(f"No user found with phone: {phone_number}")
                            st.session_state["current_user_data"] = None
                            st.session_state["current_shortlists"] = None
                        else:
                            st.session_state["current_user_data"] = user_data
                            user_id = user_data.get("id") or user_data.get("userid") or user_data.get("user_id")
                            if user_id:
                                try:
                                    shortlists = get_shortlists_by_user(user_id)
                                    st.session_state["current_shortlists"] = shortlists
                                except Exception as db_e: st.warning(f"Could not fetch shortlists: {db_e}"); st.session_state["current_shortlists"] = None
                            else: st.warning("User ID not found in loaded data."); st.session_state["current_shortlists"] = None
                            st.success("User data loaded successfully!")
                            # Clear previous results when new user is loaded
                            st.session_state["generated_report_text"] = ""
                            st.session_state["rag_answer"] = ""
                    except Exception as e:
                        st.error(f"An error occurred while loading user data: {e}")
                        logging.error(f"DB error during user load: {e}", exc_info=True)
                        st.session_state["current_user_data"] = None
                        st.session_state["current_shortlists"] = None

    # --- Main Area Content ---
    if st.session_state.get("current_user_data"):
        user_data = st.session_state["current_user_data"]

        # Display User Info (Copied from previous version)
        st.subheader("Loaded User Information")
        col1, col2 = st.columns(2)
        with col1: st.markdown(f"**Name:** {user_data.get('username', 'N/A').strip()}")
        with col1: st.markdown(f"**Email:** {user_data.get('usermail', 'N/A')}")
        with col2: st.markdown(f"**Target Country:** {user_data.get('DreamCountry', 'N/A')}")
        with col2: st.markdown(f"**Contact:** {user_data.get('phone', 'N/A')}")
        if st.session_state.get("current_shortlists"):
             with st.expander("Show/Hide Shortlists"): st.write("Shortlists:"); st.table(st.session_state["current_shortlists"])
        else: st.info("No shortlists found for this user.")

        st.divider()

        # Generate Use Case Messages (Optional - keep if useful)
        # st.subheader("Generate Sample Use Case Messages")
        # if st.button("Generate Messages", key="report_gen_usecase_button"):
        #      # ... (use case generation logic) ...

        # RAG Query Section (Copied from previous version)
        st.subheader("AI Research / Ask a Question")
        st.markdown("Ask the AI counselor about study abroad topics.")
        top_k_report = st.number_input("Number of Documents to Retrieve (Top K)", min_value=1, max_value=10, value=5, key="report_rag_top_k")
        user_query_report = st.text_area("Your Question:", key="report_rag_query_input", height=100)
        if st.button("Get Answer", key="report_rag_button"):
             if not user_query_report: st.warning("Please enter a question.")
             else:
                  with st.spinner("Thinking..."):
                       try:
                           logging.info(f"Calling RAG with query: '{user_query_report}', top_k: {top_k_report}")
                           # Ensure user_data (profile) is passed correctly
                           answer = do_rag_query(user_query=user_query_report, user_profile=st.session_state["current_user_data"], top_k=top_k_report)
                           st.session_state["rag_answer"] = answer
                       except Exception as e: st.error(f"RAG system error: {e}"); logging.error(f"RAG query error: {e}", exc_info=True); st.session_state["rag_answer"] = f"Sorry, an error occurred: {e}"
        if st.session_state["rag_answer"]: st.markdown("**AI Counselor's Answer:**"); st.markdown(st.session_state["rag_answer"])

        st.divider()

        # Personalized Report Section (Copied from previous version)
        st.subheader("Generate Personalized Report")
        extra_notes_report = st.text_area(
            "Add extra notes/information for the report:",
            key="report_extra_notes_input", height=150,
            help="These notes will be appended to the report generation queries."
        )

        if st.button("Generate Report Preview", key="report_generate_button"):
            profile_report = st.session_state["current_user_data"] # Use the data from session state
            username_report = profile_report.get('username', 'User').strip() if profile_report.get('username') else 'User'
            dream_country_report = profile_report.get("DreamCountry", "")
            if not dream_country_report or dream_country_report == 'N/A':
                st.warning("Target country info missing. Report context might be limited.")
                dream_country_report = "the user's target country"

            report_sections = { # Use the full definitions
                "Career Outlook": f"Provide a detailed career outlook for professions relevant to the user's profile and potential fields of study in {dream_country_report}. Mention typical salary ranges and job prospects if available.",
                "University Options": f"Suggest 3-5 suitable universities in {dream_country_report} based on the user's profile (e.g., academic background, interests) and potential fields of interest. Include brief reasons for each suggestion, mentioning any specializations or strengths.",
                "Admission Requirements": f"Summarize general academic and language admission requirements (e.g., common tests like IELTS/TOEFL/GRE/GMAT, typical GPA ranges, prerequisite subjects) for universities in {dream_country_report} relevant to the user's likely field of study.",
                "Immigration Pathways": f"Briefly outline potential post-study work visa options or relevant immigration pathways in {dream_country_report} for international students completing studies in fields relevant to the user.",
                "Cost of Living & Tuition": f"Provide a general estimate of the average annual tuition fees and living costs for an international student in {dream_country_report}."
            }
            if extra_notes_report:
                 for key in report_sections: report_sections[key] += f"\n\nAdditional context: {extra_notes_report}"

            report_texts = {}
            report_top_k_gen = 5
            generation_successful = True
            with st.spinner("Generating report sections... This may take a moment."):
                 progress_bar = st.progress(0.0, text="Initializing report generation...")
                 total_sections = len(report_sections)
                 for i, (section_title, section_query) in enumerate(report_sections.items()):
                      progress_text = f"Generating section ({i+1}/{total_sections}): {section_title}..."
                      st.info(progress_text) # Show progress step
                      progress_bar.progress(float(i) / total_sections, text=progress_text) # Update progress bar
                      logging.info(f"Calling RAG for report section '{section_title}', top_k: {report_top_k_gen}")
                      try:
                           # Ensure profile_report (user_data) is passed
                           section_answer = do_rag_query(user_query=section_query, user_profile=profile_report, top_k=report_top_k_gen)
                           report_texts[section_title] = section_answer
                           logging.info(f"Successfully generated section: {section_title}")
                      except Exception as e:
                           error_message = f"Error generating section '{section_title}': {e}"; st.error(error_message); logging.error(f"Report section error '{section_title}': {e}", exc_info=True); report_texts[section_title] = f"Could not generate this section due to an error: {e}"; generation_successful = False
                 progress_bar.progress(1.0, text="Report generation complete.") # Final progress update
                 st.info("Report generation process finished.") # Keep info message for clarity

            # Combine and store results (Copied)
            final_report_text = f"Personalized Study Abroad Report for {username_report}\nTarget Country: {dream_country_report}\n{'=' * 40}\n\n"
            for title, text in report_texts.items(): final_report_text += f"## {title}\n\n{text}\n\n---\n\n"
            st.session_state["generated_report_text"] = final_report_text
            # progress_bar.empty() # Can remove this if final update is sufficient
            if generation_successful: st.success("Report content generated successfully!")
            else: st.warning("Report generated, but one or more sections encountered errors. Please review.")

        # Display Report Preview and Copy Instruction (Copied)
        if st.session_state["generated_report_text"]:
            st.subheader("Report Preview")
            st.text_area("Preview (Scrollable):", value=st.session_state["generated_report_text"], height=400, key="report_preview_area", disabled=False)
            st.caption("You can select and copy the report text from the preview area above.")

    else:
        # Message displayed if no user is loaded yet
        st.info("⬅️ Load a user profile using the sidebar to view and generate reports.")