from google import genai
from google.genai import types
import streamlit as st
from twilio.rest import Client as TwilioClient
from prompt import SYSTEM_PROMPT, WELCOME_MESSAGE_TEMPLATE, SUMMARY_REQUEST_PROMPT





GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
TWILIO_ACCOUNT_SID = st.secrets["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_FROM = st.secrets["TWILIO_WHATSAPP_FROM"]
TWILIO_CONTENT_SID = st.secrets["TWILIO_CONTENT_SID"]


@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=GEMINI_API_KEY)

@st.cache_resource
def get_twilio_client():
    return TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

twilio_client = get_twilio_client()


gemini_client = get_gemini_client()
MODEL_NAME = "gemini-3.5-flash"

def clean_whatsapp_text(text):
    if not text:
        return "No nutrition summary available."
    text = " ".join(text.split())  # collapse whitespace/newlines
    return text[:1500] + "..." if len(text) > 1500 else text


def send_summary_to_phone(user_name,to_phone_number,summary):

    # Content template expects {{1}} = name, {{2}} = summary.
    try:
        content_variables = st.json.dumps(
            {"1": user_name, "2": clean_whatsapp_text(summary)}, ensure_ascii=False
        )
        message = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{to_phone_number}",
            content_sid=TWILIO_CONTENT_SID,
            content_variables=content_variables,
        )
        return True, message.sid
    except Exception as error:
        return False, str(error)

def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.markdown(message["content"])
        elif message["kind"] == "image":
            st.image(message["content"])


def add_message(role, kind, content):
    st.session_state.messages.append({"role": role, "kind": kind, "content": content})
    render_message(st.session_state.messages[-1])


def ask_gemini(parts):
    try:
        return st.session_state.chat.send_message(parts).text
    except Exception as error:
        return f"Sorry, something went wrong: {error}"

    
# step 1: onboarding (username and phone number)
if 'onboarded' not in st.session_state:
    st.title("StudyToTop 📚")
    st.caption("Snap & Study")

    with st.form("onboarding_form"):
        st.subheader("Welcome to StudyToTop! Let's get you started.")
        name = st.text_input("What's your name?")
        phone_number = st.text_input("What's your phone number?")

        submitted = st.form_submit_button("start new journey")
        if submitted:
            if not name or not phone_number:
                st.error("Please fill in both fields.")
            else:
                st.session_state['name'] = name.strip()
                st.session_state['phone_number'] = phone_number.strip()
                st.session_state.chat = gemini_client.chats.create(
                    model=MODEL_NAME,
                    config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
                )
                st.session_state.messages = []
                st.session_state['onboarded'] = True
                st.success(f"Thanks {name}! You're all set to start studying.")
                st.rerun()  # Rerun the app to show the main interface
            st.stop()  # Stop the app to show the main interface

# create a chat interface for the user to interact with the AI study buddy
header_col, button_col = st.columns([5, 2], vertical_alignment="center")
 
with header_col:
    st.title("StudyToTop 📚")
 
with button_col:
    send_disabled = len(st.session_state.messages) <= 2
    if st.button("📤 Send to WhatsApp", disabled=send_disabled, use_container_width=True):
        with st.spinner("Summarizing your day..."):
            summary = ask_gemini([SUMMARY_REQUEST_PROMPT])
        success, info = send_summary_to_phone(st.session_state.phone_number, st.session_state.name, summary)
        if success:
            st.success("Sent! Check your WhatsApp 📲")
        else:
            st.error(f"Couldn't send that: {info}")

st.caption(f"Logged in as {st.session_state.name} - updates go to {st.session_state.phone_number}")

if not st.session_state.messages:
    add_message("assistant", "text", WELCOME_MESSAGE_TEMPLATE.format(name=st.session_state['name']))
else:
    for message in st.session_state.messages:
        render_message(message)

user_input = st.chat_input(
    "Type your question or upload an image here...",
    accept_file=True,
    file_type=["png", "jpg", "jpeg", "pdf"],
)

if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text.strip()
    parts = []

    if photo is not None:
        photo_bytes = photo.getvalue()
        add_message("user", "image", photo_bytes)
        parts.append(types.Part.from_bytes(data=photo_bytes, mime_type=photo.type))

    if text:
        add_message("user", "text", text)
        parts.append(text)
    elif photo is not None:
        parts.append("Please explain the content of the uploaded image.")

    with st.spinner("Generating explanation..."):
        answer = ask_gemini(parts)
    add_message("assistant", "text", answer)
