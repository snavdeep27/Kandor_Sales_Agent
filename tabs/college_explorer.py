# tabs/college_explorer.py

import streamlit as st
import logging
import datetime
from dateutil.relativedelta import relativedelta
from typing import Optional, Dict, Any, List # Added List

# --- Import Core Logic ---
try:
    from db_connection import (
        get_users_by_university_interaction,
        get_latest_shortlist_data_and_uni_name, # Use the updated function
        get_user_by_id
    )
    from rag_utils import do_rag_query, VECTOR_STORE_IDS
except ImportError as e:
    st.error(f"(College Explorer Tab) Failed to import required modules: {e}. Check file structure.")
    logging.error(f"(College Explorer Tab) Module import error: {e}", exc_info=True)
    st.write("Error: Core modules not found. Tab cannot function.")
    st.stop() # Stop if core DB/RAG utils can't be loaded


# --- Helper Function for Message Generation ---
# (This function definition remains unchanged from the previous correct version)
def generate_college_explorer_messages(
        user_profile: dict, target_university_name: str, target_course_name: str,
        target_university_id: Optional[str], query_profile_data: dict
    ) -> list[str]:
    """Generates messages focused on the TARGET university and course selected by the user."""
    messages = []
    if not user_profile or not target_university_name: return ["Error: Missing user profile or target university data."]
    username = user_profile.get('username', 'there'); user_id = user_profile.get('userid')
    shortlist_degree = query_profile_data.get('degreeTitle', 'your field')
    shortlist_countries = query_profile_data.get('countries', [])
    shortlist_country = shortlist_countries[0] if shortlist_countries else 'your target country'
    logging.info(f"Generating messages for User: {user_id} ({username}), Target Uni: {target_university_name}, Target Course: {target_course_name}, Target Degree: {shortlist_degree}")
    uni_details = {}
    try:
        uni_query = f"Provide details about {target_university_name}"
        if target_university_id: uni_query += f" (ID: {target_university_id})"
        uni_query += f", including general admission requirements, estimated fees (annual tuition & living costs if possible), location highlights, and student acceptance rate if available. Mention details relevant to {shortlist_degree} programs if possible."
        uni_info_raw = do_rag_query(user_query=uni_query, user_profile=user_profile, top_k=3)
        if uni_info_raw and "not available" not in uni_info_raw.lower() and "error" not in uni_info_raw.lower():
            uni_details['raw'] = uni_info_raw
            lines = uni_info_raw.split('\n')
            for line in lines:
                if "admission" in line.lower(): uni_details['admissions'] = line
                if "fee" in line.lower() or "tuition" in line.lower() or "cost" in line.lower(): uni_details['fees'] = line
                if "accept" in line.lower() and "rate" in line.lower(): uni_details['acceptance'] = line
                if "locat" in line.lower() or "city" in line.lower(): uni_details['location'] = line
        else: logging.warning(f"RAG query for university details ({target_university_name}) returned limited info or failed.")
    except Exception as e: logging.error(f"RAG Error fetching details for {target_university_name}: {e}")
    # --- Message Templates ---
    messages.append(f"Hi {username}, saw you were looking into {target_university_name}! It's a popular choice, especially for programs like '{target_course_name}'. How can we assist further?")
    messages.append(f"Thinking about the '{target_course_name}' program (or similar {shortlist_degree} fields) at {target_university_name}? Let's explore if it's the right fit for your goals in {shortlist_country}.")
    if uni_details.get('admissions'): messages.append(f"Admission insight for {target_university_name}: {uni_details['admissions'][:250]}...")
    elif uni_details.get('acceptance'): messages.append(f"Regarding {target_university_name}'s selectivity: {uni_details['acceptance'][:250]}...")
    else: messages.append(f"We can help find specific admission requirements for '{target_course_name}' at {target_university_name}.")
    if uni_details.get('fees'): messages.append(f"Estimated Costs at {target_university_name}: {uni_details['fees'][:250]}... Does this work with your financial plan?")
    else: messages.append(f"Let's research the budget needed for the '{target_course_name}' program at {target_university_name}.")
    if uni_details.get('location'): messages.append(f"Living near {target_university_name}: {uni_details['location'][:250]}... Think about the campus and city environment!")
    else: messages.append(f"Researching the campus location and city life around {target_university_name} is important.")
    messages.append(f"What specifically interests you most about '{target_course_name}' at {target_university_name}? Faculty, research, modules?")
    # Need top_courses for this message, retrieve from shortlist_data if needed, or adapt message
    # Example: messages.append(f"How does {target_university_name} compare to other options you considered for {shortlist_degree}?")
    messages.append(f"What makes {target_university_name} stand out for you compared to other options for {shortlist_degree}?") # Adapted message
    if uni_details.get('raw'): messages.append(f"More details we found on {target_university_name}: {uni_details['raw'][:300]}...")
    else: messages.append(f"Want a more detailed report on {target_university_name}, focusing on the {shortlist_degree} department?")
    messages.append(f"Ready to move forward with {target_university_name}? Kandor can guide you through the application process for '{target_course_name}'.")
    messages.append(f"Focusing on {target_university_name} is a big step! What questions do you have about applying or preparing?")
    # Fill remaining messages
    while len(messages) < 10: messages.append(f"Let us know if you have more questions about {target_university_name} or '{target_course_name}'!")
    return messages[:10]


# --- Main Rendering Function for the Tab ---
def render():
    st.header("College Explorer Follow-ups")
    st.markdown("Identify users who interacted with universities recently, view their latest shortlist, and generate targeted messages.")

    # --- Date Selection ---
    st.subheader("Select Interaction Date")
    today = datetime.date.today()
    thirty_days_ago = today - relativedelta(days=29)
    date_range = [thirty_days_ago + datetime.timedelta(days=x) for x in range((today - thirty_days_ago).days + 1)]
    date_options = {d.strftime("%Y-%m-%d (%A)"): d for d in sorted(date_range, reverse=True)}
    yesterday_str = (today - relativedelta(days=1)).strftime("%Y-%m-%d (%A)")
    default_index = 0
    if yesterday_str in date_options: default_index = list(date_options.keys()).index(yesterday_str)

    selected_date_str = st.selectbox(
        "Select Date:", options=list(date_options.keys()),
        key="college_explorer_date_selector", index=default_index
    )
    selected_date_obj = date_options[selected_date_str]

    # --- Initialize State ---
    if "college_explorer_interactions" not in st.session_state: st.session_state["college_explorer_interactions"] = {}
    if "college_explorer_selected_interaction_index" not in st.session_state: st.session_state["college_explorer_selected_interaction_index"] = None
    if "college_explorer_fetched_data" not in st.session_state: st.session_state["college_explorer_fetched_data"] = {}
    if "college_explorer_target_selection" not in st.session_state: st.session_state["college_explorer_target_selection"] = None
    if "college_explorer_generated_messages" not in st.session_state: st.session_state["college_explorer_generated_messages"] = {}
    if "college_explorer_loaded_date" not in st.session_state: st.session_state["college_explorer_loaded_date"] = None

    # --- Fetch Interactions Button ---
    if st.button(f"Find University Interactions for {selected_date_str}", key="college_explorer_find_button"):
        st.session_state["college_explorer_selected_interaction_index"] = None
        st.session_state["college_explorer_target_selection"] = None
        st.session_state["college_explorer_fetched_data"] = {}
        st.session_state["college_explorer_generated_messages"] = {}
        st.session_state["college_explorer_loaded_date"] = selected_date_str

        with st.spinner(f"Searching for university interactions on {selected_date_str}..."):
            try:
                interactions = get_users_by_university_interaction(selected_date_obj)
                st.session_state.setdefault("college_explorer_interactions", {})[selected_date_str] = interactions
                if not interactions: st.info(f"No relevant university interactions found for {selected_date_str}.")
            except Exception as e:
                st.error(f"Database error fetching interactions: {e}")
                logging.error(f"Error calling get_users_by_university_interaction for {selected_date_obj}: {e}", exc_info=True)
                st.session_state.setdefault("college_explorer_interactions", {})[selected_date_str] = []

    # --- Display Interactions and Message Area ---
    loaded_date = st.session_state.get("college_explorer_loaded_date")
    interactions_list = []
    if loaded_date == selected_date_str:
        interactions_list = st.session_state.get("college_explorer_interactions", {}).get(selected_date_str, [])

    if loaded_date == selected_date_str:
        if interactions_list:
            st.subheader(f"University Interactions from {selected_date_str}")
            col_interactions, col_messages_area = st.columns([2, 3])

            with col_interactions:
                st.markdown("**Select Interaction:**")
                # --- Use Index for Selection ---
                interaction_options_map = {} # Maps display name to index
                display_options_list = [] # Ordered list of display names for radio options
                for i, interaction in enumerate(interactions_list):
                    # Display Uni ID initially, name/course comes after selection
                    display_name = f"{interaction.get('username', 'N/A')} ({interaction.get('phone', 'N/A')}) -> Uni ID: {interaction.get('university_id')} @ {interaction.get('interaction_time', '--:--')}"
                    interaction_options_map[display_name] = i
                    display_options_list.append(display_name)

                # --- CORRECTED Callback ---
                def handle_interaction_selection_change():
                    selected_display_name = st.session_state.college_explorer_interaction_selector_radio # Get selected display name string
                    new_selected_index = None
                    if selected_display_name in display_options_list:
                        try:
                            new_selected_index = display_options_list.index(selected_display_name) # Find integer index
                        except ValueError:
                            new_selected_index = None
                            logging.warning(f"Selected display name '{selected_display_name}' not found in options list.")

                    current_index = st.session_state.get("college_explorer_selected_interaction_index")
                    if new_selected_index is not None and current_index != new_selected_index:
                        st.session_state["college_explorer_selected_interaction_index"] = new_selected_index # Store INTEGER index
                        st.session_state["college_explorer_target_selection"] = None # Reset target uni selection
                        # Clear potentially outdated fetched data/messages for the previous selection (optional)
                        # cache_key_to_clear = f"{current_index}_{loaded_date}" # Example if needed
                        # st.session_state.get("college_explorer_fetched_data", {}).pop(cache_key_to_clear, None)
                        # Consider clearing relevant message cache entries too

                # --- Corrected Radio Button Usage ---
                st.radio(
                    "Select User/University Interaction:",
                    options=display_options_list, # Use the ordered list of strings
                    format_func=lambda x: x, # Display the string option
                    key="college_explorer_interaction_selector_radio", # Widget's state key
                    # Provide the *integer* index from session state
                    index=st.session_state.get("college_explorer_selected_interaction_index"),
                    on_change=handle_interaction_selection_change
                )

            # --- Right Column: Display Shortlist, Select Target, Generate/Show Messages ---
            with col_messages_area:
                selected_index = st.session_state.get("college_explorer_selected_interaction_index")

                if selected_index is not None and selected_index < len(interactions_list):
                    selected_interaction = interactions_list[selected_index]
                    user_id = selected_interaction.get('user_id')
                    uni_id = selected_interaction.get('university_id') # The ID from event_logs
                    cache_key = f"{selected_index}_{selected_date_str}" # Cache key based on index/date

                    # --- Step 1: Fetch (or get from cache) Profile & Shortlist Data ---
                    fetched_data = st.session_state.get("college_explorer_fetched_data", {}).get(cache_key)

                    if not fetched_data:
                        # ... (Fetching logic remains the same as previous correct version) ...
                        st.info("Fetching user profile and shortlist data...")
                        with st.spinner("Loading details..."):
                            user_profile = None; shortlist_data = None; uni_name = f"ID: {uni_id}"; course_name = "N/A"
                            try: user_profile = get_user_by_id(user_id)
                            except Exception as e: logging.error(f"Failed fetch profile {user_id}: {e}")
                            try:
                                shortlist_data = get_latest_shortlist_data_and_uni_name(user_id, selected_date_obj, uni_id)
                                if shortlist_data:
                                    uni_name = shortlist_data.get('interacted_university_name', uni_name)
                                    course_name = shortlist_data.get('interacted_course_name', course_name)
                            except Exception as e: logging.error(f"Failed fetch shortlist {user_id}/{selected_date_obj}: {e}")
                            fetched_data = {'user_profile': user_profile, 'shortlist_data': shortlist_data, 'interacted_university_name': uni_name, 'interacted_course_name': course_name}
                            st.session_state.setdefault("college_explorer_fetched_data", {})[cache_key] = fetched_data
                            st.rerun()

                    else: # Data is fetched/cached
                        user_profile = fetched_data.get('user_profile')
                        shortlist_data = fetched_data.get('shortlist_data')

                        if not user_profile or not shortlist_data:
                            st.warning("Could not load necessary user profile or shortlist data for this interaction.")
                        else:
                            # --- Step 2: Display Top 5 Shortlist Options ---
                            st.subheader("Top Shortlist Options (from Interaction Date):")
                            top_courses = shortlist_data.get('top_shortlisted_courses', [])

                            if not top_courses or (len(top_courses)==1 and "Error" in top_courses[0]['name']):
                                 st.warning("No shortlist courses found or shortlist failed to parse.")
                            else:
                                 # --- Step 3: Select Target University/Course ---
                                 shortlist_display_options = {}
                                 for idx, course_info in enumerate(top_courses):
                                     uni_name = course_info.get('university', 'N/A')
                                     course_name = course_info.get('name', 'N/A')
                                     # Try to get uni_id if present in the course_info dict
                                     uni_id_from_shortlist = course_info.get('university_id') # Assumes it might exist here

                                     display_text = f"{idx+1}. {uni_name} - {course_name}"
                                     shortlist_display_options[display_text] = {
                                         "university_name": uni_name,
                                         "course_name": course_name,
                                         "university_id": uni_id_from_shortlist
                                     }

                                 target_selector_key = f"college_explorer_target_selector_{cache_key}"
                                 # Use st.session_state.get to check existing selection for persistence
                                 current_target_selection_data = st.session_state.get("college_explorer_target_selection")
                                 current_target_display = None
                                 if current_target_selection_data:
                                     # Find the display text matching the stored selection data
                                     for dt, data in shortlist_display_options.items():
                                         if data == current_target_selection_data:
                                             current_target_display = dt
                                             break

                                 selected_target_display = st.selectbox(
                                     "Choose a shortlisted option to generate messages for:",
                                     options=["-- Select --"] + list(shortlist_display_options.keys()),
                                     # Set index based on current selection if it exists in options
                                     index= (list(shortlist_display_options.keys()).index(current_target_display) + 1) if current_target_display else 0,
                                     key=target_selector_key
                                 )

                                 # --- Step 4: Store Selection and Show Generate Button ---
                                 if selected_target_display != "-- Select --":
                                     selected_target_data = shortlist_display_options[selected_target_display]
                                     # Store the choice if it changed
                                     if st.session_state.get("college_explorer_target_selection") != selected_target_data:
                                        st.session_state["college_explorer_target_selection"] = selected_target_data
                                        # Clear messages when target changes
                                        message_cache_key = f"{cache_key}_{selected_target_display}"
                                        st.session_state.get("college_explorer_generated_messages", {}).pop(message_cache_key, None)


                                     # Display Generate button only after a target is selected
                                     st.markdown("---")
                                     generate_button_key = f"college_generate_btn_{cache_key}_{selected_target_display}" # Unique button key
                                     if st.button("Generate Messages", key=generate_button_key):
                                         # --- Step 5: Generate Messages ---
                                         target_uni_name = selected_target_data.get("university_name")
                                         target_course_name = selected_target_data.get("course_name")
                                         target_uni_id = selected_target_data.get("university_id")
                                         query_profile_data = shortlist_data.get('query_profile_data', {})

                                         if target_uni_name and target_course_name:
                                             with st.spinner("AI is crafting messages..."):
                                                 try:
                                                     messages = generate_college_explorer_messages(
                                                         user_profile=user_profile,
                                                         target_university_name=target_uni_name,
                                                         target_course_name=target_course_name,
                                                         target_university_id=target_uni_id,
                                                         query_profile_data=query_profile_data
                                                     )
                                                     message_cache_key = f"{cache_key}_{selected_target_display}"
                                                     st.session_state.setdefault("college_explorer_generated_messages", {})[message_cache_key] = messages
                                                 except Exception as e:
                                                     st.error(f"Error during message generation: {e}")
                                                     logging.error(f"Msg gen error for target {target_uni_name}: {e}", exc_info=True)
                                                     # Store error message to display
                                                     message_cache_key = f"{cache_key}_{selected_target_display}"
                                                     st.session_state.setdefault("college_explorer_generated_messages", {})[message_cache_key] = [f"Error generating: {e}"]

                                         else:
                                              st.warning("Invalid target selection data.")

                                 # --- Step 6: Display Generated Messages ---
                                 selected_target = st.session_state.get("college_explorer_target_selection")
                                 # Check if the currently selected display option matches the stored target data
                                 if selected_target and selected_target_display != "-- Select --" and selected_target == shortlist_display_options[selected_target_display]:
                                      message_cache_key = f"{cache_key}_{selected_target_display}"
                                      generated_messages = st.session_state.get("college_explorer_generated_messages", {}).get(message_cache_key)

                                      if generated_messages:
                                           st.markdown("---")
                                           st.subheader("Generated Messages:")
                                           # Check if the first message indicates an error
                                           if isinstance(generated_messages, list) and generated_messages and "Error" in generated_messages[0]:
                                                st.error(generated_messages[0])
                                           else:
                                                st.success(f"Showing {len(generated_messages)} messages for **{selected_target.get('university_name')} - {selected_target.get('course_name')}**:")
                                                for i, msg in enumerate(generated_messages, 1):
                                                    msg_display_key = f"college_msg_{message_cache_key}_{i}" # Unique key
                                                    st.text_area(f"Message {i}", value=msg, height=110, key=msg_display_key, help="You can copy this message.")


                else: # No interaction selected
                    st.info("Select a user/university interaction from the list on the left.")

        # Handle case where interaction list is empty after fetch for the selected date
        elif loaded_date == selected_date_str and not interactions_list:
            # Message shown inside button logic if fetch returned empty
             pass

    # Handle case where button hasn't been clicked for the selected date yet
    elif loaded_date != selected_date_str:
         st.info(f"Click the button above to find interactions for {selected_date_str}.")