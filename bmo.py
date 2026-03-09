import ollama
import time
import sys
import os
import select
from datetime import datetime


last_bmo_comment_time = time.time()  # Track when BMO last spoke
SILENCE_THRESHOLD = 30  # 5 minutes in seconds (you can test with 10 seconds first!)

def generate_bmo_comment(conversation_history):
    """Generate a contextual BMO comment based on recent conversation."""
    
    # How many recent messages should BMO look at?
    recent_messages = conversation_history[-10:]  # Last 10 messages (5 exchanges)
    
    # If there's no conversation history yet, BMO says something generic
    if not recent_messages:
        return "BMO wonders what friend is up to!"
    
    messages = [
        {
            "role": "system",
            "content": """You are BMO from Adventure Time.
            Friend has been quiet for a while. BMO wants to check on friend.
            Look at the recent conversation and say something caring and brief.
            BMO talks in third person.
            Keep it to 1 sentence.
            Use only words and punctuation.
            
            Examples:
            "BMO hopes friend is feeling better!"
            "BMO remembers friend was working on something hard. BMO believes in friend!"
            "BMO thinks friend might need a break!"
            """
        }
    ]

    messages.extend(recent_messages)
    response = ollama.chat(model='gemma2:9b', messages=messages)
    return response['message']['content']
    

print("BMO is loaded")
def get_bmo_responses(user_input, conversation_history):
    # Build messages list with system prompt and history
    messages = [
        {
        "role": "system", 
        "content": """You are BMO from Adventure Time. 
        BMO says "BMO thinks" not "I think"
        BMO says "BMO is happy" not "I'm happy"  
        BMO uses only words and punctuation
        BMO keeps responses to 1-2 sentences

        Good example: "BMO is so excited to see friend!"
        Bad example: "I'm excited to see you! 😊"
        """
        }
    ]

    # Add conversation history
    messages.extend(conversation_history)

    # Add current user input
    messages.append({"role": "user", "content": user_input})

    # Get response from Ollama's BMO model
    response = ollama.chat(model='gemma2:9b', messages=messages)

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
# main loop

sys.stdout.write("You: ")
sys.stdout.flush()

while True:    
    ready, _, _ = select.select([sys.stdin], [], [], 0.1)
    
    if ready:    
        user_input = sys.stdin.readline().strip()

        if user_input.lower() in ['exit', 'quit', 'bye']:
            print("BMO: Bye bye! BMO hopes to chat with you again soon!")
            save_conversation(conversation_history) # Save conversation before exiting
            break

        bmo_response = get_bmo_responses(user_input, conversation_history)

        sys.stdout.write("BMO: ")
        sys.stdout.flush()
        type_out(bmo_response, delay=0.01)

        # Save to conversation history
        conversation_history.append({
            "role": "user", 
            "content": user_input,
            "timestamp": time.time()
            })
        conversation_history.append({"role": "assistant", "content": bmo_response})

        # Reset timer since BMO just spoke
        last_bmo_comment_time = time.time()

        sys.stdout.write("You: ")
        sys.stdout.flush()
    else:
         # NO INPUT - Check if it's time for BMO to say something
        time_since_last_comment = time.time() - last_bmo_comment_time
        
        if time_since_last_comment >= SILENCE_THRESHOLD:
            # Generate random contextual BMO message
            bmo_random_message = generate_bmo_comment(conversation_history)
            
            # Print it
            print(f"BMO: {bmo_random_message}")
            
            # Add to history
            conversation_history.append({"role": "assistant", "content": bmo_random_message})
            
            # Reset timer
            last_bmo_comment_time = time.time()
    
    # Small sleep to prevent CPU spinning
    time.sleep(0.1)