import random

USE_CASES = {
    "course_info": "Here is some info on choosing the right course ...",
    "country_info": "Guidelines for picking the right country ...",
    "visa_policy": "Visa policies vary based on your target country ...",
    # ...
    # Up to 30 different topics
}

def generate_use_case_message(use_case_key, user_profile):
    """
    Returns a short text message for the specified use case, 
    optionally personalizing it with 'user_profile'.
    """
    if use_case_key not in USE_CASES:
        return "No template found for that use case."

    base_text = USE_CASES[use_case_key]
    # Simple personalization example
    user_name = user_profile.get("username", "Aspirant")
    personalized_text = f"Hey {user_name}, {base_text}"
    return personalized_text


def generate_all_use_cases(user_profile):
    """
    Returns a list of 30 text messages for all use cases,
    or you can pick specific ones as needed.
    """
    messages = []
    for use_case_key in USE_CASES.keys():
        msg = generate_use_case_message(use_case_key, user_profile)
        messages.append(msg)

    # If you truly have 30 templates, store them in the dictionary 
    # or create a structure that holds all 30, then generate them all.
    # This is just an example.
    return messages
