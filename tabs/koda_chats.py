# tabs/koda_chats.py

import streamlit as st
import logging
import datetime
from dateutil.relativedelta import relativedelta
import json
from typing import Optional, Dict, Any, List

# --- Import Core Logic ---
try:
    # Import NEW DB functions
    from db_connection import get_combined_chat_users_on_date, get_ielts_user_profile, get_latest_shortlist_details
    # Use a potentially more capable model for summarization
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    import os
except ImportError as e:
    st.error(f"(Koda Chats Tab) Failed to import required modules: {e}. Check file structure.")
    logging.error(f"(Koda Chats Tab) Module import error: {e}", exc_info=True)
    st.write("Error: Core modules not found. Tab cannot function.")
    st.stop()

# --- Helper Functions ---

# Intent classification (remains the same)
def classify_intent(conv_history_str: Optional[str]) -> str:
    if not conv_history_str: return "Unknown"
    text = conv_history_str.lower()
    ielts_keywords = ["ielts", "band", "score", "test", "exam", "listening", "reading", "writing", "speaking", "english proficiency"]
    study_abroad_keywords = ["university", "college", "course", "country", "visa", "apply", "admission", "study abroad", "program", "korea", "usa", "canada", "uk", "australia", "germany", "shortlist"]
    ielts_score = sum(keyword in text for keyword in ielts_keywords)
    study_abroad_score = sum(keyword in text for keyword in study_abroad_keywords)
    if ielts_score > study_abroad_score and ielts_score > 0: return "IELTS"
    elif study_abroad_score > 0: return "Study Abroad"
    else: return "General/Unknown"

# V2 Summarization function - Improved Prompt & Model
@st.cache_data(show_spinner=False) # Cache the summary result
def get_chat_summary_v2(user_messages: str, model_name: str = "gpt-4o") -> str: # Use gpt-4o
    """Generates a refined summary focusing on user's questions/goals using OpenAI."""
    if not user_messages:
        return "No user messages found in the conversation history."
    logging.info(f"Requesting summary using model: {model_name}")
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key: return "Error: OPENAI_API_KEY not configured."

        llm = ChatOpenAI(model_name=model_name, temperature=0.1, openai_api_key=api_key, max_tokens=200) # Increase tokens slightly

        # Refined prompt
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", "You are an expert assistant analyzing chat logs between a student and an AI counselor (Koda). Your task is to carefully read ONLY the messages from the 'user' role provided below and identify the user's primary questions, goals, problems, or points of confusion regarding their study abroad journey or IELTS preparation. Ignore the assistant's responses. Synthesize these user points into a concise 2-4 sentence summary. Focus on *what the user was trying to achieve or figure out*. Do not just list topics."),
            ("human", "User Messages:\n---\n{user_input}\n---\nSummary of User's Key Points:")
        ])

        chain = prompt_template | llm | StrOutputParser()
        max_input_length = 10000 # Allow longer input for potentially combined history
        truncated_input = user_messages[:max_input_length] + ("..." if len(user_messages) > max_input_length else "")
        summary = chain.invoke({"user_input": truncated_input})
        return summary if summary else "Could not generate summary."

    except Exception as e:
        logging.error(f"Error during chat summarization V2: {e}", exc_info=True)
        return f"Error generating summary: {e}"

# --- Main Rendering Function for the Tab ---
def render():
    st.header("Koda Chat Interactions Review")
    st.markdown("Review user interactions from Koda chats and shortlists, view profiles, and understand user intent.")

    # --- Date Selection ---
    st.subheader("Select Activity Date")
    today = datetime.date.today()
    thirty_days_ago = today - relativedelta(days=29)
    date_range = [thirty_days_ago + datetime.timedelta(days=x) for x in range((today - thirty_days_ago).days + 1)]
    date_options = {d.strftime("%Y-%m-%d (%A)"): d for d in sorted(date_range, reverse=True)}
    yesterday_str = (today - relativedelta(days=1)).strftime("%Y-%m-%d (%A)")
    default_index = 0
    if yesterday_str in date_options: default_index = list(date_options.keys()).index(yesterday_str)

    selected_date_str = st.selectbox(
        "Select Date:", options=list(date_options.keys()),
        key="koda_chats_date_selector", index=default_index
    )
    selected_date_obj = date_options[selected_date_str]

    # --- Fetch Combined Chat Users Button ---
    if st.button(f"Find User Activity for {selected_date_str}", key="koda_chats_find_button"):
        # Reset state for new date
        st.session_state["koda_chats_selected_user_index"] = None
        st.session_state["koda_chats_ielts_profile"] = {}
        st.session_state["koda_chats_shortlist_profile"] = {}
        st.session_state["koda_chats_summary"] = {}
        st.session_state["koda_chats_loaded_date"] = selected_date_str

        with st.spinner(f"Searching for user activity on {selected_date_str}..."):
            try:
                # Call the NEW combined function
                combined_users = get_combined_chat_users_on_date(selected_date_obj)
                # Process users to add intent and time string
                processed_users = []
                for user_data in combined_users:
                    user_data['intent'] = classify_intent(user_data.get('latest_conv_history_str'))
                    ts = user_data.get('overall_latest_ts')
                    user_data['interaction_time'] = ts.strftime("%H:%M") if isinstance(ts, datetime.datetime) else "N/A"
                    processed_users.append(user_data)

                st.session_state.setdefault("koda_chats_user_list", {})[selected_date_str] = processed_users
                if not processed_users: st.info(f"No user activity found in Koda chats or Shortlists for {selected_date_str}.")

            except Exception as e:
                st.error(f"Database error fetching combined user activity: {e}")
                logging.error(f"Error calling get_combined_chat_users_on_date for {selected_date_obj}: {e}", exc_info=True)
                st.session_state.setdefault("koda_chats_user_list", {})[selected_date_str] = []

    # --- Display User List and Details Area ---
    loaded_date = st.session_state.get("koda_chats_loaded_date")
    chat_users_list = []
    if loaded_date == selected_date_str:
        chat_users_list = st.session_state.get("koda_chats_user_list", {}).get(selected_date_str, [])

    if loaded_date == selected_date_str:
        if chat_users_list:
            st.subheader(f"User Activity from {selected_date_str}")
            col_users, col_details = st.columns([1, 2])

            with col_users:
                st.markdown("**Select User:**")
                user_options = {}
                display_list = []
                for i, user_data in enumerate(chat_users_list):
                    display_name = f"{user_data.get('username', 'N/A')} ({user_data.get('phone', 'N/A')}) - [{user_data.get('intent', 'N/A')}] @ {user_data.get('interaction_time', '--:--')}"
                    user_options[display_name] = i
                    display_list.append(display_name)

                def handle_koda_user_selection_change():
                    selected_display_name = st.session_state.koda_chats_user_selector_radio
                    new_selected_index = None
                    if selected_display_name in display_list:
                        try: new_selected_index = display_list.index(selected_display_name)
                        except ValueError: new_selected_index = None
                    if new_selected_index is not None and st.session_state.get("koda_chats_selected_user_index") != new_selected_index:
                        st.session_state["koda_chats_selected_user_index"] = new_selected_index

                st.radio( "Users with Activity:", options=display_list,
                    key="koda_chats_user_selector_radio",
                    index=st.session_state.get("koda_chats_selected_user_index"),
                    on_change=handle_koda_user_selection_change
                )

            # --- Right Column: Summary & Profiles ---
            with col_details:
                selected_index = st.session_state.get("koda_chats_selected_user_index")

                if selected_index is not None and selected_index < len(chat_users_list):
                    selected_user_data = chat_users_list[selected_index]
                    user_id = selected_user_data.get('user_id')
                    cache_key = f"{selected_index}_{loaded_date}" # Cache key

                    st.subheader(f"Details for {selected_user_data.get('username', 'N/A')}")

                    # --- Generate/Display Chat Summary ---
                    summary = st.session_state.get("koda_chats_summary", {}).get(cache_key)
                    if not summary:
                        st.info("Generating chat summary...")
                        with st.spinner("AI is summarizing the conversation..."):
                            conv_history_str = selected_user_data.get('latest_conv_history_str', '{}')
                            user_messages_text = ""
                            try:
                                conv_data = json.loads(conv_history_str)
                                history_list = conv_data.get("conv_history", conv_data if isinstance(conv_data, list) else [])
                                user_turns = [turn['content'] for turn in history_list if isinstance(turn, dict) and turn.get('role') == 'user' and turn.get('content')]
                                user_messages_text = "\n---\n".join(user_turns) # Separate turns clearly
                            except Exception as e:
                                user_messages_text = f"Error processing history: {e}"
                                logging.error(f"Error extracting user messages for {user_id}: {e}")

                            if not user_messages_text.strip() or "Error" in user_messages_text:
                                 summary = "Could not extract user messages for summary."
                            else:
                                 # Call V2 summary function
                                 summary = get_chat_summary_v2(user_messages_text)

                            st.session_state.setdefault("koda_chats_summary", {})[cache_key] = summary
                            st.rerun()
                    else:
                        st.markdown("**Chat Summary (User's Input Focus):**")
                        st.markdown(f"> {summary}")
                        st.markdown("---")

                    # --- Fetch/Display IELTS User Profile ---
                    ielts_profile = st.session_state.get("koda_chats_ielts_profile", {}).get(cache_key)
                    if ielts_profile is None: # Check for None specifically, as {} means not found
                         st.info("Fetching IELTS profile details...")
                         with st.spinner("Loading IELTS profile..."):
                              try:
                                   ielts_profile = get_ielts_user_profile(user_id)
                                   st.session_state.setdefault("koda_chats_ielts_profile", {})[cache_key] = ielts_profile if ielts_profile else {"status": "Not Found"}
                                   st.rerun()
                              except Exception as e:
                                   st.error(f"Failed to fetch IELTS profile: {e}")
                                   st.session_state.setdefault("koda_chats_ielts_profile", {})[cache_key] = {"status": "Error"}
                    else: # Display cached IELTS profile
                        st.markdown("**IELTS Profile Data:**")
                        if ielts_profile and ielts_profile.get("status") != "Not Found" and ielts_profile.get("status") != "Error":
                             profile_items = [
                                 f"- **Target Country:** {ielts_profile.get('DreamCountry', 'N/A')}",
                                 f"- **IELTS Status:** {ielts_profile.get('ielts_status', 'N/A')}",
                                 f"- **Study Abroad Status:** {ielts_profile.get('study_abroad_status', 'N/A')}",
                                 f"- **Funds:** {ielts_profile.get('Funds', 'N/A')}",
                                 f"- **Goal:** {ielts_profile.get('goal', 'N/A')}",
                                 f"- **Category/SubCategory:** {ielts_profile.get('category', 'N/A')} / {ielts_profile.get('subCategory', 'N/A')}",
                                 f"- **IELTS Attempts:** {ielts_profile.get('ielts_attempts', 'N/A')}",
                                 f"- **Work Status:** {ielts_profile.get('work_status', 'N/A')}"
                             ]
                             st.markdown("\n".join(profile_items))
                        elif ielts_profile.get("status") == "Not Found":
                             st.markdown("*No specific IELTS profile found.*")
                        else:
                             st.markdown("*Error loading IELTS profile.*")
                        st.markdown("---")


                    # --- Fetch/Display Shortlist Query Profile ---
                    shortlist_profile_data = st.session_state.get("koda_chats_shortlist_profile", {}).get(cache_key)
                    if shortlist_profile_data is None:
                         st.info("Fetching latest shortlist profile data...")
                         with st.spinner("Loading shortlist data..."):
                              try:
                                   latest_shortlist = get_latest_shortlist_details(user_id)
                                   if latest_shortlist and 'query_profile_data' in latest_shortlist:
                                        shortlist_profile_data = latest_shortlist['query_profile_data']
                                   else:
                                        shortlist_profile_data = {"status": "Not Found"}
                                   st.session_state.setdefault("koda_chats_shortlist_profile", {})[cache_key] = shortlist_profile_data
                                   st.rerun()
                              except Exception as e:
                                   st.error(f"Failed to fetch shortlist details: {e}")
                                   logging.error(f"Error fetching shortlist details for {user_id}: {e}")
                                   st.session_state.setdefault("koda_chats_shortlist_profile", {})[cache_key] = {"status": "Error"}
                    else: # Display cached shortlist profile
                        st.markdown("**Latest Shortlist Query Profile:**")
                        if shortlist_profile_data and shortlist_profile_data.get("status") != "Not Found" and shortlist_profile_data.get("status") != "Error":
                             query_items = [f"- **{k.replace('_', ' ').title()}:** {v}" for k, v in shortlist_profile_data.items() if k != 'error' and v]
                             if query_items:
                                 st.markdown("\n".join(query_items))
                             else:
                                 st.markdown("*No details found in latest shortlist query.*")
                        elif shortlist_profile_data.get("status") == "Not Found":
                             st.markdown("*No shortlist record found for this user.*")
                        else:
                             st.markdown("*Error loading shortlist profile.*")

                else:
                    st.info("Select a user from the list on the left to view chat summary and profile details.")

        # Handle case where user list is empty after fetch
        elif loaded_date == selected_date_str and not chat_users_list:
             pass # Message shown inside button logic

    # Handle case where button hasn't been clicked for the selected date yet
    elif loaded_date != selected_date_str:
         st.info(f"Click the button above to find user activity for {selected_date_str}.")