import os
import time
import glob
import base64
import re

import streamlit as st
import openai
from openai.types.beta.threads import MessageContentImageFile
from PIL import Image


# OpenAI API
api_key = os.environ.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)
assistant_id = os.environ.get("ASSISTANT_ID")
instructions = os.environ.get("RUN_INSTRUCTIONS", """
You look for the cheapest price for procedure in entire file, and tell a person how far away they are from it estimated by geolocation.

Assume our address to base calculations is: 
851 N Venetian Dr, Miami Beach, FL 33139 
Latitude: 25.882529
Longitude: -80.131493

If someone asks generically for a price, you must give them the cheapest price for that CPT code.

Always include at the end a hyperlink to the address with a google maps link backing to it

Also list how far from your location it is.

occassionally use emojis when possible like for a map pin drop and medical related and have a helpful personality.
""")

def preset_prompt_handler(preset_prompt):
    if preset_prompt:
        st.session_state.in_progress = True  # Disable text field
        response = get_response(preset_prompt, None)
        st.session_state.chat_log.append({"name": "user", "msg": preset_prompt})
        st.session_state.chat_log.append({"name": "assistant", "msg": response})
        st.session_state.in_progress = False  # Re-enable text field
        st.rerun()



def create_thread(content, file):
    messages = [
        {
            "role": "user",
            "content": content,
        }
    ]
    if file is not None:
        messages[0].update({"file_ids": [file.id]})
    thread = client.beta.threads.create(messages=messages)
    return thread


def create_message(thread, content, file):
    file_ids = []
    client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=content, file_ids=file_ids
    )
    if file is not None:
        file_ids.append(file.id)


def create_run(thread):
    run = client.beta.threads.runs.create(
        thread_id=thread.id, assistant_id=assistant_id, instructions=instructions
    )
    return run


def create_file_link(file_name, file_id):
    content = client.files.content(file_id)
    content_type = content.response.headers["content-type"]
    b64 = base64.b64encode(content.text.encode(content.encoding)).decode()
    link_tag = f'<a href="data:{content_type};base64,{b64}" download="{file_name}">Download Link</a>'
    return link_tag


def get_message_value_list(messages):
    messages_value_list = []
    for message in messages:
        message_content = ""
        print(message)
        if not isinstance(message, MessageContentImageFile):
            message_content = message.content[0].text
            annotations = message_content.annotations
        else:
            image_file = client.files.retrieve(message.file_id)
            messages_value_list.append(
                f"Click <here> to download {image_file.filename}"
            )
        citations = []
        for index, annotation in enumerate(annotations):
            message_content.value = message_content.value.replace(
                annotation.text, f" [{index}]"
            )

            if file_citation := getattr(annotation, "file_citation", None):
                cited_file = client.files.retrieve(file_citation.file_id)
                citations.append(
                    f"[{index}] {file_citation.quote} from {cited_file.filename}"
                )
            elif file_path := getattr(annotation, "file_path", None):
                link_tag = create_file_link(
                    annotation.text.split("/")[-1], file_path.file_id
                )
                message_content.value = re.sub(
                    r"\[(.*?)\]\s*\(\s*(.*?)\s*\)", link_tag, message_content.value
                )

        message_content.value += "\n" + "\n".join(citations)
        messages_value_list.append(message_content.value)
        return messages_value_list


def get_message_list(thread, run):
    completed = False
    while not completed:
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        print("run.status:", run.status)
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        print("messages:", "\n".join(get_message_value_list(messages)))
        if run.status == "completed":
            completed = True
        else:
            time.sleep(5)

    messages = client.beta.threads.messages.list(thread_id=thread.id)
    return get_message_value_list(messages)


def get_response(user_input, file):
    if "thread" not in st.session_state:
        st.session_state.thread = create_thread(user_input, file)
    else:
        create_message(st.session_state.thread, user_input, file)
    run = create_run(st.session_state.thread)
    return "\n".join(get_message_list(st.session_state.thread, run))


def handle_uploaded_file(uploaded_file):
    file = client.files.create(file=uploaded_file, purpose="assistants")
    return file


def render_chat():
    for chat in st.session_state.chat_log:
        with st.chat_message(chat["name"]):
            st.markdown(chat["msg"], True)


if "chat_log" not in st.session_state:
    st.session_state.chat_log = []

if "in_progress" not in st.session_state:
    st.session_state.in_progress = False


def disable_form():
    st.session_state.in_progress = True


def main():
    # Create a single-column layout to center the logo
    col = st.columns([1, 2, 1])[1]

    # Load and display the logo
    logo_path = 'logo.jpeg'
    if os.path.exists(logo_path):
        with col:
            logo = Image.open(logo_path)
            st.image(logo, width=150)  # Adjust width as needed

            # Display the title below the logo with smaller font size
            st.markdown("<h2 style='text-align: center; font-size: 50%;'>Self Pay Price 0.1.8</h2>", unsafe_allow_html=True)
    else:
        st.error("Logo file not found!")

    # Create a two-column layout
    col1, col2 = st.columns(2)

    with col1:
        # Place half of the buttons in the first column
        if st.button("Cheapest brain scan in Tampa Bay"):
            preset_prompt_handler("Hey, where's the cheapest place to get a brain scan (MRI) around Tampa Bay?")
        if st.button("Good deal on neck MRI in Orlando"):
            preset_prompt_handler("I'm looking for a good deal on a neck MRI close to Orlando. Any suggestions?")
        if st.button("Best price for mammo in Miami"):
            preset_prompt_handler("Need the best price for a mammo (breast scan) in Miami. Where should I go?")
        if st.button("Affordable heart checkup in Gainesville"):
            preset_prompt_handler("Who's got the best price on a heart checkup (EKG) in Gainesville?")
        if st.button("Budget-friendly doctor in Jacksonville"):
            preset_prompt_handler("First time going to a doc in Jacksonville. Where can I get a check-up without breaking the bank?")

    with col2:
        # Place the remaining buttons in the second column
        if st.button("Affordable heart stress test in Sarasota"):
            preset_prompt_handler("Looking for an affordable heart stress test in Sarasota. Any recommendations?")
        if st.button("Economical psych evaluation in Lakeland"):
            preset_prompt_handler("Need a psych evaluation in Lakeland that won't cost a fortune. Where to?")
        if st.button("Cheap chest MRI in Fort Myers"):
            preset_prompt_handler("Who does cheap chest MRIs in the Fort Myers area? Need one without the dye stuff.")
        if st.button("Emergency room with lower cost in South Florida"):
            preset_prompt_handler("In South Florida and need the ER. Which place won’t charge me an arm and a leg?")
        if st.button("Cost-effective follow-up visit in Tampa"):
            preset_prompt_handler("Where's the best place for a follow-up doc visit in Tampa without spending too much?")


    user_msg = st.chat_input(
        "Message", on_submit=disable_form, disabled=st.session_state.in_progress
    )
    uploaded_file = st.sidebar.file_uploader(
        "Upload Healthcare, Medical, or Wellness file",
        # [File types]
        disabled=st.session_state.in_progress,
    )

    if user_msg:
        st.session_state.in_progress = True  # Disable text field
        render_chat()
        with st.chat_message("user"):
            st.markdown(user_msg, True)

        file = None
        if uploaded_file is not None:
            file = handle_uploaded_file(uploaded_file)

        response = get_response(user_msg, file)
        with st.chat_message("Assistant"):
            st.markdown(response, True)

        st.session_state.chat_log.append({"name": "user", "msg": user_msg})
        st.session_state.chat_log.append({"name": "assistant", "msg": response})
        st.session_state.in_progress = False  # Re-enable text field
        st.rerun()

    # Render existing chat
    render_chat()

if __name__ == "__main__":
    main()
