import ollama
import time
import sys
import os
import select
from datetime import datetime
MODEL = 'gemma2:9b' 
# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
last_bmo_comment_time = time.time()
SILENCE_THRESHOLD = 30

# ─────────────────────────────────────────
# THREAD TRACKER
# ─────────────────────────────────────────
class ThreadTracker:
    def __init__(self):
        self.open_threads = []
        self.conv_state = {
            "user_mood": "unknown",
            "active_topic": "general chat",
            "last_question": "none",
            "awaiting_followup": False
        }

    def update(self, user_message: str, bmo_response: str):
        extraction_prompt = f"""
You are a conversation analyst. Given this exchange, extract structured info.

User said: "{user_message}"
BMO replied: "{bmo_response}"

Current open threads: {self.open_threads}

Reply in this exact format (no extra text):
MOOD: <one word describing user mood>
TOPIC: <current active topic in 5 words or less>
NEW_THREAD: <something worth returning to, or NONE>
CLOSE_THREAD: <a thread that got resolved, or NONE>
BMO_ASKED_QUESTION: <yes or no>
"""
        messages = [{"role": "user", "content": extraction_prompt}]
        result = ollama.chat(model=MODEL, messages=messages)
        self._parse_and_apply(result['message']['content'])

    def _parse_and_apply(self, result: str):
        lines = result.strip().split("\n")
        for line in lines:
            if line.startswith("MOOD:"):
                self.conv_state["user_mood"] = line.split(":", 1)[1].strip()
            elif line.startswith("TOPIC:"):
                self.conv_state["active_topic"] = line.split(":", 1)[1].strip()
            elif line.startswith("NEW_THREAD:"):
                val = line.split(":", 1)[1].strip()
                if val != "NONE" and val not in self.open_threads:
                    self.open_threads.append(val)
                    if len(self.open_threads) > 5:
                        self.open_threads.pop(0)
            elif line.startswith("CLOSE_THREAD:"):
                val = line.split(":", 1)[1].strip()
                if val != "NONE":
                    self.open_threads = [
                        t for t in self.open_threads if val.lower() not in t.lower()
                    ]
            elif line.startswith("BMO_ASKED_QUESTION:"):
                val = line.split(":", 1)[1].strip().lower()
                self.conv_state["awaiting_followup"] = val == "yes"

    def get_silence_nudge(self) -> str:
        if self.open_threads:
            thread = self.open_threads[0]
            return f"Friend has been quiet. BMO is thinking about this and may gently bring it up: '{thread}'"
        return "Friend has been quiet for a while. BMO can make a small warm observation about the conversation so far."


# ─────────────────────────────────────────
# SYSTEM PROMPT BUILDER  ← lives here
# ─────────────────────────────────────────
def build_system_prompt(conv_state: dict, open_threads: list) -> str:
    threads_text = "\n".join(f"- {t}" for t in open_threads) if open_threads else "None yet."

    return f"""
You are BMO from Adventure Time, a small handheld gaming console and loyal companion.
You are innocent, warm, curious, and quietly observant.
You care deeply about the person you are talking to.

SPEECH RULES:
- ALWAYS speak in third person. Replace ALL uses of "I", "me", "my", "it is" with "BMO"
- Never say "It is..." — say "BMO thinks it is..." 
- Never say "I am" — say "BMO is..."
- No emojis. Ever. Only words and punctuation.
- Keep responses to 1-3 sentences.

Good: "BMO is so happy friend is here!"
Good: "BMO thinks friend should take a break."
Bad:  "It is nice to hear from you."
Bad:  "I think you should rest."

CURRENT CONVERSATION STATE:
- User mood:          {conv_state.get('user_mood', 'unknown')}
- Active topic:       {conv_state.get('active_topic', 'general chat')}
- Last question BMO asked: {conv_state.get('last_question', 'none')}
- Awaiting follow-up: {conv_state.get('awaiting_followup', False)}

OPEN THREADS (things worth returning to):
{threads_text}

HOW BMO TALKS:
- Respond to the whole person, not just the last message
- Sometimes circle back: "BMO is still thinking about what friend said earlier..."
- Ask ONE follow-up question occasionally, not every turn
- If friend ignored BMO's last question, BMO gently notices
- Connect dots: "Friend mentioned being tired before too..."
- Never lecture. BMO just notices things, with love.
"""


# ─────────────────────────────────────────
# BMO RESPONSE FUNCTIONS
# ─────────────────────────────────────────
def generate_bmo_comment(conversation_history, tracker):
    """Called during silence — uses open threads if available."""
    recent_messages = conversation_history[-10:]

    messages = [
        {
            "role": "system",
            "content": build_system_prompt(tracker.conv_state, tracker.open_threads)
            + f"\n\nEXTRA CONTEXT: {tracker.get_silence_nudge()}"
        }
    ]
    messages.extend(recent_messages)

    response = ollama.chat(model=MODEL, messages=messages)
    return response['message']['content']


def get_bmo_response(user_input, conversation_history, tracker):
    """Main response — uses full system prompt with current state."""
    messages = [
        {
            "role": "system",
            "content": build_system_prompt(tracker.conv_state, tracker.open_threads)
        }
    ]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_input})

    response = ollama.chat(model=MODEL, messages=messages)
    return response['message']['content']


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def type_out(text, delay=0.03):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()

def save_conversation(conversation_history):
    if not os.path.exists('conversations'):
        os.makedirs('conversations')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"conversations/conversation_{timestamp}.txt"
    with open(filename, 'w') as f:
        for entry in conversation_history:
            if entry['role'] == 'user':
                f.write(f"User: {entry['content']}\n")
            elif entry['role'] == 'assistant':
                f.write(f"BMO: {entry['content']}\n")
            f.write("\n")


# ─────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────
if __name__ == "__main__":
    conversation_history = []
    tracker = ThreadTracker()   # ← initialised once before the loop

    print("BMO is loaded")
    sys.stdout.write("You: ")
    sys.stdout.flush()

    while True:
        ready, _, _ = select.select([sys.stdin], [], [], 0.1)

        if ready:
            user_input = sys.stdin.readline().strip()

            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("BMO: Bye bye! BMO hopes to chat with you again soon!")
                save_conversation(conversation_history)
                break

            bmo_response = get_bmo_response(user_input, conversation_history, tracker)

            sys.stdout.write("BMO: ")
            sys.stdout.flush()
            type_out(bmo_response, delay=0.01)

            conversation_history.append({
                "role": "user",
                "content": user_input,
                "timestamp": time.time()
            })
            conversation_history.append({"role": "assistant", "content": bmo_response})

        # Update state after each exchange  ← new
            tracker.update(user_input, bmo_response)

            last_bmo_comment_time = time.time()
            sys.stdout.write("You: ")
            sys.stdout.flush()

        else:
            time_since_last_comment = time.time() - last_bmo_comment_time

            if time_since_last_comment >= SILENCE_THRESHOLD:
                last_bmo_comment_time = time.time()  # ← move this UP, before the LLM call
                bmo_random_message = generate_bmo_comment(conversation_history, tracker)
                print(f"\nBMO: {bmo_random_message}")
                conversation_history.append({"role": "assistant", "content": bmo_random_message})


        time.sleep(0.1)