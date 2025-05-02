# tabs/ai_tools.py

import streamlit as st
import logging

# --- Import Core Logic ---
try:
    from db_connection import get_aitools_profile_users
    from rag_utils import do_rag_query # Assuming RAG is needed for suggestions
except ImportError as e:
    st.error(f"(AI Tools Tab) Failed to import required modules: {e}. Check file structure.")
    logging.error(f"(AI Tools Tab) Module import error: {e}", exc_info=True)
    st.write("Error: Core modules not found. Tab cannot function.")
    st.stop()

# --- Helper Function for Message Generation ---
def generate_ai_tools_messages(profile_data: dict) -> list[str]:
    """Generates insightful messages based on non-NULL fields in aitools_profile."""
    messages = []
    if not profile_data:
        return ["Error: No profile data provided."]

    # Extract known fields, handling None
    userid = profile_data.get('userid')
    username = profile_data.get('username', 'User') # Get username from joined data
    category = profile_data.get('category')
    subCategory = profile_data.get('subCategory')
    selectedPlan = profile_data.get('selectedPlan')
    career = profile_data.get('career')
    countries = profile_data.get('countries') # Might be string or list? Assuming string for now based on example
    highestLevel = profile_data.get('highestLevel')
    course = profile_data.get('course') # Specific course mentioned

    logging.info(f"Generating AI Tools messages for User: {userid} ({username})")

    # Identify non-null fields to understand user's focus/confusion
    present_fields = {
        'category': category, 'subCategory': subCategory, 'plan': selectedPlan,
        'career': career, 'countries': countries, 'level': highestLevel, 'course': course
    }
    non_null_info = {k: v for k, v in present_fields.items() if v is not None and v != ''}

    # Construct profile subset for RAG context if needed
    rag_context_profile = {
        "aitools_category": category, "aitools_subCategory": subCategory,
        "aitools_career": career, "aitools_countries": countries,
        "aitools_highestLevel": highestLevel, "aitools_course": course,
        "aitools_budget": selectedPlan
        # Add other relevant profile fields if joining with users_latest_state provides more
    }

    # --- Generate Messages based on available info ---

    # Message 1: Acknowledge exploration
    explore_msg = f"Hi {username}, thanks for using the AI tools!"
    if non_null_info:
        explore_msg += " Looks like you're exploring options related to: "
        explore_msg += ", ".join([f"{k.replace('_',' ').title()}: '{v}'" for k, v in non_null_info.items()]) + "."
    else:
        explore_msg += " Let us know what you're trying to figure out!"
    messages.append(explore_msg)

    # Message 2: Focus on Career goal if present
    if career:
        msg = f"Focusing on becoming a {career}?"
        if not countries and not course:
            # Use RAG to suggest countries/courses
            rag_query = f"What are some good countries and general course types for a career as a {career}, considering someone looking for {highestLevel or 'any level'} education?"
            try:
                suggestions = do_rag_query(user_query=rag_query, user_profile=rag_context_profile, top_k=2)
                if suggestions and "not available" not in suggestions.lower():
                    msg += f" We can help explore options. Some suggestions based on AI: {suggestions[:200]}..."
                else:
                    msg += " We can research the best countries and study paths for this role."
            except Exception as e:
                logging.warning(f"RAG failed for career suggestions: {e}")
                msg += " We can help research suitable countries and study paths."
        elif not countries:
             msg += f" We can help identify the best countries to study '{course or subCategory or category}' to reach that goal."
        elif not course and (category or subCategory):
             msg += f" Let's find the right courses in {countries} related to '{subCategory or category}' that lead to this career."
        else:
            msg += " Let's ensure your chosen path aligns well with this goal!"
        messages.append(msg)

    # Message 3: Focus on Subject/Specialization if present
    elif category or subCategory:
        subject = subCategory or category
        msg = f"Interested in {subject} (in {category})?"
        if not career and not countries:
            # Use RAG
            rag_query = f"What are typical career paths and good study destinations for {subject} (field: {category}) at the {highestLevel or 'any'} level?"
            try:
                suggestions = do_rag_query(user_query=rag_query, user_profile=rag_context_profile, top_k=2)
                if suggestions and "not available" not in suggestions.lower():
                    msg += f" Potential paths & places based on AI: {suggestions[:200]}..."
                else:
                     msg += " We can explore potential careers and ideal study destinations for this field."
            except Exception as e:
                logging.warning(f"RAG failed for subject suggestions: {e}")
                msg += " We can explore potential careers and ideal study destinations."
        elif not career:
             msg += f" We can research potential career outcomes after studying this in {countries}."
        elif not countries:
             msg += f" Let's find the best countries to study {subject} to become a {career}."
        else:
             msg += f" {countries} is a great choice for this field!"
        messages.append(msg)

    # Message 4: Focus on Country if present
    elif countries:
        msg = f"Thinking about studying in {countries}?"
        if not category and not subCategory and not career:
            msg += " What subjects or career paths are you considering there? Knowing this helps us find the best opportunities."
        elif category or subCategory:
             msg += f" It's a good destination for fields like {category or subCategory}. Let's find specific programs."
        elif career:
             msg += f" We can explore how studying in {countries} helps achieve your goal of becoming a {career}."
        messages.append(msg)

    # Message 5: Budget Signal
    if selectedPlan:
        messages.append(f"Noted your budget preference: {selectedPlan}. We'll keep this in mind when suggesting universities and programs.")

    # Message 6: Education Level
    if highestLevel:
         messages.append(f"Looking for {highestLevel} programs? We can filter options based on this level and your field of interest ({category or subCategory or 'any field'}).")

    # Message 7: Specific Course Mentioned
    if course:
        msg = f"You mentioned interest in '{course}'."
        if category and course != category: msg += f" (related to {category})"
        if countries: msg += f" in {countries}"
        msg += ". We can find universities offering this specific program or similar ones."
        messages.append(msg)

    # Message 8: Connecting pieces
    if career and (category or subCategory) and countries:
         messages.append(f"Combining your interest in {career}, {subCategory or category}, and {countries} - let's find programs that perfectly match all three!")
    elif career and (category or subCategory):
         messages.append(f"Let's bridge your interest in {subCategory or category} with your {career} goal. We can find programs that offer the right skills.")
    elif (category or subCategory) and countries:
         messages.append(f"Studying {subCategory or category} in {countries} offers great opportunities. Let's find the best universities there for you.")

    # Message 9: Value Prop / Next Step
    messages.append("Kandor's AI tools are just the start! Our counselors can provide personalized guidance based on your exploration. What's your main question right now?")

    # Message 10: General Encouragement
    messages.append("Exploring study abroad options is a big step! Keep using the AI tools, and don't hesitate to ask us specific questions.")

    # Fill remaining messages
    # ... (fill logic) ...
    while len(messages) < 10: messages.append(f"We're here to help clarify your path, {username}. What's on your mind?")

    return messages[:10]


# --- Main Rendering Function for the Tab ---
def render():
    st.header("AI Tools User Insights")
    st.markdown("View users who have used AI exploration tools and generate helpful follow-up messages based on their indicated interests.")

    # --- Initialize State for this tab ---
    if "ai_tools_users_list" not in st.session_state: st.session_state["ai_tools_users_list"] = None
    if "ai_tools_selected_userid" not in st.session_state: st.session_state["ai_tools_selected_userid"] = None
    if "ai_tools_generated_messages" not in st.session_state: st.session_state["ai_tools_generated_messages"] = {} # Cache per userid

    # --- Load User List ---
    # Load once or provide a refresh button
    if st.session_state["ai_tools_users_list"] is None:
        with st.spinner("Loading AI Tools user list..."):
            try:
                st.session_state["ai_tools_users_list"] = get_aitools_profile_users()
            except Exception as e:
                st.error(f"Failed to load user list: {e}")
                st.session_state["ai_tools_users_list"] = [] # Set empty list on error

    users_list = st.session_state["ai_tools_users_list"]

    if not users_list:
        st.warning("No users found in the AI Tools profile table or failed to load.")
        return # Stop rendering if no users

    # --- Layout ---
    col_users, col_details_messages = st.columns([1, 2])

    with col_users:
        st.subheader("Select User")
        # Create display options
        user_options = {f"{user.get('username', 'N/A')} ({user.get('phone', 'N/A')})": user.get('userid') for user in users_list}
        display_list = list(user_options.keys())

        # Callback to handle selection change
        def handle_aitools_user_selection():
            selected_display = st.session_state.ai_tools_user_selector_radio
            if selected_display and selected_display in user_options:
                 selected_uid = user_options[selected_display]
                 if st.session_state.get("ai_tools_selected_userid") != selected_uid:
                      st.session_state["ai_tools_selected_userid"] = selected_uid
                      # Clear message cache for previous user? Optional.
                      # Message generation happens in the other column based on selection change.

        # Find current index for radio button
        current_selection_index = None
        selected_uid_from_state = st.session_state.get("ai_tools_selected_userid")
        if selected_uid_from_state:
             # Find the display name corresponding to the selected user ID
             for display_name, uid in user_options.items():
                  if uid == selected_uid_from_state:
                      try:
                          current_selection_index = display_list.index(display_name)
                      except ValueError: pass # Should not happen
                      break

        st.radio(
            "Users:",
            options=display_list,
            key="ai_tools_user_selector_radio",
            index=current_selection_index, # Set pre-selection based on state
            on_change=handle_aitools_user_selection
        )

    with col_details_messages:
        selected_userid = st.session_state.get("ai_tools_selected_userid")

        if not selected_userid:
            st.info("Select a user from the list on the left.")
        else:
            # Find the selected user's full profile data from the list
            selected_profile_data = next((user for user in users_list if user.get('userid') == selected_userid), None)

            if not selected_profile_data:
                st.error("Selected user data not found.")
            else:
                st.subheader(f"User Insights for: {selected_profile_data.get('username', selected_userid)}")

                # Display non-null profile fields
                st.markdown("**User's Explored Interests:**")
                displayed_info = False
                fields_to_display = ['category', 'subCategory', 'selectedPlan', 'career', 'countries', 'highestLevel', 'course']
                for field in fields_to_display:
                    value = selected_profile_data.get(field)
                    if value is not None and value != '':
                        # Simple formatting for display
                        label = field.replace('_', ' ').replace('selectedPlan', 'Budget Plan').title()
                        st.markdown(f"- **{label}:** {value}")
                        displayed_info = True
                if not displayed_info:
                    st.markdown("- *No specific interests recorded via AI tools yet.*")

                st.divider()

                # --- Message Generation and Display ---
                st.subheader("Suggested Follow-up Messages")
                # Check cache first
                cached_messages = st.session_state.get("ai_tools_generated_messages", {}).get(selected_userid)

                if cached_messages:
                    st.success(f"Showing {len(cached_messages)} cached messages:")
                    for i, msg in enumerate(cached_messages, 1):
                        st.text_area(f"Message {i}", value=msg, height=100, key=f"aitools_msg_{selected_userid}_{i}", help="Copy message text.")
                else:
                    # Generate button or generate automatically? Let's generate automatically on selection for now.
                    with st.spinner("Generating insightful messages..."):
                         try:
                             messages = generate_ai_tools_messages(selected_profile_data)
                             # Cache messages
                             st.session_state.setdefault("ai_tools_generated_messages", {})[selected_userid] = messages
                             st.rerun() # Rerun to display newly generated messages
                         except Exception as e:
                             st.error(f"Failed to generate messages: {e}")
                             logging.error(f"AI Tools message generation error for {selected_userid}: {e}", exc_info=True)

# If running standalone for testing
if __name__ == "__main__":
     st.warning("Running AI Tools tab standalone.")
     # Add minimal state init if needed for testing
     render()