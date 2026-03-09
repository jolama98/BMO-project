# test_tracker.py
from bmo import ThreadTracker


tracker = ThreadTracker()

tracker.update(
    user_message="I've been really stressed about my job interview tomorrow",
    bmo_response="BMO thinks friend should get some rest before the big day!"
)

print("Mood:", tracker.conv_state['user_mood'])
print("Topic:", tracker.conv_state['active_topic'])
print("Open threads:", tracker.open_threads)
print("Awaiting followup:", tracker.conv_state['awaiting_followup'])
