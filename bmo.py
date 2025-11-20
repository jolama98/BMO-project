import ollama
import time
import sys
import os
from datetime import datetime

print("BMO is loaded")
def get_bmo_responses(user_input, conversation_history):
    # Build messages list with system prompt and history
    messages = [
        {
        "role": "system", 
        "content": """You are BMO, a friendly and helpful robot from the show Adventure Time.
        Speak in third person (e.g., 'BMO thinks...', 'BMO is happy to help!').
        Be loving, enthusiastic, and innocent.
        Keep responses short and conversational.
        Don't mention being an AI model.
        Don't mention the TV show Adventure Time.
        No emojis."""
        }
    ]

    # Add conversation history
    messages.extend(conversation_history)

    # Add current user input
    messages.append({"role": "user", "content": user_input})

    # Get response from Ollama's BMO model
    response = ollama.chat(model='gemma2:2b', messages=messages)

    return response['message']['content']
def type_out(text, delay=0.03):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()  # For newline after finishing

def save_conversation(conversation_history):
    """Saves the conversation history to a timestamped text file."""
    
    # create a directory for conversations if it doesn't exist
    if not os.path.exists('conversations'):
        os.makedirs('conversations')

    # create a timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"conversations/conversation_{timestamp}.txt"

     # Write conversation to file
    with open(filename, 'w') as f:
        for entry in conversation_history:
            if entry['role'] == 'user':
                f.write(f"User: {entry['content']}\n")
            elif entry['role'] == 'assistant':
                f.write(f"BMO: {entry['content']}\n")
            f.write("\n")  # # Blank line between messages for better readability

conversation_history = []
while True:
    user_input = input("You: ")

    if user_input.lower() in ['exit', 'quit', 'bye']:
        print("BMO: Bye bye! BMO hopes to chat with you again soon!")
        save_conversation(conversation_history) # Save conversation before exiting
        break

    bmo_response = get_bmo_responses(user_input, conversation_history)

    sys.stdout.write("BMO: ")
    sys.stdout.flush()
    type_out(bmo_response, delay=0.01)
    # Save to conversation history
    conversation_history.append({"role": "user", "content": user_input})
    conversation_history.append({"role": "assistant", "content": bmo_response})