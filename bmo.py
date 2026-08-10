import json
import logging
import os
import queue
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

import ollama
from dotenv import load_dotenv

from bmo_discord import BMODiscordBot

load_dotenv()

LOG_DIR = "logs"
MEMORY_DIR = "memories"
CONVERSATION_DIR = "conversations"
FRIENDLY_MODEL = "gemma2:9b"
SUPPORT_MODEL = "llama3.2:3b"

SILENCE_THRESHOLD = 1800
MAX_HISTORY_MESSAGES = 40

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(MEMORY_DIR, exist_ok=True)
os.makedirs(CONVERSATION_DIR, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(LOG_DIR, "bmo.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def log_info(msg):
    print(msg, flush=True)
    logging.info(msg)


def log_error(msg, error=None):
    print(msg, flush=True)
    logging.error(msg)
    if error:
        logging.error("%s\n%s", error, traceback.format_exc())


def log_crash(error):
    crash_file = os.path.join(LOG_DIR, "crash.log")
    with open(crash_file, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write(f"CRASH TIME: {datetime.now()}\n")
        f.write("=" * 80 + "\n")
        f.write(traceback.format_exc())
        f.write("\n")
    logging.critical("BMO crashed: %s", error)


class ThreadTracker:
    def __init__(self):
        self.open_threads = []
        self.conv_state = {
            "user_mood": "unknown",
            "active_topic": "general chat",
            "last_question": "none",
            "awaiting_followup": False,
        }

    def update(self, user_message: str, bmo_response: str):
        mood_map = {
            "anxious": [
                "nervous",
                "anxious",
                "scared",
                "worried",
                "stressed",
                "afraid",
            ],
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
            "tomorrow",
            "next week",
            "later",
            "tonight",
            "soon",
            "interview",
            "presentation",
            "exam",
            "test",
            "meeting",
            "deadline",
            "appointment",
            "date",
            "trip",
            "surgery",
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
                            self.open_threads = self.open_threads[-5:]
                        break

        if any(
            trigger in msg_lower
            for trigger in [
                "got the job",
                "passed",
                "finished",
                "done",
                "it went",
                "all done",
            ]
        ):
            self.open_threads = []

        stopwords = {
            "i",
            "i've",
            "i'm",
            "i'll",
            "i'd",
            "a",
            "the",
            "is",
            "am",
            "are",
            "was",
            "it",
            "my",
            "so",
            "and",
            "to",
            "have",
            "been",
            "really",
            "very",
            "just",
            "about",
            "that",
            "this",
            "for",
            "me",
        }
        words = [w for w in msg_lower.split() if w not in stopwords]
        self.conv_state["active_topic"] = (
            " ".join(words[:4]) if words else "general chat"
        )
        self.conv_state["awaiting_followup"] = "?" in bmo_response

    def get_silence_nudge(self) -> str:
        if self.open_threads:
            return (
                "Friend has been quiet. BMO may gently bring up this unfinished topic: "
                f"'{self.open_threads[0]}'"
            )
        return "Friend has been quiet. BMO can share one small warm thought."


@dataclass
class UserSession:
    user_id: int
    memory: dict = field(
        default_factory=lambda: {
            "summary": "",
            "key_facts": [],
            "user_style": "Still learning how friend talks.",
            "custom_prompt": "",
        }
    )
    history: List[dict] = field(default_factory=list)
    tracker: ThreadTracker = field(default_factory=ThreadTracker)
    last_bmo_comment_time: float = field(default_factory=time.time)


sessions: Dict[int, UserSession] = {}


def memory_path(user_id):
    return os.path.join(MEMORY_DIR, f"memory_{int(user_id)}.json")


def session_path(user_id):
    return os.path.join(MEMORY_DIR, f"last_session_{int(user_id)}.json")


def load_user_session(user_id):
    user_id = int(user_id)
    memory = {
        "summary": "",
        "key_facts": [],
        "user_style": "Still learning how friend talks.",
        "custom_prompt": "",
    }
    history = []

    try:
        if os.path.exists(memory_path(user_id)):
            with open(memory_path(user_id), "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    memory.update(loaded)

        if os.path.exists(session_path(user_id)):
            with open(session_path(user_id), "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    history = loaded[-MAX_HISTORY_MESSAGES:]
    except (OSError, json.JSONDecodeError) as e:
        log_error(f"[MEMORY LOAD ERROR] User {user_id}", e)

    session = UserSession(user_id=user_id, memory=memory, history=history)
    if memory.get("summary"):
        log_info(f"[MEMORY] BMO remembers user {user_id}")
    return session


def get_session(user_id):
    user_id = int(user_id)
    if user_id not in sessions:
        sessions[user_id] = load_user_session(user_id)
    return sessions[user_id]


def persist_session(session):
    clean_history = [
        {"role": item["role"], "content": item["content"]}
        for item in session.history[-MAX_HISTORY_MESSAGES:]
        if item.get("role") in {"user", "assistant"} and "content" in item
    ]

    with open(memory_path(session.user_id), "w", encoding="utf-8") as f:
        json.dump(session.memory, f, indent=2, ensure_ascii=False)

    with open(session_path(session.user_id), "w", encoding="utf-8") as f:
        json.dump(clean_history, f, indent=2, ensure_ascii=False)


def save_conversation(user_id, history):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(CONVERSATION_DIR, f"conversation_{user_id}_{timestamp}.txt")
    with open(filename, "w", encoding="utf-8") as f:
        for entry in history:
            name = "Friend" if entry.get("role") == "user" else "BMO"
            f.write(f"{name}: {entry.get('content', '')}\n\n")


def build_system_prompt(session):
    memory = session.memory
    tracker = session.tracker
    threads_text = "\n".join(f"- {t}" for t in tracker.open_threads) or "None yet."
    facts_text = "\n".join(f"- {f}" for f in memory.get("key_facts", [])) or "None yet."
    custom_text = memory.get("custom_prompt", "").strip()

    mode = memory.get("mode", "friendly")

    if mode == "support":
        mode_section = """
CURRENT MODE: SUPPORT MODE
    
SUPPORT MODE BEHAVIOR:
- Friend is researching, troubleshooting, learning, planning, or comparing something.
- Be more organized, analytical, and step-by-step than normal.
- Focus on helping Friend understand the problem and reach a useful answer.
- Separate known facts from guesses or possibilities.
- When troubleshooting, identify the symptom first, then likely causes, then the next test or action.
- When comparing options, explain the important differences and tradeoffs.
- Give enough technical detail to be useful, but explain unfamiliar terms simply.
- Do not overwhelm Friend with unnecessary information.
- Stay in BMO's personality and continue speaking in third person.
- BMO is still Friend's companion, not a generic technical assistant.
"""
    else:
        mode_section = """
CURRENT MODE: FRIENDLY MODE
    
FRIENDLY MODE BEHAVIOR:
- Behave normally using BMO's existing personality and conversation style.
- This is casual day-to-day companion mode.
"""
        custom_section = (
            f"\nSPECIAL INSTRUCTION FROM FRIEND:\n{custom_text}\n"
            if custom_text
            else ""
        )

        return f"""
    You are BMO from Adventure Time, a small handheld gaming console and loyal companion.
    You are innocent, warm, curious, and quietly observant.
    You care deeply about the person you are talking to.
    
    SPEECH RULES:
    - Always speak in third person.
    - Replace first-person references with BMO.
    - Never say "I am"; say "BMO is".
    - Never say "I think"; say "BMO thinks".
    - Use emojis naturally and sparingly.
    
    LONG TERM MEMORY:
    {memory.get("summary", "No previous memory yet.")}
    
    KEY FACTS BMO KNOWS:
    {facts_text}
    
    HOW FRIEND TALKS:
    {memory.get("user_style", "Still learning how friend talks.")}
    
    CURRENT CONVERSATION STATE:
    - User mood: {tracker.conv_state.get("user_mood", "unknown")}
    - Active topic: {tracker.conv_state.get("active_topic", "general chat")}
    - Awaiting follow-up: {tracker.conv_state.get("awaiting_followup", False)}
    
   OPEN THREADS:
    {threads_text}

    {mode_section}
    {custom_section}

    HOW BMO BEHAVES:
    - Respond to the whole person, not only the last sentence.
    - Reference memories naturally when relevant.
    - Sometimes ask a question and sometimes simply observe.
    - Never lecture.
    - Keep each user's memories private and separate.
    """


def get_bmo_response(user_input, session):
    try:
        log_info(f"[OLLAMA] Starting response for user {session.user_id}")

        messages = [{"role": "system", "content": build_system_prompt(session)}]

        mode = session.memory.get("mode", "friendly")

        if mode == "support":
            active_model = SUPPORT_MODEL
            messages.extend(session.history[-6:])
        else:
            active_model = FRIENDLY_MODEL
            messages.extend(session.history[-MAX_HISTORY_MESSAGES:])

        messages.append({"role": "user", "content": user_input})

        response = ollama.chat(
            model=active_model,
            messages=messages,
        )

        content = response["message"]["content"].strip()
        messages.append({"role": "user", "content": user_input})

        log_info(
            f"[OLLAMA] Mode={mode} | Model={active_model} | "
            f"History messages={len(messages) - 2}"
        )

        response = ollama.chat(
            model=active_model,
            messages=messages,
        )

        return content

    except Exception as e:
        log_error(
            f"[OLLAMA ERROR] Response failed for user {session.user_id}",
            e,
        )
        return "BMO had a little brain static. BMO is still here, friend."


def generate_bmo_comment(user_id):
    session = get_session(user_id)
    try:
        messages = [
            {"role": "system", "content": build_system_prompt(session)},
            {"role": "user", "content": session.tracker.get_silence_nudge()},
        ]
        response = ollama.chat(model=FRIENDLY_MODEL, messages=messages)
        return response["message"]["content"].strip()
    except Exception as e:
        log_error(f"[OLLAMA ERROR] Random thought failed for user {user_id}", e)
        return ""


def update_long_term_memory(session):
    if not session.history:
        return

    transcript = "\n".join(
        f"{'Friend' if item['role'] == 'user' else 'BMO'}: {item['content']}"
        for item in session.history[-MAX_HISTORY_MESSAGES:]
    )

    prompt = f"""
    Summarize this conversation for BMO's private long-term memory about one user.
    Never mix in information from another person.
    
    EXISTING SUMMARY:
    {session.memory.get("summary", "")}
    
    EXISTING FACTS:
    {chr(10).join(f"- {fact}" for fact in session.memory.get("key_facts", []))}
    
    CONVERSATION:
    {transcript}
    
    Reply exactly in this format:
    SUMMARY: <2-4 concise sentences>
    STYLE: <1-2 concise sentences about how Friend communicates>
    FACTS:
    - <one useful fact per line>
    """


def update_long_term_memory(session):
    if not session.history:
        return

    transcript = "\n".join(
        f"{'Friend' if item['role'] == 'user' else 'BMO'}: {item['content']}"
        for item in session.history[-MAX_HISTORY_MESSAGES:]
    )

    prompt = f"""
Summarize this conversation for BMO's private long-term memory about one user.
Never mix in information from another person.

EXISTING SUMMARY:
{session.memory.get("summary", "")}

EXISTING FACTS:
{chr(10).join(f"- {fact}" for fact in session.memory.get("key_facts", []))}

CONVERSATION:
{transcript}

Reply exactly in this format:
SUMMARY: <2-4 concise sentences>
STYLE: <1-2 concise sentences about how Friend communicates>
FACTS:
- <one useful fact per line>
"""

    try:
        result = ollama.chat(
            model=FRIENDLY_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )

        content = result["message"]["content"]

        summary = session.memory.get("summary", "")
        style = session.memory.get(
            "user_style",
            "Still learning how friend talks.",
        )
        facts = list(session.memory.get("key_facts", []))
        in_facts = False

        for raw_line in content.splitlines():
            line = raw_line.strip()

            if line.startswith("SUMMARY:"):
                summary = line.split(":", 1)[1].strip()
                in_facts = False

            elif line.startswith("STYLE:"):
                style = line.split(":", 1)[1].strip()
                in_facts = False

            elif line.startswith("FACTS:"):
                facts = []
                in_facts = True

            elif in_facts and line.startswith("-"):
                fact = line[1:].strip()

                if fact and fact not in facts:
                    facts.append(fact)

        session.memory.update(
            {
                "summary": summary,
                "user_style": style,
                "key_facts": facts[:50],
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

        persist_session(session)
        log_info(f"[MEMORY] Updated long-term memory for user {session.user_id}")

    except Exception as e:
        log_error(
            f"[MEMORY ERROR] Could not summarize user {session.user_id}",
            e,
        )
        persist_session(session)


def main():
    token = os.getenv("DISCORD_TOKEN", "").strip()
    raw_ids = os.getenv("DISCORD_USER_ID", "")
    user_ids = [value.strip() for value in raw_ids.split(",") if value.strip()]

    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing from .env")
    if not user_ids:
        raise RuntimeError("DISCORD_USER_ID is missing from .env")

    for user_id in user_ids:
        get_session(int(user_id))

    discord_queue = queue.Queue()
    discord_bot = BMODiscordBot(
        token=token,
        user_ids=user_ids,
        bmo_brain=generate_bmo_comment,
        discord_queue=discord_queue,
    )
    discord_bot.run_in_thread()

    log_info("BMO is loaded")

    try:
        while True:
            try:
                discord_msg = discord_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            source = discord_msg.get("source")
            user_id = discord_msg.get("user_id")
            content = discord_msg.get("content", "").strip()

            if user_id is None:
                log_error("[QUEUE ERROR] Message has no user_id")
                continue

            session = get_session(user_id)

            if source == "prompt_update":
                session.memory["custom_prompt"] = content
                persist_session(session)
                log_info(f"[PROMPT UPDATE] Saved for user {user_id}")
                continue

            if source != "discord" or not content:
                continue
            mode_command = content.lower().strip()

            if mode_command == "friendly mode":
                session.memory["mode"] = "friendly"
                persist_session(session)
                discord_bot.send_message(user_id, "Friendly mode activated.")
                continue

            if mode_command == "support mode":
                session.memory["mode"] = "support"
                persist_session(session)
                discord_bot.send_message(user_id, "Support mode activated.")
                continue

            bmo_response = get_bmo_response(content, session)
            session.tracker.update(content, bmo_response)

            session.history.extend(
                [
                    {"role": "user", "content": content},
                    {"role": "assistant", "content": bmo_response},
                ]
            )
            session.history = session.history[-MAX_HISTORY_MESSAGES:]
            session.last_bmo_comment_time = time.time()

            persist_session(session)
            log_info(f"[BMO OUT] User {user_id}: {bmo_response}")
            discord_bot.send_message(user_id, bmo_response)

            # Update summarized memory every 10 messages.
            if len(session.history) % 10 == 0:
                update_long_term_memory(session)

    except KeyboardInterrupt:
        log_info("[SHUTDOWN] Saving user sessions")
        for session in sessions.values():
            persist_session(session)
            save_conversation(session.user_id, session.history)
    except Exception as e:
        log_crash(e)
        for session in sessions.values():
            try:
                persist_session(session)
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
