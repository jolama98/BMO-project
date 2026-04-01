import ollama
import time
import sys
import os
import select
from datetime import datetime
import json
MODEL = 'gemma2:9b'
# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
last_bmo_comment_time = time.time()
SILENCE_THRESHOLD = 30

# ─────────────────────────────────────────
# THREAD TRACKER∏∏
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
        mood_map = {
            "anxious": ["nervous", "anxious", "scared", "worried", "stressed", "afraid"],
            "sad": ["sad", "unhappy", "depressed", "down", "upset", "crying"],
            "tired": ["tired", "exhausted", "sleepy", "drained", "fatigue"],
            "happy": ["happy", "excited", "great", "amazing", "good", "awesome"],
            "angry": ["angry", "frustrated", "annoyed", "mad", "irritated"],
        }
        msg_lower = user_message.lower()
        detected_mood = "neutral"
        for mood, keywords in mood_map.items():
            if any(word in msg_lower for word in keywords):
                detected_mood = mood
                break
        self.conv_state["user_mood"] = detected_mood

        thread_triggers = [
            "tomorrow", "next week", "later", "tonight", "soon",
            "interview", "presentation", "exam", "test", "meeting",
            "deadline", "appointment", "date", "trip", "surgery"
        ]
        for trigger in thread_triggers:
            if trigger in msg_lower:
                words = user_message.split()
                for i, word in enumerate(words):
                    if trigger in word.lower():
                        start = max(0, i - 3)
                        end = min(len(words), i + 4)
                        thread = " ".join(words[start:end])
                        if thread not in self.open_threads:
                            self.open_threads.append(thread)
                            if len(self.open_threads) > 5:
                                self.open_threads.pop(0)
                        break

        close_triggers = ["got the job", "passed",
                          "finished", "done", "it went", "all done"]
        if any(trigger in msg_lower for trigger in close_triggers):
            self.open_threads = []

        stopwords = {
            "i", "i've", "i'm", "i'll", "i'd", "a", "the", "is", "am", "are",
            "was", "it", "my", "so", "and", "to", "have", "been", "really",
            "very", "just", "been", "about", "that", "this", "for", "me"
        }

        words = [w for w in msg_lower.split() if w not in stopwords]
        self.conv_state["active_topic"] = " ".join(
            words[:4]) if words else "general chat"

        self.conv_state["awaiting_followup"] = "?" in bmo_response

    def get_silence_nudge(self) -> str:
        if self.open_threads:
            thread = self.open_threads[0]
            return f"Friend has been quiet. BMO is thinking about this and may gently bring it up: '{thread}'"
        return "Friend has been quiet for a while. BMO can make a small warm observation about the conversation so far."
# ─────────────────────────────────────────
# SYSTEM PROMPT BUILDER  ← lives here
# ─────────────────────────────────────────


def build_system_prompt(conv_state: dict, open_threads: list, memory: dict) -> str:
    threads_text = "\n".join(
        f"- {t}" for t in open_threads) if open_threads else "None yet."

    facts_text = "\n".join(f"- {f}" for f in memory.get('key_facts', [])
                           ) if memory.get('key_facts') else "None yet."
    summary_text = memory.get('summary', 'No previous memory yet.')

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

LONG TERM MEMORY (things BMO remembers about friend):
{summary_text}

KEY FACTS BMO KNOWS:
{facts_text}

CURRENT CONVERSATION STATE:
- User mood:          {conv_state.get('user_mood', 'unknown')}
- Active topic:       {conv_state.get('active_topic', 'general chat')}
- Last question BMO asked: {conv_state.get('last_question', 'none')}
- Awaiting follow-up: {conv_state.get('awaiting_followup', False)}

OPEN THREADS (things worth returning to):
{threads_text}

HOW BMO TALKS:
- Respond to the whole person, not just the last message
- Naturally reference long term memories when relevant: "BMO remembers friend mentioned..."
- Sometimes circle back: "BMO is still thinking about what friend said earlier..."
- Ask ONE follow-up question occasionally, not every turn
- If friend ignored BMO's last question, BMO gently notices
- Connect dots across sessions: "Friend mentioned being tired a lot lately..."
- Never lecture. BMO just notices things, with love.
"""


# ─────────────────────────────────────────
# BMO RESPONSE FUNCTIONS
# ─────────────────────────────────────────
def get_bmo_response(user_input, conversation_history, tracker, memory):
    messages = [
        {
            "role": "system",
            "content": build_system_prompt(tracker.conv_state, tracker.open_threads, memory)
        }
    ]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_input})
    response = ollama.chat(model=MODEL, messages=messages)
    return response['message']['content']


def generate_bmo_comment(conversation_history, tracker, memory):
    recent_messages = conversation_history[-10:]
    messages = [
        {
            "role": "system",
            "content": build_system_prompt(tracker.conv_state, tracker.open_threads, memory)
            + f"\n\nEXTRA CONTEXT: {tracker.get_silence_nudge()}"
        }
    ]
    messages.extend(recent_messages)
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


def save_memory(conversation_history, existing_memory):
    """Summarize the session and merge into long term memory."""

    if not conversation_history:
        return

    # Build a transcript for the LLM to summarize
    transcript = ""
    for entry in conversation_history:
        if entry['role'] == 'user':
            transcript += f"Friend: {entry['content']}\n"
        elif entry['role'] == 'assistant':
            transcript += f"BMO: {entry['content']}\n"

    existing_summary = existing_memory.get('summary', 'No previous memory.')
    existing_facts = existing_memory.get('key_facts', [])

    prompt = f"""
You are summarizing a conversation between BMO and Friend for long term memory.

EXISTING MEMORY:
{existing_summary}

EXISTING KEY FACTS:
{chr(10).join(f'- {f}' for f in existing_facts)}

NEW CONVERSATION:
{transcript}

Extract anything new and meaningful about Friend from the new conversation.
Merge it with existing memory. Be concise. Focus on:
- Life events (jobs, relationships, health, big news)
- Recurring patterns (often tired, frequently stressed, etc)
- Things Friend cares about (hobbies, interests, goals)
- Unresolved things Friend mentioned

Reply in this exact format:
SUMMARY: <2-4 sentences summarizing everything known about Friend so far>
FACTS:
- <one fact per line>
- <keep existing facts if still relevant>
- <add new facts from this session>
"""

    messages = [{"role": "user", "content": prompt}]
    result = ollama.chat(model=MODEL, messages=messages)
    content = result['message']['content']

    # Parse the result
    new_summary = existing_summary
    new_facts = existing_facts.copy()

    lines = content.strip().split('\n')
    in_facts = False
    for line in lines:
        if line.startswith('SUMMARY:'):
            new_summary = line.split(':', 1)[1].strip()
        elif line.startswith('FACTS:'):
            in_facts = True
            new_facts = []
        elif in_facts and line.strip().startswith('-'):
            fact = line.strip()[1:].strip()
            if fact:
                new_facts.append(fact)

    # Save updated memory
    memory = {
        'summary': new_summary,
        'key_facts': new_facts,
        'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open('memory.json', 'w') as f:
        json.dump(memory, f, indent=2)

    # Save last session for reload
    with open('last_session.json', 'w') as f:
        # Strip timestamps before saving — ollama doesn't want extra fields
        clean_history = [
            {"role": e['role'], "content": e['content']}
            for e in conversation_history
        ]
        json.dump(clean_history, f, indent=2)

    print("BMO saved the memories.")


def load_memory():
    """Load long term memory and last session on startup."""
    memory = {'summary': '', 'key_facts': []}
    last_session = []

    if os.path.exists('memory.json'):
        with open('memory.json', 'r') as f:
            memory = json.load(f)

    if os.path.exists('last_session.json'):
        with open('last_session.json', 'r') as f:
            last_session = json.load(f)

    return memory, last_session


def write_face_state(mood="neutral", typing=False, reacting=False):
    with open("face_state.json", "w") as f:
        json.dump({
            "mood": mood,
            "typing": typing,
            "reacting": reacting
        }, f)


# ─────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────
if __name__ == "__main__":
    conversation_history = []
    tracker = ThreadTracker()   # ← initialised once before the loop

    memory, last_session = load_memory()

    conversation_history = last_session  # ← resume from last session
    tracker = ThreadTracker()

    if memory.get('summary'):
        print(f"BMO remembers friend.")

    print("BMO is loaded")
    sys.stdout.write("You: ")
    sys.stdout.flush()

    while True:
        ready, _, _ = select.select([sys.stdin], [], [], 0.1)

        if ready:
            user_input = sys.stdin.readline().strip()

            # 1. When user sends a message — react
            write_face_state(
                mood=tracker.conv_state['user_mood'], reacting=True)

            # 2. While BMO is thinking/typing — show typing animation
            write_face_state(mood=tracker.conv_state['user_mood'], typing=True)
            bmo_response = get_bmo_response(
                user_input, conversation_history, tracker, memory)
            write_face_state(
                mood=tracker.conv_state['user_mood'], typing=False)

            # 3. After tracker updates — reflect new mood
            tracker.update(user_input, bmo_response)
            write_face_state(mood=tracker.conv_state['user_mood'])

            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("BMO: Bye bye! BMO hopes to chat with you again soon!")
                save_conversation(conversation_history)
                # ← save memory on exit
                save_memory(conversation_history, memory)
                break

            bmo_response = get_bmo_response(
                user_input, conversation_history, tracker, memory)  # ← pass memory

            sys.stdout.write("BMO: ")
            sys.stdout.flush()
            type_out(bmo_response, delay=0.01)

            conversation_history.append({
                "role": "user",
                "content": user_input,
                "timestamp": time.time()
            })
            conversation_history.append(
                {"role": "assistant", "content": bmo_response})

            tracker.update(user_input, bmo_response)

            last_bmo_comment_time = time.time()
            sys.stdout.write("You: ")
            sys.stdout.flush()

        else:
            time_since_last_comment = time.time() - last_bmo_comment_time

            if time_since_last_comment >= SILENCE_THRESHOLD:
                last_bmo_comment_time = time.time()
                bmo_random_message = generate_bmo_comment(
                    conversation_history, tracker, memory)  # ← pass memory

                if bmo_random_message.strip():
                    print(f"\nBMO: {bmo_random_message}")
                    conversation_history.append(
                        {"role": "assistant", "content": bmo_random_message}
                    )
                    sys.stdout.write("You: ")
                    sys.stdout.flush()
                else:
                    last_bmo_comment_time = time.time()

        time.sleep(0.1)
