# tabs/student_followup.py

import streamlit as st
import logging
import datetime
import json 
from typing import Optional, Dict, Any, List
import pandas as pd # Need pandas if using get_all_records effectively

# --- Import Core Logic ---
try:
    # Import gspread utils and necessary DB/RAG functions
    import gspread_utils
    from db_connection import get_user_by_phone, get_ielts_user_profile, get_latest_shortlist_details
    from rag_utils import do_rag_query
except ImportError as e:
    st.error(f"(Student Follow-up Tab) Failed to import required modules: {e}. Check file structure.")
    logging.error(f"(Student Follow-up Tab) Module import error: {e}", exc_info=True)
    st.write("Error: Core modules not found. Tab cannot function.")
    st.stop()

# --- Helper to get combined DB profile ---
# @st.cache_data(ttl=300) # Optional caching
def get_combined_db_profile(phone_number: str) -> Optional[Dict[str, Any]]:
    """Fetches user_latest_state and ielts_profile data."""
    if not phone_number: return None
    logging.info(f"Fetching DB profile for phone: {phone_number}")
    user_state = get_user_by_phone(phone_number)
    if not user_state:
        logging.warning(f"No user found in users_latest_state for phone {phone_number}")
        return None

    user_id = user_state.get('userid')
    ielts_profile = None
    if user_id:
        ielts_profile = get_ielts_user_profile(user_id)

    # Combine profiles (ielts_profile overrides user_state if keys overlap, unlikely here)
    combined = {**(user_state or {}), **(ielts_profile or {})}
    return combined if combined else None


# --- Main Rendering Function for the Tab ---
def render():
    st.header("Student Follow-up CRM")

    # --- Connect to Google Sheet ---
    # Do this once at the top
    client = gspread_utils.get_gspread_client()
    worksheet = None
    if client:
        worksheet = gspread_utils.get_worksheet(client)
    else:
        st.error("Failed to connect to Google Sheets. CRM functionality disabled.")
        return # Stop rendering if no sheet connection

    if not worksheet:
        st.error("Could not open the required Google Worksheet. CRM functionality disabled.")
        return

    # --- Section 1: Today's Activities ---
    st.subheader(f"Activities Due Today ({datetime.date.today().strftime('%Y-%m-%d')})")
    with st.spinner("Loading activities due today..."):
        try:
            due_today_records = gspread_utils.get_followups_due_today(worksheet)
        except Exception as e:
            st.error(f"Error fetching activities: {e}")
            due_today_records = []

    if not due_today_records:
        st.info("No follow-up activities scheduled for today.")
    else:
        st.success(f"Found {len(due_today_records)} activities due today.")
        # Get user details for display
        user_phones_today = [rec.get("PhoneNumber") for rec in due_today_records if rec.get("PhoneNumber")]
        user_profiles_today = {} # phone -> profile dict
        if user_phones_today:
             with st.spinner("Fetching user details for today's activities..."):
                for phone in user_phones_today:
                     if phone not in user_profiles_today: # Avoid refetching
                         profile = get_combined_db_profile(phone)
                         user_profiles_today[phone] = profile if profile else {} # Store profile or empty dict

        # Display activities
        for i, record in enumerate(due_today_records):
            phone = record.get("PhoneNumber")
            profile = user_profiles_today.get(phone, {})
            username = profile.get('username', 'N/A')

            with st.expander(f"{username} ({phone}) - Action: {record.get('Current_Action_Medium', 'N/A')}", expanded=False):
                st.markdown(f"**Plan:** {record.get('Plan_of_Action', 'N/A')}")
                st.markdown(f"**Message/Task:** {record.get('Message', 'N/A')}")
                st.markdown(f"**Next Action Date:** {record.get('Next_Action_Date', 'N/A')}") # Should be today
                st.markdown(f"**Last Updated:** {record.get('Current_Action_Date', 'N/A')}")
                st.markdown(f"**User ID:** {record.get('Userid', 'N/A')}")
                # Add a button to load this user into the editor below?
                if st.button("Load this User in Editor", key=f"load_today_{i}"):
                    st.session_state["followup_loaded_user_phone"] = phone
                    st.session_state["followup_db_profile"] = profile # Store fetched profile
                    # Find the CRM record again (could optimize by passing index)
                    crm_data, crm_index = gspread_utils.find_followup_by_phone(worksheet, phone)
                    st.session_state["followup_crm_record"] = crm_data
                    st.session_state["followup_crm_row_index"] = crm_index
                    st.rerun() # Rerun to populate editor

    st.divider()

    # --- Section 2: Create / Edit Follow-up Plan ---
    st.subheader("Create / Edit Follow-up Plan")

    # Sidebar for loading user
    with st.sidebar:
        st.header("Load Student (Follow-up)")
        phone_input = st.text_input("Enter Phone Number:", key="followup_phone_input", value=st.session_state.get("followup_loaded_user_phone", ""))

        if st.button("Load User Data", key="followup_load_button"):
            if not phone_input:
                st.warning("Please enter a phone number.")
            else:
                st.session_state["followup_loaded_user_phone"] = phone_input
                # Clear previous state
                st.session_state["followup_db_profile"] = None
                st.session_state["followup_crm_record"] = None
                st.session_state["followup_crm_row_index"] = None
                st.session_state["followup_rag_suggestion"] = None
                # Fetch new data
                with st.spinner("Loading user profile and CRM record..."):
                    # Fetch DB Profile
                    profile = get_combined_db_profile(phone_input)
                    st.session_state["followup_db_profile"] = profile

                    # Fetch CRM Record from Sheet
                    crm_data = None
                    crm_index = None
                    # Assign result to a temporary variable first
                    find_result = gspread_utils.find_followup_by_phone(worksheet, phone_input)

                    # Check if the result is not None before unpacking
                    if find_result is not None:
                        crm_data, crm_index = find_result # Unpack only if successful
                        logging.info(f"Found existing CRM record at index {crm_index} for {phone_input}")
                    else:
                        logging.info(f"No existing CRM record found for {phone_input}")
                        # crm_data and crm_index remain None

                    st.session_state["followup_crm_record"] = crm_data
                    st.session_state["followup_crm_row_index"] = crm_index
                    # --- END CORRECTION ---

                    # Now the rest of the logic can safely use crm_data (which might be None)
                    if not profile: st.warning(f"No primary profile found for {phone_input} in the database.")
                    if not crm_data: st.info(f"No existing follow-up plan found for {phone_input}. You can create a new one.")
                    else: st.success(f"Loaded existing follow-up plan for {phone_input}.")

    # --- Display and Edit Area ---
    loaded_phone = st.session_state.get("followup_loaded_user_phone")
    db_profile = st.session_state.get("followup_db_profile")
    crm_record = st.session_state.get("followup_crm_record")
    crm_row_index = st.session_state.get("followup_crm_row_index")

    if loaded_phone:
        st.markdown(f"#### Editing Plan for: {db_profile.get('username', 'N/A') if db_profile else 'N/A'} ({loaded_phone})")
        if not db_profile:
             st.warning("Cannot proceed without basic user profile from database.")
             return # Stop if no DB profile

        # Display key DB profile points for context
        with st.expander("Show/Hide User Profile Context", expanded=False):
             st.markdown(f"**User ID:** {db_profile.get('userid', 'N/A')}")
             st.markdown(f"**Target Country:** {db_profile.get('DreamCountry', 'N/A')}")
             st.markdown(f"**IELTS Status:** {db_profile.get('ielts_status', 'N/A')}")
             st.markdown(f"**Study Abroad Status:** {db_profile.get('study_abroad_status', 'N/A')}")
             st.markdown(f"**Funds:** {db_profile.get('Funds', 'N/A')}")
             st.markdown(f"**Goal:** {db_profile.get('goal', 'N/A')}")
             st.markdown(f"**Category/SubCategory:** {db_profile.get('category', 'N/A')} / {db_profile.get('subCategory', 'N/A')}")
             # Add latest shortlist info? Fetch if needed
             # latest_shortlist = get_latest_shortlist_details(db_profile['userid'])

        # --- Input Fields ---
        plan_default = crm_record.get("Plan_of_Action", "") if crm_record else ""
        next_date_default = crm_record.get("Next_Action_Date") if crm_record else None # Should be date object or None
        medium_default_index = ["WhatsApp", "Email"].index(crm_record["Current_Action_Medium"]) if crm_record and crm_record.get("Current_Action_Medium") in ["WhatsApp", "Email"] else 0
        message_default = crm_record.get("Message", "") if crm_record else ""

        st.markdown("**Plan Strategy**")
        plan_action = st.text_area("Plan of Action (Long term strategy, notes)", value=plan_default, height=200, key="followup_plan")

        # --- RAG Suggestion Button ---
        if st.button("Suggest Plan Strategy (using AI)", key="followup_suggest_plan"):
             with st.spinner("AI is thinking about a strategy..."):
                  # Create prompt for RAG
                  prompt_context = f"User Profile:\n{json.dumps(db_profile, indent=2, default=str)}\n\n"
                  # Add shortlist context if needed (fetch first)
                  # prompt_context += f"Latest Shortlist: {...}\n\n"
                  rag_query = f"Based on the user profile, suggest a multi-step follow-up plan (over several weeks/months) to guide this student towards their study abroad goal. Consider their status (IELTS, Study Abroad), target country/field, and potential budget. Outline key communication points and potential topics."
                  try:
                       suggestion = do_rag_query(user_query=rag_query, user_profile=db_profile, top_k=3) # Pass profile for context
                       st.session_state["followup_rag_suggestion"] = suggestion
                  except Exception as e:
                       st.error(f"Failed to get AI suggestion: {e}")
                       logging.error(f"RAG query failed for plan suggestion: {e}")

        rag_suggestion = st.session_state.get("followup_rag_suggestion")
        if rag_suggestion:
            st.markdown("**AI Suggested Strategy:**")
            st.info(rag_suggestion)
            # Add button to potentially append suggestion to plan?
            # if st.button("Append Suggestion to Plan"):
            #    st.session_state['followup_plan_value'] = plan_action + "\n\n-- AI Suggestion --\n" + rag_suggestion # Needs state management for text_area value

        st.markdown("---")
        st.markdown("**Next Action**")
        col1, col2 = st.columns(2)
        with col1:
            next_action_date = st.date_input("Next Action Date", value=next_date_default, key="followup_next_date")
        with col2:
            action_medium = st.selectbox("Action Medium", ["WhatsApp", "Email"], index=medium_default_index, key="followup_medium")

        message_action = st.text_area("Message / Task for Next Action", value=message_default, height=150, key="followup_message")

        # --- Save Button ---
        if st.button("Save Plan / Update Action", key="followup_save"):
            # Prepare data dictionary matching sheet headers
            save_data = {
                "Userid": db_profile.get("userid"), # Get Userid from DB profile
                "PhoneNumber": loaded_phone,
                "Plan_of_Action": st.session_state.followup_plan, # Get current value from widget state
                "Next_Action_Date": next_action_date, # Already a date object from date_input
                "Current_Action_Medium": action_medium,
                "Message": st.session_state.followup_message,
                # Current_Action_Date is set automatically by update/add functions
            }

            # Validate required fields
            if not save_data["Userid"]:
                 st.error("Cannot save: Userid is missing from the loaded database profile.")
            else:
                 with st.spinner("Saving to Google Sheet..."):
                      success = False
                      if crm_row_index: # Existing record, update it
                           success = gspread_utils.update_followup(worksheet, crm_row_index, save_data)
                      else: # New record, append it
                           success = gspread_utils.add_followup(worksheet, save_data)

                      if success:
                           st.success("Follow-up plan saved successfully!")
                           # Clear suggestion and potentially refresh CRM record state?
                           st.session_state["followup_rag_suggestion"] = None
                           # Refetch CRM record after save
                           crm_data, crm_index = gspread_utils.find_followup_by_phone(worksheet, loaded_phone)
                           st.session_state["followup_crm_record"] = crm_data
                           st.session_state["followup_crm_row_index"] = crm_index
                           st.rerun() # Refresh to show updated state
                      else:
                           st.error("Failed to save follow-up plan to Google Sheet.")


    else: # No user loaded in editor
        st.info("⬅️ Load a user using their phone number in the sidebar to create or edit their follow-up plan.")