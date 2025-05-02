# tabs/shortlist_users.py

import streamlit as st
import logging
import datetime
from dateutil.relativedelta import relativedelta
import json # Might be needed if passing complex data

# --- Import Core Logic ---
try:
    # get_users_shortlisted_on_date now returns the enhanced dictionary
    from db_connection import get_users_shortlisted_on_date
    from rag_utils import do_rag_query
except ImportError as e:
    st.error(f"(Shortlist Tab) Failed to import required modules: {e}. Check file structure.")
    logging.error(f"(Shortlist Tab) Module import error: {e}", exc_info=True)
    # st.stop() # Avoid stopping the whole app if possible
    st.write("Error: Core modules not found. Tab cannot function.") # Display error within tab


# --- Updated Helper Function for Message Generation ---
def generate_shortlist_followup_messages(user_profile: dict) -> list[str]:
    """
    Generates ~10 helpful follow-up messages using the enhanced user profile.
    """
    messages = []
    if not user_profile:
        return ["Error: Cannot generate messages without user profile data."]

    # Extract data using .get() for safety
    username = user_profile.get('username', 'there')
    user_id = user_profile.get('user_id') # For logging/debugging

    # Prioritize country from user state, fallback to query JSON
    country = user_profile.get('state_dream_country')
    query_countries = user_profile.get('query_countries', [])
    if not country and query_countries:
        country = query_countries[0] # Take the first country from query if state is missing
    country = country or "your target country" # Final fallback

    degree = user_profile.get('query_degreeTitle', 'your desired field')
    specializations = user_profile.get('query_specializations', [])
    education_level = user_profile.get('query_educationLevel', 'your current education level')
    budget_signal = user_profile.get('query_budget', 'N/A')
    ielts_status = user_profile.get('ielts_status', 'N/A')
    study_abroad_status = user_profile.get('study_abroad_status', 'N/A')
    total_practice = user_profile.get('total_practice', 0)
    creation_time = user_profile.get('shortlist_creation_time', 'recently')
    top_courses = user_profile.get('top_shortlisted_courses', [])

    logging.info(f"Generating messages for user {user_id} ({username}) with profile: {user_profile}") # Log profile data

    # --- Message Templates using Enhanced Data ---

    # 1. Intro / Shortlist Context
    messages.append(f"Hi {username}, following up on the shortlist for {degree} you generated around {creation_time}. Kandor is here to help you take the next steps!")

    # 2. Country Focus
    country_msg = f"Focusing on {country}? It's a great choice for {degree}. We can delve deeper into university options or visa processes there."
    if query_countries and country not in query_countries and country != "your target country":
         country_msg += f" (We also noted your query mentioned {', '.join(query_countries)}.)"
    messages.append(country_msg)

    # 3. Course & Specialization Focus
    course_msg = f"For your interest in {degree}"
    if specializations:
        course_msg += f", especially focusing on {', '.join(specializations)}"
    if top_courses:
         course_msg += f". How did you feel about options like '{top_courses[0].get('name')}' at {top_courses[0].get('university', 'N/A')}?"
    else:
         course_msg += ". Let's explore specific programs that match your goals."
    messages.append(course_msg)

    # 4. IELTS Status / Prep
    if ielts_status and ielts_status != 'N/A' and ielts_status != 'Score Not Required':
        if 'Completed' in ielts_status or 'Score Added' in ielts_status:
             messages.append("Great to see your IELTS status is updated! Does your score meet the requirements for your preferred universities?")
        elif 'In Progress' in ielts_status or 'Planning' in ielts_status:
             messages.append(f"How is the IELTS preparation going (status: {ielts_status})? Kandor has resources that might help boost your score!")
        else: # Catch other statuses
             messages.append(f"Noticed your IELTS status is '{ielts_status}'. Need any guidance or practice materials?")
    else:
        messages.append("Are you planning to take the IELTS or another English proficiency test for admission to universities in {country}?")

    # 5. Study Abroad Status / Next Steps
    if study_abroad_status and study_abroad_status != 'N/A':
        messages.append(f"Your current study abroad status is '{study_abroad_status}'. What's the next big step you're focusing on? Application essays? University selection?")
    else:
        messages.append("What stage are you at in your study abroad journey? Researching, applying, or waiting for offers? Let us know how we can help.")

    # 6. Job Focus (RAG - pass enhanced profile)
    job_query = f"Briefly, what's the job outlook for {degree} graduates (specializing in {', '.join(specializations) if specializations else 'general'}) in {country}?"
    try:
        # Create a context profile subset for RAG if needed, or pass the whole dict
        rag_profile_context = {
            "DreamCountry": country,
            "MajorSubject": degree,
            "Specializations": specializations,
            # Add other relevant fields if RAG prompt uses them
        }
        job_info = do_rag_query(user_query=job_query, user_profile=rag_profile_context, top_k=2)
        if job_info and "not available" not in job_info.lower() and "error" not in job_info.lower():
             concise_job_info = job_info.split('\n')[0][:200] + ('...' if len(job_info) > 200 else '') # Keep it brief
             messages.append(f"Career outlook in {country} for {degree}: {concise_job_info}")
        else:
             messages.append(f"Thinking about careers after studying {degree} in {country}? We can explore job market trends for your specializations.")
    except Exception as e:
        logging.warning(f"RAG query failed for job outlook (User: {username}): {e}")
        messages.append(f"Interested in job prospects for {degree} in {country}? Let's research that together.")

    # 7. Immigration Focus (RAG - pass enhanced profile)
    immigration_query = f"What are the general post-study work visa options in {country} for international students graduating in {degree}?"
    try:
        rag_profile_context = {"DreamCountry": country, "MajorSubject": degree} # Simplified context for this query
        imm_info = do_rag_query(user_query=immigration_query, user_profile=rag_profile_context, top_k=2)
        if imm_info and "not available" not in imm_info.lower() and "error" not in imm_info.lower():
             concise_imm_info = imm_info.split('\n')[0][:200] + ('...' if len(imm_info) > 200 else '')
             messages.append(f"Post-study work options in {country} related to {degree}: {concise_imm_info}")
        else:
             messages.append(f"Understanding visa options after graduation in {country} is key. We can clarify pathways relevant to {degree}.")
    except Exception as e:
        logging.warning(f"RAG query failed for immigration info (User: {username}): {e}")
        messages.append(f"Navigating post-study visa options in {country}? We're here to guide you based on your interest in {degree}.")

    # 8. University Reminder (using top shortlisted)
    if len(top_courses) >= 2:
         messages.append(f"Let's revisit your shortlisted universities like {top_courses[0].get('university')} and {top_courses[1].get('university')}. We can check specific admission requirements or campus life details.")
    elif top_courses:
         messages.append(f"Let's take a closer look at {top_courses[0].get('university')} from your shortlist. We can find detailed admission info for the '{top_courses[0].get('name')}' program.")

    # 9. Budget Signal
    if budget_signal != 'N/A':
        messages.append(f"Considering your indicated budget ({budget_signal}), we can help find quality programs for {degree} in {country} that align with your financial plan.")

    # 10. Platform Engagement / General Support
    if total_practice > 10: # Example threshold
         messages.append(f"Great work on the {total_practice} IELTS practice questions on Kandor! Keep it up! Remember, the team is here for any support you need.")
    else:
         messages.append(f"Don't hesitate to reach out, {username}! The Kandor platform and team are ready to assist with any questions about your study abroad journey.")

    # Ensure we have 10 messages (add generic ones if needed)
    generic_messages = [
        f"Planning study abroad is a journey! What's the next milestone for you, {username}?",
        f"Need help comparing universities for {degree} in {country}? Let us know your criteria!",
        "Application deadlines can sneak up! Let's ensure you're on track for your target intake.",
        f"Remember, choosing the right course like {degree} is crucial for your future goals. Let's ensure it's the perfect fit!"
    ]
    idx = 0
    while len(messages) < 10 and idx < len(generic_messages):
        if generic_messages[idx] not in messages: # Avoid duplicates
             messages.append(generic_messages[idx])
        idx += 1

    return messages[:10] # Return exactly 10


# --- Main Rendering Function for the Tab ---
def render():
    st.header("Follow-up Messages for Shortlisted Users")

    # --- Date Selection ---
    # (Date selection logic remains the same)
    today = datetime.date.today()
    thirty_days_ago = today - relativedelta(days=29)
    date_range = [thirty_days_ago + datetime.timedelta(days=x) for x in range((today - thirty_days_ago).days + 1)]
    date_options = {d.strftime("%Y-%m-%d (%A)"): d for d in sorted(date_range, reverse=True)}
    selected_date_str = st.selectbox(
        "Select Shortlist Creation Date:",
        options=list(date_options.keys()),
        key="shortlist_date_selector", # Keep key consistent
        index=0
    )
    selected_date_obj = date_options[selected_date_str]

    # --- Fetch Users Button ---
    if st.button("Find Users Shortlisted on this Date", key="shortlist_find_users_button"): # Keep key consistent
        st.session_state["shortlist_selected_date"] = selected_date_obj
        st.session_state["shortlist_selected_user_id"] = None
        st.session_state["shortlist_generated_messages"] = []
        st.session_state["shortlisted_users_list"] = [] # Clear before fetch

        with st.spinner(f"Searching for users shortlisted on {selected_date_str}..."):
            try:
                # Call the REVISED DB function
                users = get_users_shortlisted_on_date(selected_date_obj)
                st.session_state["shortlisted_users_list"] = users # Store the enhanced list
                # Log fetched data structure for debugging
                if users:
                    logging.debug(f"Fetched user details structure: {users[0]}")

            except Exception as e:
                st.error(f"Database error fetching shortlisted users: {e}")
                logging.error(f"Error calling get_users_shortlisted_on_date: {e}", exc_info=True)
                st.session_state["shortlisted_users_list"] = []


    # --- Display Users and Generate Messages Section ---
    if st.session_state.get("shortlist_selected_date"):
        # Retrieve the potentially enhanced user list from session state
        users_list = st.session_state.get("shortlisted_users_list", [])

        if not users_list:
             # Check if the button was clicked for this date to show message, avoids showing it initially
            if st.session_state.get("shortlist_selected_date") == selected_date_obj:
                st.info(f"No users found with shortlists created on {st.session_state['shortlist_selected_date'].strftime('%Y-%m-%d')}.")
        else:
            st.subheader(f"Users Shortlisted on {st.session_state['shortlist_selected_date'].strftime('%Y-%m-%d')}")
            col_users, col_messages = st.columns([1, 2])

            with col_users:
                st.markdown("**Select User:**")
                # --- UPDATED User Options ---
                # Create display names including the creation time
                user_options_dict = {}
                for user in users_list:
                    # Use the new enhanced dictionary fields
                    display_name = f"{user.get('username', 'N/A')} ({user.get('phone', 'N/A')}) @ {user.get('shortlist_creation_time', '--:--')}"
                    user_id = user.get('user_id')
                    if user_id: # Only add if user_id is valid
                        user_options_dict[display_name] = user_id

                # Callback function remains structurally similar
                def handle_user_selection():
                    selected_display_name = st.session_state.shortlist_user_selector
                    if selected_display_name and selected_display_name in user_options_dict:
                        newly_selected_user_id = user_options_dict[selected_display_name]
                        if st.session_state.get("shortlist_selected_user_id") != newly_selected_user_id:
                            st.session_state["shortlist_selected_user_id"] = newly_selected_user_id
                            st.session_state["shortlist_generated_messages"] = [] # Clear old messages
                            # No need to fetch profile again, it's already in users_list
                            # The full enhanced profile will be retrieved below before generating messages

                # Radio button - options list now uses the new display names
                st.radio(
                    "Select User to Generate Follow-up Messages:",
                    options=list(user_options_dict.keys()),
                    key="shortlist_user_selector",
                    index=None,
                    on_change=handle_user_selection
                )

            with col_messages:
                st.subheader("Generated Follow-up Messages")
                selected_user_id = st.session_state.get("shortlist_selected_user_id")

                if selected_user_id:
                    # Find the full enhanced profile for the selected user from the list in session state
                    selected_user_profile = next((user for user in users_list if user.get('user_id') == selected_user_id), None)

                    if not selected_user_profile:
                         st.error("Error: Could not find details for the selected user in the loaded list.")
                         st.session_state["shortlist_generated_messages"] = ["Error: User details missing."]

                    # Check if messages are already generated FOR THIS USER
                    elif st.session_state.get("shortlist_generated_messages"):
                        messages_to_display = st.session_state["shortlist_generated_messages"]
                        # Display user details briefly for context
                        st.markdown(f"**Messages for:** {selected_user_profile.get('username', 'N/A')} ({selected_user_profile.get('phone', 'N/A')})")
                        st.markdown(f"**Target:** {selected_user_profile.get('state_dream_country', 'N/A')} | **Field:** {selected_user_profile.get('query_degreeTitle', 'N/A')}")

                        st.success(f"Showing {len(messages_to_display)} messages:")
                        for i, msg in enumerate(messages_to_display, 1):
                            st.text_area(f"Message {i}", value=msg, height=110, key=f"shortlist_msg_{selected_user_id}_{i}", help="You can copy this message.")
                    else:
                        # Messages not generated yet, generate them now using the full profile
                        st.info(f"Generating messages for {selected_user_profile.get('username', 'N/A')}...")
                        with st.spinner("AI is crafting helpful messages..."):
                             try:
                                 # Call the UPDATED message generation function with the ENHANCED profile
                                 messages = generate_shortlist_followup_messages(selected_user_profile)
                                 st.session_state["shortlist_generated_messages"] = messages
                                 st.rerun() # Rerun to display the newly generated messages
                             except Exception as e:
                                 st.error(f"Error generating messages: {e}")
                                 logging.error(f"Message generation error for user {selected_user_id}: {e}", exc_info=True)
                                 st.session_state["shortlist_generated_messages"] = [f"Failed to generate messages due to an error: {e}"]
                                 st.rerun() # Rerun to display the error message

                else:
                    st.info("Select a user from the list on the left to generate and view suggested follow-up messages.")

    # else: # Initial state before date is searched - handled by button logic
    #     pass