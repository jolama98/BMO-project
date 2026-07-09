BMO is my AI companion project. 
Im learning Python as I go, this project is for a Raspberry Pi, BMO is based on a the Adventure Time charterer BMO.

//TODO - Take user input ✅
//TODO - Import ollama ✅
//TODO - build BMO personality ✅
//TODO - Save conversations ✅
//TODO - Exit chat without using Control + C ✅

Step Two 
Conversation Memory

Random or not? 🤔🤔🤔🤔🤔🤔🤔🤔🤔🤔🤔🤔🤔🤔
Random Unprompted BMO-isms {
    When BMO says something randomly, should user be able to reply to it? Or does it just appear and then BMO waits for user next message?

    When BMO generates a random context-aware message, how should it decide what to talk about?  It should take from the past 30 min of conversation
    history.
}

Loop:
  → Check if input is ready (DON'T FREEZE)
  → If input ready:
      - Get the input
      - Call bmo_response(user_input, conversation_history)
      - Append to conversation_history
      - Reset timer
  → If no input ready:
      - Check timer
      - If timer > 5 minutes:
          - Generate random BMO message using conversation_history
          - Append BMO's random message to conversation_history
          - Reset timer
  → Wait 0.1 seconds
  → Repeat

[10 minutes of silence]
BMO: Friend mentioned being tired. BMO hopes friend is resting!
[Now what? Can user respond to this?]


//TODO - Check for user input. First find a library ⚙︎










