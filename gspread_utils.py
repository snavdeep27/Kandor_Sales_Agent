# gspread_utils.py

import gspread
from google.oauth2.service_account import Credentials
import streamlit as st
import logging
import os
import pandas as pd
import datetime
from typing import List, Dict, Optional, Tuple, Any

# --- Constants ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/16iNXwp9-TFUS0zPgvY3lobCWDHtslYUp7KS-a_kVgWA/edit?usp=sharing"
WORKSHEET_NAME = "Sheet1" # Adjust if your worksheet has a different name
SERVICE_ACCOUNT_FILE_LOCAL = "/Users/navdeepsingh/Downloads/kandor-hosting-61cc4a4d9a4b.json" # Local path fallback

# Define the exact headers your sheet uses (case-sensitive)
EXPECTED_HEADERS = [
    "Userid", "PhoneNumber", "Plan_of_Action", "Current_Action_Date",
    "Next_Action_Date", "Current_Action_Medium", "Message"
]

# --- Authentication ---
@st.cache_resource(ttl=600) # Cache the client for 10 minutes
def get_gspread_client() -> Optional[gspread.Client]:
    """Authenticates with Google Sheets API using Service Account."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    creds = None
    try:
        # Try Streamlit secrets first
        if "gcp_service_account" in st.secrets:
            logging.info("Authenticating via Streamlit secrets (GCP Service Account)...")
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"], scopes=scopes
            )
            logging.info("Authentication via secrets successful.")
        # Fallback to local file if secrets not found (for local dev)
        elif os.path.exists(SERVICE_ACCOUNT_FILE_LOCAL):
            logging.info(f"Authenticating via local service account file: {SERVICE_ACCOUNT_FILE_LOCAL}")
            creds = Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE_LOCAL, scopes=scopes
            )
            logging.info("Authentication via local file successful.")
        else:
            st.error("Google Sheets credentials not found. Configure Streamlit secrets or check local file path.")
            logging.error("Credentials not found in secrets or local file.")
            return None

        client = gspread.authorize(creds)
        return client

    except Exception as e:
        st.error(f"Google Sheets Authentication Error: {e}")
        logging.error(f"gspread authentication failed: {e}", exc_info=True)
        return None

# In gspread_utils.py

# ... (other imports and functions like get_gspread_client) ...

# --- CORRECTED get_worksheet function ---
@st.cache_resource(ttl=600) # Cache the worksheet object
def get_worksheet(
    _client: gspread.Client, # Argument renamed with underscore for caching
    sheet_url: str = SHEET_URL,
    worksheet_name: str = WORKSHEET_NAME
) -> Optional[gspread.Worksheet]:
    """Opens the specified worksheet. Cache ignores the _client argument."""
    # Use the renamed argument inside the function body
    if not _client:                  # <<< CHANGED client to _client HERE
        logging.error("get_worksheet called with invalid client object.")
        return None
    try:
        logging.info(f"Opening Google Sheet URL: {sheet_url}")
        # Use the renamed argument here too
        spreadsheet = _client.open_by_url(sheet_url) # <<< CHANGED client to _client HERE
        worksheet = spreadsheet.worksheet(worksheet_name)
        logging.info(f"Successfully opened worksheet: {worksheet_name}")
        # Validate headers (optional but good practice)
        headers = worksheet.row_values(1)
        if headers != EXPECTED_HEADERS:
             logging.warning(f"Worksheet headers ({headers}) do not match expected headers ({EXPECTED_HEADERS}). Check sheet structure.")
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Error: Google Sheet not found at URL: {sheet_url}")
        logging.error(f"SpreadsheetNotFound: {sheet_url}")
        return None
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Error: Worksheet '{worksheet_name}' not found in the Google Sheet.")
        logging.error(f"WorksheetNotFound: {worksheet_name}")
        return None
    except Exception as e:
        st.error(f"Error opening Google Sheet/Worksheet: {e}")
        logging.error(f"Error opening sheet/worksheet: {e}", exc_info=True)
        return None

# ... (rest of gspread_utils.py) ...
# --- Read Operations ---
# @st.cache_data(ttl=60) # Cache data for 1 minute
def get_all_followups(worksheet: gspread.Worksheet) -> List[Dict[str, Any]]:
    """Gets all rows from the worksheet as a list of dictionaries."""
    if not worksheet: return []
    try:
        logging.info(f"Fetching all records from worksheet '{worksheet.title}'...")
        # Using get_all_records assumes first row is header
        records = worksheet.get_all_records()
        logging.info(f"Fetched {len(records)} records.")
        # Convert date strings if needed (gspread might handle this, check output)
        for record in records:
            for date_col in ["Current_Action_Date", "Next_Action_Date"]:
                if date_col in record and isinstance(record[date_col], str):
                    # Attempt to parse common date formats, handle empty strings
                    if record[date_col]:
                        try:
                            # Try parsing common formats, add more if needed
                            parsed_date = None
                            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y"): # Add expected formats
                                try:
                                    parsed_date = datetime.datetime.strptime(record[date_col], fmt).date()
                                    break
                                except ValueError:
                                    continue
                            if parsed_date:
                                record[date_col] = parsed_date
                            else: # Keep as string if parsing fails
                                logging.warning(f"Could not parse date string '{record[date_col]}' in column {date_col}. Keeping as string.")
                        except Exception as e:
                            logging.warning(f"Error parsing date {record[date_col]} in {date_col}: {e}. Keeping as string.")
                    else:
                        record[date_col] = None # Convert empty string to None

        return records
    except Exception as e:
        st.error(f"Error reading data from Google Sheet: {e}")
        logging.error(f"Error in get_all_followups: {e}", exc_info=True)
        return []

def get_followups_due_today(worksheet: gspread.Worksheet) -> List[Dict[str, Any]]:
    """Filters all followups to get records where Next_Action_Date is today."""
    all_records = get_all_followups(worksheet)
    if not all_records: return []

    today = datetime.date.today()
    due_today = []
    logging.info(f"Filtering for records due today: {today.isoformat()}")

    for record in all_records:
        next_action_date = record.get("Next_Action_Date")
        # Ensure comparison is between date objects
        if isinstance(next_action_date, datetime.date):
            if next_action_date == today:
                due_today.append(record)
        elif isinstance(next_action_date, str) and next_action_date: # Try parsing again if needed
            try:
                parsed_date = datetime.datetime.strptime(next_action_date, "%Y-%m-%d").date() # Assuming YYYY-MM-DD
                if parsed_date == today:
                     due_today.append(record)
            except ValueError:
                logging.warning(f"Could not compare date string '{next_action_date}' for 'due today' check.")

    logging.info(f"Found {len(due_today)} records due today.")
    return due_today

def find_followup_by_phone(worksheet: gspread.Worksheet, phone_number: str) -> Optional[Tuple[Dict[str, Any], int]]:
    """Finds the first row matching a phone number. Returns (data_dict, row_index)."""
    if not worksheet or not phone_number: return None
    try:
        logging.info(f"Searching for phone number: {phone_number}")
        # Using find - might be slow on large sheets without index
        # Ensure phone number format matches sheet (e.g., +91 prefix?)
        cell = worksheet.find(phone_number, in_column=EXPECTED_HEADERS.index("PhoneNumber") + 1) # Find in PhoneNumber column (1-based index)
        if cell:
            row_index = cell.row
            # Get all values in that row, then zip with headers
            row_values = worksheet.row_values(row_index)
            headers = worksheet.row_values(1) # Get headers again
            data_dict = dict(zip(headers, row_values))
            logging.info(f"Found record for {phone_number} at row {row_index}")
             # Convert dates for consistency
            for date_col in ["Current_Action_Date", "Next_Action_Date"]:
                 if date_col in data_dict and isinstance(data_dict[date_col], str) and data_dict[date_col]:
                      try: data_dict[date_col] = datetime.datetime.strptime(data_dict[date_col], "%Y-%m-%d").date()
                      except ValueError: pass # Keep as string if format is wrong
                 elif date_col in data_dict and not data_dict[date_col]: data_dict[date_col] = None # Handle empty string
            return data_dict, row_index
        else:
            logging.info(f"No record found for phone number: {phone_number}")
            return None
    except Exception as e:
        st.error(f"Error finding record by phone number: {e}")
        logging.error(f"Error in find_followup_by_phone for {phone_number}: {e}", exc_info=True)
        return None


# --- Write Operations ---

def update_followup(worksheet: gspread.Worksheet, row_index: int, data_dict: Dict[str, Any]) -> bool:
    """Updates an existing row in the worksheet using its index."""
    if not worksheet or not row_index: return False
    try:
        # Ensure data is ordered correctly according to headers
        headers = EXPECTED_HEADERS
        # Format dates as strings for Sheets ('YYYY-MM-DD')
        data_dict['Current_Action_Date'] = datetime.date.today().isoformat() # Set current date on update
        if isinstance(data_dict.get('Next_Action_Date'), datetime.date):
            data_dict['Next_Action_Date'] = data_dict['Next_Action_Date'].isoformat()
        elif data_dict.get('Next_Action_Date') is None:
             data_dict['Next_Action_Date'] = '' # Use empty string for None dates

        # Create list in header order, handling missing keys
        row_values = [data_dict.get(header, '') for header in headers]

        logging.info(f"Updating row {row_index} with data: {row_values}")
        worksheet.update(f'A{row_index}', [row_values]) # Update entire row starting from column A
        logging.info(f"Row {row_index} updated successfully.")
        return True
    except Exception as e:
        st.error(f"Error updating Google Sheet row {row_index}: {e}")
        logging.error(f"Error in update_followup for row {row_index}: {e}", exc_info=True)
        return False


def add_followup(worksheet: gspread.Worksheet, data_dict: Dict[str, Any]) -> bool:
    """Appends a new row to the worksheet."""
    if not worksheet: return False
    try:
        headers = EXPECTED_HEADERS
        # Format dates as strings ('YYYY-MM-DD')
        data_dict['Current_Action_Date'] = datetime.date.today().isoformat() # Set current date on add
        if isinstance(data_dict.get('Next_Action_Date'), datetime.date):
            data_dict['Next_Action_Date'] = data_dict['Next_Action_Date'].isoformat()
        elif data_dict.get('Next_Action_Date') is None:
             data_dict['Next_Action_Date'] = ''

        # Ensure all headers are present, provide default empty string if not
        row_values = [data_dict.get(header, '') for header in headers]

        logging.info(f"Appending new row with data: {row_values}")
        worksheet.append_row(row_values, value_input_option='USER_ENTERED') # USER_ENTERED tries to interpret types
        logging.info("New row appended successfully.")
        return True
    except Exception as e:
        st.error(f"Error adding row to Google Sheet: {e}")
        logging.error(f"Error in add_followup: {e}", exc_info=True)
        return False