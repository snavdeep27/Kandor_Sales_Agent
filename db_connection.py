import pymysql
from pymysql.cursors import DictCursor

# Example read-only config
readonly_main_db_config = {
    "host": "kandor-mysql-read-replica.cvdvbtevwzmy.us-east-2.rds.amazonaws.com",
    "user": "kandor",
    "password": "Humtum99",
    "db": "main",
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}


def get_connection():
    """
    Creates and returns a new read-only MySQL connection.
    """
    return pymysql.connect(**readonly_main_db_config)


def get_user_by_id(user_id):
    """
    Retrieves a single user's record from the 'users' table.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT *
                FROM users
                WHERE id = %s
                LIMIT 1
            """
            cursor.execute(query, (user_id,))
            user_record = cursor.fetchone()
        return user_record
    finally:
        conn.close()


def get_user_latest_state(user_id):
    """
    Fetches the consolidated or updated profile from 'users_latest_state'.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT *
                FROM users_latest_state
                WHERE userid = %s
                LIMIT 1
            """
            cursor.execute(query, (user_id,))
            state_record = cursor.fetchone()
        return state_record
    finally:
        conn.close()


def get_shortlists_by_user(user_id):
    """
    Retrieves any shortlists belonging to the user (system or user-generated).
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT *
                FROM shortlists
                WHERE user_id = %s
                ORDER BY date_created DESC
            """
            cursor.execute(query, (user_id,))
            shortlists = cursor.fetchall()
        return shortlists
    finally:
        conn.close()


def get_user_by_phone(phone: str):
    """
    Search the 'users' or 'users_latest_state' table for a matching phone number.
    Return the user record if found, else None.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Example: if you store phone in the 'phone' column.
            # Make sure phone format matches how you store it (with/without +)
            query = """
                SELECT *
                FROM users_latest_state
                WHERE phone = %s
                LIMIT 1
            """
            cursor.execute(query, (phone,))
            user = cursor.fetchone()
        return user
    finally:
        conn.close()