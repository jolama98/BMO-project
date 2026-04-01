def update(self, user_message: str, bmo_response: str):
    # MOOD - simple keyword matching
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

    # THREADS - look for upcoming or unresolved events
    thread_triggers = [
        "tomorrow", "next week", "later", "tonight", "soon",
        "interview", "presentation", "exam", "test", "meeting",
        "deadline", "appointment", "date", "trip", "surgery"
    ]
    for trigger in thread_triggers:
        if trigger in msg_lower:
            # Grab a short snippet around the trigger word
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

    # CLOSE THREADS - if user says it went well/badly, clear related threads
    close_triggers = ["got the job", "passed",
                      "finished", "done", "it went", "all done"]
    if any(trigger in msg_lower for trigger in close_triggers):
        self.open_threads = []

    # TOPIC - just use the first few meaningful words
    stopwords = {"i", "a", "the", "is", "am", "are", "was",
                 "it", "my", "so", "and", "to", "have", "been"}
    words = [w for w in user_message.lower().split() if w not in stopwords]
    self.conv_state["active_topic"] = " ".join(
        words[:4]) if words else "general chat"

    # FOLLOWUP - did BMO ask a question?
    self.conv_state["awaiting_followup"] = "?" in bmo_response


# print(
    # f"DEBUG → mood: {tracker.conv_state['user_mood']} | threads: {tracker.open_threads}")
