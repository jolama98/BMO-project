# thread_tracker.py
MODEL = 'gemma2:9b' 
import ollama

class ThreadTracker:
    def __init__(self):
        self.open_threads = []      # things BMO should return to
        self.conv_state = {
            "user_mood": "unknown",
            "active_topic": "general chat",
            "last_question": "none",
            "awaiting_followup": False
        }

def update(self, user_message: str, bmo_response: str):
    extraction_prompt = f"""
You are a conversation analyst. Look at what the user said and extract structured info.

User said: "{user_message}"

Current open threads: {self.open_threads}

A NEW_THREAD is anything unresolved, upcoming, or emotionally significant from the user's message.
Examples: "job interview tomorrow", "argument with a friend", "big presentation"

Reply in this exact format (no extra text):
MOOD: <one word describing user mood>
TOPIC: <current active topic in 5 words or less>
NEW_THREAD: <unresolved situation from user message, or NONE>
CLOSE_THREAD: <a thread that got resolved, or NONE>
BMO_ASKED_QUESTION: <yes or no>
"""
    messages = [{"role": "user", "content": extraction_prompt}]
    result = ollama.chat(model=MODEL, messages=messages)  # ← fixed
    self._parse_and_apply(result['message']['content'])   # ← fixed

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
                    # Cap it so BMO doesn't hoard 50 threads
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

    def get_silence_prompt(self) -> str:
        """
        Called by your existing silence detection.
        Returns a prompt nudge for BMO to use during quiet moments.
        """
        if self.open_threads:
            thread = self.open_threads[0]  # oldest unresolved thread
            return f"There has been a long silence. BMO is thinking about this open thread and may gently bring it up: '{thread}'"
        else:
            return "There has been a long silence. BMO can make a small, warm observation about the conversation so far."
