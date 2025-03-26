import streamlit as st
import json
from dotenv import load_dotenv
from io import BytesIO
from fpdf import FPDF

load_dotenv()  # Load .env for environment variables

from db_connection import (
    get_user_by_phone,
    get_shortlists_by_user
)
from usecase_templates import generate_all_use_cases
from rag_utils import create_bedrock_rag_chain, do_rag_query

def generate_pdf_report(report_text: str) -> bytes:
    """
    Converts report text into a multi-page PDF, returning as bytes.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)

    for line in report_text.split("\n"):
        pdf.multi_cell(0, 10, txt=line, align="L")

    pdf_output = pdf.output(dest="S").encode("latin-1")
    return pdf_output

def main():
    st.title("AI Study Abroad Counselor - Demo (Bedrock)")

    # Set up session state for user data if it doesn't exist yet
    if "user_data" not in st.session_state:
        st.session_state["user_data"] = None
    if "shortlists" not in st.session_state:
        st.session_state["shortlists"] = None
    if "report_text" not in st.session_state:
        st.session_state["report_text"] = ""

    # 1) Input user phone
    phone_number = st.text_input("Enter Phone (with country code)", value="+919999999999")

    # Button to load user data
    if st.button("Load User Data"):
        if not phone_number:
            st.warning("Please enter a phone number.")
        else:
            user_data = get_user_by_phone(phone_number)
            if not user_data:
                st.error("No user found with that phone.")
            else:
                st.session_state["user_data"] = user_data
                user_id = user_data.get("id") or user_data.get("userid")
                if user_id:
                    shortlists = get_shortlists_by_user(user_id)
                    st.session_state["shortlists"] = shortlists
                else:
                    st.session_state["shortlists"] = None
                st.success("User data loaded successfully!")

    # Check if we have user data in session
    if st.session_state["user_data"]:
        user_data = st.session_state["user_data"]
        full_name = user_data.get("username", "N/A").strip()
        user_email = user_data.get("usermail", "N/A")
        dream_country = user_data.get("DreamCountry", "N/A")
        contact = user_data.get("phone", "N/A")

        st.markdown(f"**Name:** {full_name}")
        st.markdown(f"**Email:** {user_email}")
        st.markdown(f"**Target Country:** {dream_country}")
        st.markdown(f"**Contact:** {contact}")

        # Show shortlists if any
        if st.session_state["shortlists"]:
            st.subheader("Shortlists (from 'shortlists'):")
            for sl in st.session_state["shortlists"]:
                st.write(f"Shortlist ID: {sl['id']}, Date: {sl['date_created']}")
        else:
            st.info("No shortlists found for this user.")

        st.write("---")
        # 2) Generate 30 messages
        st.subheader("Generate 30 Messages")
        if st.button("Generate 30 Messages"):
            messages = generate_all_use_cases(user_data)
            st.subheader("Generated Messages:")
            for i, msg in enumerate(messages, start=1):
                st.markdown(f"**Message {i}:** {msg}")

        st.write("---")

        # 3) RAG Query (AI Counselor)
        st.subheader("AI Research / RAG Query (via Bedrock KB)")
        knowledge_base_id = st.text_input("Knowledge Base ID", value="F0K2JEBKE8")
        top_k = st.number_input("Number of documents to retrieve (Top K)", min_value=1, max_value=10, value=3)
        user_query = st.text_area("Ask the AI Counselor something about study abroad:")

        if st.button("Get Answer"):
            rag_chain = create_bedrock_rag_chain(
                knowledge_base_id=knowledge_base_id,
                top_k=top_k
            )
            answer = do_rag_query(rag_chain, user_query, user_profile=user_data)
            st.write("**AI Counselor's Answer:**")
            st.write(answer)

        st.write("---")

        # 4) Personalized Report
        st.subheader("Generate Personalized Report")
        extra_notes = st.text_area(
            "Any extra notes/information from your chat with the user",
            help="These notes will be included in the final multi-page report."
        )

        if st.button("Preview Report"):
            rag_chain = create_bedrock_rag_chain(
                knowledge_base_id="F0K2JEBKE8",
                top_k=5
            )
            profile = {
                "username": full_name,
                "usermail": user_email,
                "DreamCountry": dream_country,
                "phone": contact
            }
            prompt_for_report = f"""
Please generate a thorough 3-4 page style report covering:
1) Career options for the user, typical salaries, and job counts
2) Various course specializations possible in {dream_country}
3) 6-7 potential colleges with requirements/deadlines
4) Visa policies for the user’s profession in {dream_country}
5) Path to permanent residency
6) Estimated total cost of education
7) Scholarships available

Additional notes from counselor: {extra_notes}
            """.strip()

            report_text = do_rag_query(rag_chain, prompt_for_report, user_profile=profile)
            st.session_state["report_text"] = report_text

        # If we have a generated report, show a preview
        if st.session_state["report_text"]:
            st.subheader("Report Preview")
            st.text_area("Preview:", value=st.session_state["report_text"], height=300)

            if st.button("Export to PDF"):
                pdf_bytes = generate_pdf_report(st.session_state["report_text"])
                st.download_button(
                    label="Download PDF",
                    data=pdf_bytes,
                    file_name="personalized_report.pdf",
                    mime="application/pdf"
                )

    else:
        # If no user data in session, prompt user to load it
        st.info("Please enter phone and click 'Load User Data' to proceed.")


if __name__ == "__main__":
    main()
