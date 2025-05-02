# db_connection.py

import pymysql
from pymysql.cursors import DictCursor
import datetime
import json
import logging
from dateutil.relativedelta import relativedelta
from typing import Optional, List, Dict, Any # Import necessary types

# Example read-only config (ensure this is correct)
readonly_main_db_config = {
    "host": "kandor-mysql-read-replica.cvdvbtevwzmy.us-east-2.rds.amazonaws.com",
    "user": "kandor",
    "password": "Humtum99",
    "db": "main",
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
    "connect_timeout": 20,
    "read_timeout": 60,
    "write_timeout": 60
}

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_connection():
    """Creates and returns a new read-only MySQL connection."""
    try:
        conn = pymysql.connect(**readonly_main_db_config)
        return conn
    except pymysql.Error as e:
        logging.error(f"Database connection failed: {e}")
        return None

# --- Keep existing functions like get_user_by_id, get_user_by_phone etc. ---
# Make sure get_user_by_id exists if you need it elsewhere
def get_user_by_id(user_id):
    """Retrieves a single user's record from 'users_latest_state'."""
    conn = get_connection()
    if not conn: return None
    try:
        with conn.cursor() as cursor:
            # Assuming user ID in users_latest_state is 'userid'
            query = "SELECT * FROM users_latest_state WHERE userid = %s LIMIT 1"
            cursor.execute(query, (user_id,))
            user_record = cursor.fetchone()
        return user_record
    except pymysql.Error as e:
        logging.error(f"DB Error fetching user by ID {user_id}: {e}")
        return None
    finally:
        if conn: conn.close()

def get_user_by_phone(phone: str):
    """Search 'users_latest_state' table for a matching phone number."""
    conn = get_connection()
    if not conn: return None
    try:
        with conn.cursor() as cursor:
            query = "SELECT * FROM users_latest_state WHERE phone = %s LIMIT 1"
            cursor.execute(query, (phone,))
            user = cursor.fetchone()
        return user
    except pymysql.Error as e:
        logging.error(f"DB Error fetching user by phone {phone}: {e}")
        return None
    finally:
        if conn: conn.close()

def get_shortlists_by_user(user_id):
    """Retrieves shortlists for a user (simplified version for now)."""
    conn = get_connection()
    if not conn: return []
    try:
        with conn.cursor() as cursor:
            # Select relevant fields, including the JSON ones
            query = """
                SELECT id, user_id, shortlist, date_created, query
                FROM shortlists
                WHERE user_id = %s
                ORDER BY date_created DESC
            """
            cursor.execute(query, (user_id,))
            shortlists_raw = cursor.fetchall()
            # Basic parsing attempt (could be more robust)
            parsed_shortlists = []
            for sl in shortlists_raw:
                try:
                    sl['query_data'] = json.loads(sl.get('query', '{}') or '{}')
                    sl['shortlist_data'] = json.loads(sl.get('shortlist', '{}') or '{}')
                except json.JSONDecodeError:
                    sl['query_data'] = {"error": "Failed to parse query JSON"}
                    sl['shortlist_data'] = {"error": "Failed to parse shortlist JSON"}
                parsed_shortlists.append(sl)
            return parsed_shortlists
    except pymysql.Error as e:
        logging.error(f"DB Error fetching shortlists for user {user_id}: {e}")
        return []
    finally:
        if conn: conn.close()

# --- REVISED Function for Shortlist Tab ---

def get_users_shortlisted_on_date(selected_date: datetime.date):
    """
    Retrieves detailed info for users who created their LATEST shortlist
    on the specified date. Includes parsed data from JSON fields.

    Args:
        selected_date: The specific date (datetime.date object) to filter by.

    Returns:
        A list of dictionaries, each containing enhanced user/shortlist info.
        Returns an empty list if no users found or on error.
    """
    conn = get_connection()
    users_details_list = []
    if not conn:
        return users_details_list

    try:
        with conn.cursor() as cursor:
            # Find the latest shortlist record ID for each user on the selected date
            # This subquery ensures we only process one (the latest) shortlist per user per day
            sub_query = """
                SELECT MAX(id) as latest_shortlist_id
                FROM shortlists
                WHERE DATE(date_created) = %s
                GROUP BY user_id
            """

            # Main query joining the latest shortlist with user state
            query = """
                SELECT
                    s.user_id,
                    s.date_created,
                    s.query as query_json_str,
                    s.shortlist as shortlist_json_str,
                    uls.username,
                    uls.phone,
                    uls.DreamCountry as state_dream_country,
                    uls.ielts_status,
                    uls.study_abroad_status,
                    uls.total_practice
                FROM shortlists s
                JOIN users_latest_state uls ON s.user_id = uls.userid
                WHERE s.id IN ({})
            """.format(sub_query) # Use format here as pymysql might struggle with IN subquery placeholder

            cursor.execute(query, (selected_date,))
            results = cursor.fetchall()

        # Process results in Python
        for row in results:
            user_detail = {'user_id': row['user_id']}

            # Basic user info from users_latest_state
            user_detail['username'] = row.get('username', 'N/A')
            user_detail['phone'] = row.get('phone', 'N/A')
            user_detail['state_dream_country'] = row.get('state_dream_country') # Country from user state
            user_detail['ielts_status'] = row.get('ielts_status')
            user_detail['study_abroad_status'] = row.get('study_abroad_status')
            user_detail['total_practice'] = row.get('total_practice', 0) # Default to 0

            # Time of shortlist creation
            date_created_dt = row.get('date_created')
            if isinstance(date_created_dt, datetime.datetime):
                user_detail['shortlist_creation_time'] = date_created_dt.strftime("%H:%M") # HH:MM format
            else:
                user_detail['shortlist_creation_time'] = "N/A"

            # Parse 'query' JSON
            query_data = {}
            try:
                query_json_str = row.get('query_json_str', '{}') or '{}' # Handle None or empty string
                query_data = json.loads(query_json_str)
            except json.JSONDecodeError as e:
                logging.warning(f"Failed to parse query JSON for user {row['user_id']} on {selected_date}: {e}. String was: {query_json_str}")
                query_data = {'error': 'parse_failed'}

            user_detail['query_countries'] = query_data.get('countries', [])
            user_detail['query_degreeTitle'] = query_data.get('degreeTitle', 'N/A')
            user_detail['query_educationLevel'] = query_data.get('highestLevelOfEducation', 'N/A')
            user_detail['query_budget'] = query_data.get('selectedPlan', 'N/A')
            user_detail['query_specializations'] = query_data.get('listOfSpecializations', []) # Assuming it's a list

            # Parse 'shortlist' JSON and extract top 5 courses
            top_courses = []
            try:
                shortlist_json_str = row.get('shortlist_json_str', '{}') or '{}'
                shortlist_data = json.loads(shortlist_json_str)
                
                all_courses = []
                if isinstance(shortlist_data, dict):
                    # Iterate through university IDs (keys), then course lists (values)
                    for uni_id, courses in shortlist_data.items():
                        if isinstance(courses, list):
                            for course in courses:
                                if isinstance(course, dict):
                                    # Add score if present, otherwise default (e.g., 0) for sorting
                                    course_info = {
                                        'name': course.get('course_name', 'N/A'),
                                        'university': course.get('university', 'N/A'),
                                        'score': float(course.get('score', 0.0)) # Convert score for sorting
                                    }
                                    all_courses.append(course_info)
                                    
                # Sort courses by score (descending, higher is better?) or just take first found if no score
                # Assuming higher score is better. If score is unreliable, remove sorting.
                all_courses.sort(key=lambda x: x['score'], reverse=True)
                top_courses = all_courses[:5] # Take the top 5

            except json.JSONDecodeError as e:
                logging.warning(f"Failed to parse shortlist JSON for user {row['user_id']} on {selected_date}: {e}. String was: {shortlist_json_str}")
                top_courses = [{'name': 'Error parsing shortlist', 'university': '', 'score': 0.0}]
            except ValueError as e:
                 logging.warning(f"Failed to convert score to float for user {row['user_id']} on {selected_date}: {e}")
                 # Fallback: just take the first 5 encountered if sorting fails
                 first_five = []
                 if isinstance(shortlist_data, dict):
                    for uni_id, courses in shortlist_data.items():
                        if isinstance(courses, list):
                            for course in courses:
                                if isinstance(course, dict) and len(first_five) < 5:
                                    first_five.append({
                                        'name': course.get('course_name', 'N/A'),
                                        'university': course.get('university', 'N/A'),
                                        'score': course.get('score', 'N/A') # Keep original score string
                                    })
                    top_courses = first_five


            user_detail['top_shortlisted_courses'] = top_courses

            users_details_list.append(user_detail)

    except pymysql.Error as e:
        logging.error(f"Database error in get_users_shortlisted_on_date for date {selected_date}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error in get_users_shortlisted_on_date for date {selected_date}: {e}")
    finally:
        if conn:
            conn.close()

    return users_details_list




# --- REMOVED get_university_name_by_id function ---

# ---- UPDATED Functions for College Explorer Tab ----

def get_users_by_university_interaction(selected_date: datetime.date):
    """
    Finds users who interacted ('univ_profile', 'apply_university')
    with universities on a specific date. Returns interaction details
    WITHOUT university name initially.

    Args:
        selected_date: The date to query event logs for.

    Returns:
        A list of dictionaries, each containing:
        'user_id', 'username', 'phone', 'university_id', 'interaction_time' (HH:MM)
    """
    conn = get_connection()
    interactions = []
    if not conn: return interactions

    try:
        with conn.cursor() as cursor:
            # Query event_logs, join with users_latest_state
            # Get the latest interaction time per user/university pair on that day
            query = """
                SELECT
                    e.userid AS user_id,
                    e.event_id AS university_id,
                    MAX(e.event_created_ts) AS latest_interaction_ts,
                    uls.username,
                    uls.phone
                FROM event_logs e
                JOIN users_latest_state uls ON e.userid = uls.userid
                WHERE
                    e.event_type IN ('univ_profile', 'apply_university')
                    AND DATE(e.event_created_ts) = %s
                GROUP BY
                    e.userid, e.event_id, uls.username, uls.phone
                ORDER BY latest_interaction_ts DESC
            """
            cursor.execute(query, (selected_date,))
            results = cursor.fetchall()

        # Process results: Format time
        for row in results:
            interaction = {
                'user_id': row['user_id'],
                'username': row.get('username', 'N/A'),
                'phone': row.get('phone', 'N/A'),
                'university_id': row.get('university_id'), # Get the ID
                # University Name will be fetched later
                'interaction_time': "N/A"
            }
            # Format time
            ts = row.get('latest_interaction_ts')
            if isinstance(ts, datetime.datetime):
                interaction['interaction_time'] = ts.strftime("%H:%M")

            # Only add if university_id is present
            if interaction['university_id']:
                 interactions.append(interaction)
            else:
                 logging.warning(f"Interaction record found for user {row['user_id']} without university_id (event_id) on {selected_date}.")


    except pymysql.Error as e:
        logging.error(f"DB Error fetching university interactions for date {selected_date}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error fetching university interactions for date {selected_date}: {e}")
    finally:
        if conn: conn.close()

    return interactions


# In db_connection.py

# ... (other imports and functions) ...

def get_latest_shortlist_data_and_uni_name(
        user_id: str,
        selected_date: datetime.date, # Keep param for now to avoid changing caller immediately
        university_id_to_find: str
    ) -> Optional[Dict[str, Any]]:
    """
    Retrieves the user's MOST RECENT shortlist overall (ignoring selected_date),
    parses its JSON fields, extracts key info, AND finds the name and first course
    name of a specific university ID within that shortlist's JSON data.

    Args:
        user_id: The user's ID.
        selected_date: The date of interaction (IGNORED for shortlist lookup).
        university_id_to_find: The university ID whose details we need from the shortlist.

    Returns:
        A dictionary containing 'query_profile_data', 'top_shortlisted_courses',
        'interacted_university_name', and 'interacted_course_name',
        or None if no shortlist found for the user at all, or on error.
    """
    conn = get_connection()
    if not conn: return None

    shortlist_details = None
    logging.info(f"Fetching LATEST shortlist data for user {user_id} (ignoring date {selected_date}) to find info for uni {university_id_to_find}") # Log intent

    try:
        with conn.cursor() as cursor:
            # --- MODIFIED SQL QUERY ---
            # Remove the date filter: AND DATE(date_created) = %s
            query = """
                SELECT
                    query as query_json_str,
                    shortlist as shortlist_json_str
                FROM shortlists
                WHERE
                    user_id = %s
                ORDER BY date_created DESC
                LIMIT 1
            """
            # Execute with only user_id
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            # --- END MODIFIED SQL QUERY ---

        if result:
            # --- Parsing logic remains IDENTICAL to the previous version ---
            # It will parse the query JSON, parse the shortlist JSON,
            # extract top 5 courses, find the names for university_id_to_find,
            # and structure the dictionary.
            # ... (Keep all the JSON parsing, name finding, error handling logic from the previous correct version of this function) ...
            shortlist_details = {}
            query_data = {}
            top_courses = []
            interacted_university_name = None
            interacted_course_name = None

            # Parse 'query' JSON
            try:
                query_json_str = result.get('query_json_str', '{}') or '{}'
                query_data = json.loads(query_json_str)
            except json.JSONDecodeError as e:
                logging.warning(f"Failed to parse query JSON for user {user_id}'s latest shortlist: {e}")
                query_data = {'error': 'parse_failed'}

            shortlist_details['query_profile_data'] = {
                'countries': query_data.get('countries', []), 'degreeTitle': query_data.get('degreeTitle', 'N/A'),
                'educationLevel': query_data.get('highestLevelOfEducation', 'N/A'), 'budget': query_data.get('selectedPlan', 'N/A'),
                'specializations': query_data.get('listOfSpecializations', [])
            }

            # Parse 'shortlist' JSON, extract top 5 courses, AND find the specific university/course name
            try:
                shortlist_json_str = result.get('shortlist_json_str', '{}') or '{}'
                shortlist_data = json.loads(shortlist_json_str)
                all_courses = []
                if isinstance(shortlist_data, dict):
                    for current_uni_id, courses_list in shortlist_data.items():
                        if isinstance(courses_list, list) and courses_list:
                             if current_uni_id == university_id_to_find:
                                 interacted_university_name = courses_list[0].get('university')
                                 interacted_course_name = courses_list[0].get('course_name')
                             for course in courses_list:
                                 if isinstance(course, dict):
                                     all_courses.append({'name': course.get('course_name', 'N/A'), 'university': course.get('university', 'N/A'), 'score': float(course.get('score', 0.0))})
                all_courses.sort(key=lambda x: x['score'], reverse=True)
                top_courses = all_courses[:5]
            except json.JSONDecodeError as e:
                logging.warning(f"Failed to parse shortlist JSON for user {user_id}'s latest shortlist: {e}")
                top_courses = [{'name': 'Error parsing shortlist', 'university': '', 'score': 0.0}]
            except ValueError as e:
                 logging.warning(f"Failed to convert score to float for user {user_id}'s latest shortlist: {e}. Using unsorted.")
                 first_five = [] # Fallback logic from previous step
                 if isinstance(shortlist_data, dict):
                     count = 0
                     for current_uni_id, courses_list in shortlist_data.items():
                          if isinstance(courses_list, list) and courses_list:
                              if current_uni_id == university_id_to_find and not interacted_university_name and courses_list:
                                   interacted_university_name = courses_list[0].get('university')
                                   interacted_course_name = courses_list[0].get('course_name')
                              if count < 5:
                                  for course in courses_list:
                                     if count >= 5: break
                                     if isinstance(course, dict): first_five.append({'name': course.get('course_name', 'N/A'), 'university': course.get('university', 'N/A'), 'score': course.get('score', 'N/A')}); count += 1
                     top_courses = first_five

            shortlist_details['top_shortlisted_courses'] = top_courses
            shortlist_details['interacted_university_name'] = interacted_university_name or f"ID: {university_id_to_find}"
            shortlist_details['interacted_course_name'] = interacted_course_name or "N/A"
            # --- End of parsing logic ---
        else:
            logging.warning(f"No shortlist found AT ALL for user {user_id}.")


    except pymysql.Error as e:
        logging.error(f"DB Error fetching latest shortlist data/uni name for user {user_id}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error fetching latest shortlist data/uni name for user {user_id}: {e}")
    finally:
        if conn: conn.close()

    return shortlist_details # Will be None if no record found or if outer try fails

def get_aitools_profile_users():
    """
    Fetches all user profiles from the aitools_profile table,
    joining with users_latest_state to get username and phone.

    Returns:
        A list of dictionaries, each containing the merged data,
        or an empty list on error.
    """
    conn = get_connection()
    user_profiles = []
    if not conn:
        return user_profiles

    try:
        with conn.cursor() as cursor:
            # Select all fields from aitools_profile and required fields from users_latest_state
            # Using LEFT JOIN to ensure all aitools_profile users are included,
            # even if they somehow aren't in users_latest_state.
            query = """
                SELECT
                    a.*,
                    uls.username,
                    uls.phone
                FROM aitools_profile a
                LEFT JOIN users_latest_state uls ON a.userid = uls.userid
                ORDER BY uls.username, a.userid # Order for consistent display
            """
            cursor.execute(query)
            user_profiles = cursor.fetchall()

            # Clean up potential None values from the join if needed,
            # although DictCursor usually handles this okay.
            # Example: Replace None username/phone with 'N/A'
            for profile in user_profiles:
                if profile.get('username') is None:
                    profile['username'] = 'N/A'
                if profile.get('phone') is None:
                    profile['phone'] = 'N/A'

    except pymysql.Error as e:
        logging.error(f"DB Error fetching AI tools profiles: {e}")
    except Exception as e:
        logging.error(f"Unexpected error fetching AI tools profiles: {e}")
    finally:
        if conn:
            conn.close()

    return user_profiles

def get_ielts_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches the profile data for a specific user from ielts_users_profile.

    Args:
        user_id: The user's ID.

    Returns:
        A dictionary containing the IELTS profile data, or None if not found/error.
    """
    conn = get_connection()
    profile_data = None
    if not conn:
        return None

    try:
        with conn.cursor() as cursor:
            # Select the required fields
            query = """
                SELECT
                    userid, ielts_attempts, DreamCountry, Funds, goal, mx_region,
                    ielts_status, study_abroad_status, work_status, category, subCategory
                FROM ielts_users_profile
                WHERE userid = %s
                LIMIT 1
            """
            cursor.execute(query, (user_id,))
            profile_data = cursor.fetchone()

    except pymysql.Error as e:
        logging.error(f"DB Error fetching IELTS profile for user {user_id}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error fetching IELTS profile for user {user_id}: {e}")
    finally:
        if conn:
            conn.close()

    return profile_data

def get_combined_chat_users_on_date(selected_date: datetime.date) -> List[Dict[str, Any]]:
    """
    Fetches users active in EITHER ai_counselor_conv_history OR shortlists
    on a specific date. Returns details of the latest activity (from either table)
    for each user on that day.

    Args:
        selected_date: The date to query activity for.

    Returns:
        List of dicts: 'user_id', 'username', 'phone', 'overall_latest_ts',
                      'latest_conv_history_str', 'latest_query_json_str' (optional),
                      'latest_source' ('koda' or 'shortlist'). Empty list on error.
    """
    conn = get_connection()
    if not conn: return []

    combined_activity = {} # {userid: {details}}

    try:
        with conn.cursor() as cursor:
            # Query 1: Latest from ai_counselor_conv_history
            query1 = """
                SELECT
                    ch.userid AS user_id,
                    MAX(ch.created) AS last_ts,
                    # Fetch conv_history associated with the MAX timestamp
                    (SELECT conv_history FROM ai_counselor_conv_history chi
                     WHERE chi.userid = ch.userid AND chi.created = MAX(ch.created) LIMIT 1) as conv_history_json_str
                FROM ai_counselor_conv_history ch
                WHERE DATE(ch.created) = %s
                GROUP BY ch.userid
            """
            cursor.execute(query1, (selected_date,))
            koda_results = cursor.fetchall()
            for row in koda_results:
                combined_activity[row['user_id']] = {
                    'last_ts': row['last_ts'],
                    'conv_history_str': row.get('conv_history_json_str'),
                    'query_str': None, # No query field here
                    'source': 'koda'
                }

            # Query 2: Latest from shortlists
            query2 = """
                SELECT
                    s.user_id,
                    MAX(s.date_created) AS last_ts,
                    # Fetch conv_history and query associated with the MAX timestamp
                    (SELECT conv_history FROM shortlists si
                     WHERE si.user_id = s.user_id AND si.date_created = MAX(s.date_created) LIMIT 1) as conv_history_json_str,
                    (SELECT query FROM shortlists si
                     WHERE si.user_id = s.user_id AND si.date_created = MAX(s.date_created) LIMIT 1) as query_json_str
                FROM shortlists s
                WHERE DATE(s.date_created) = %s
                  AND s.conv_history IS NOT NULL AND s.conv_history != '' AND s.conv_history != '{}' # Ensure conv history exists
                GROUP BY s.user_id
            """
            cursor.execute(query2, (selected_date,))
            shortlist_results = cursor.fetchall()

            # Merge results, keeping only the absolute latest activity per user
            for row in shortlist_results:
                user_id = row['user_id']
                current_ts = row['last_ts']
                if user_id not in combined_activity or current_ts > combined_activity[user_id]['last_ts']:
                    combined_activity[user_id] = {
                        'last_ts': current_ts,
                        'conv_history_str': row.get('conv_history_json_str'),
                        'query_str': row.get('query_json_str'), # Store query if latest from shortlist
                        'source': 'shortlist'
                    }

        # Now fetch usernames/phones for the relevant user IDs
        final_user_list = []
        user_ids = list(combined_activity.keys())

        if user_ids:
            # Fetch user details in bulk
            user_details_map = {}
            query_users = """
                SELECT userid, username, phone
                FROM users_latest_state
                WHERE userid IN %s
            """
            with conn.cursor() as cursor:
                 # Ensure user_ids is not empty before executing
                if user_ids:
                     cursor.execute(query_users, (user_ids,))
                     uls_results = cursor.fetchall()
                     for uls_row in uls_results:
                         user_details_map[uls_row['userid']] = uls_row

            # Construct final list
            for user_id, activity_data in combined_activity.items():
                user_info = user_details_map.get(user_id, {})
                final_user_list.append({
                    'user_id': user_id,
                    'username': user_info.get('username', 'N/A'),
                    'phone': user_info.get('phone', 'N/A'),
                    'overall_latest_ts': activity_data['last_ts'],
                    'latest_conv_history_str': activity_data['conv_history_str'],
                    'latest_query_json_str': activity_data['query_str'], # Will be None if latest source was 'koda'
                    'latest_source': activity_data['source']
                })

            # Sort by latest timestamp descending
            final_user_list.sort(key=lambda x: x['overall_latest_ts'], reverse=True)


    except pymysql.Error as e:
        logging.error(f"DB Error fetching combined chat users for date {selected_date}: {e}")
        final_user_list = [] # Return empty list on error
    except Exception as e:
        logging.error(f"Unexpected error fetching combined chat users for date {selected_date}: {e}")
        final_user_list = []
    finally:
        if conn: conn.close()

    return final_user_list


def get_latest_shortlist_details(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the absolute latest shortlist entry for a user and parses
    the query JSON and extracts top 5 courses from the shortlist JSON.

    Args:
        user_id: The user's ID.

    Returns:
        A dictionary containing 'query_profile_data' and
        'top_shortlisted_courses', or None if no shortlist found or on error.
    """
    conn = get_connection()
    if not conn: return None

    shortlist_details = None
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT
                    query as query_json_str,
                    shortlist as shortlist_json_str
                FROM shortlists
                WHERE user_id = %s
                ORDER BY date_created DESC
                LIMIT 1
            """
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()

        if result:
            shortlist_details = {}
            query_data = {}
            top_courses = []

            # Parse 'query' JSON
            try:
                query_json_str = result.get('query_json_str', '{}') or '{}'
                query_data = json.loads(query_json_str)
                # Filter out internal/unwanted keys if necessary
                keys_to_exclude = {'isDeFault', 'isSelectedCareer', 'isSelectedCountry', 'isSelectedCourse', 'shortlist_id', 'user_id', 'dateStrings'}
                query_profile_data_filtered = {k: v for k, v in query_data.items() if k not in keys_to_exclude and v is not None}
                shortlist_details['query_profile_data'] = query_profile_data_filtered

            except json.JSONDecodeError as e:
                logging.warning(f"Failed to parse query JSON for user {user_id}'s latest shortlist (details fetch): {e}")
                shortlist_details['query_profile_data'] = {'error': 'parse_failed'}


            # Parse 'shortlist' JSON and extract top 5 courses (using robust logic)
            try:
                shortlist_json_str = result.get('shortlist_json_str', '{}') or '{}'
                shortlist_data = json.loads(shortlist_json_str)
                all_courses = []
                if isinstance(shortlist_data, dict):
                    for current_uni_id, courses_list in shortlist_data.items():
                        if isinstance(courses_list, list):
                            for course in courses_list:
                                if isinstance(course, dict):
                                    all_courses.append({'name': course.get('course_name', 'N/A'), 'university': course.get('university', 'N/A'), 'score': float(course.get('score', 0.0))})
                all_courses.sort(key=lambda x: x['score'], reverse=True)
                top_courses = all_courses[:5]
            except (json.JSONDecodeError, ValueError) as e:
                 logging.warning(f"Failed to parse shortlist JSON or scores for user {user_id}'s latest shortlist (details fetch): {e}")
                 # Simplified fallback (can enhance later if needed)
                 top_courses = [{'name': 'Error processing shortlist courses', 'university': '', 'score': 0.0}]

            shortlist_details['top_shortlisted_courses'] = top_courses

        else:
            logging.info(f"No shortlist record found at all for user {user_id} when fetching latest details.")


    except pymysql.Error as e:
        logging.error(f"DB Error fetching latest shortlist details for user {user_id}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error fetching latest shortlist details for user {user_id}: {e}")
    finally:
        if conn: conn.close()

    return shortlist_details


# --- can REMOVE/REPLACE `get_latest_shortlist_data_and_uni_name` ---
# This function is now superseded by the combination of
# get_combined_chat_users_on_date and get_latest_shortlist_details
# Remove its definition if it's no longer called anywhere else.