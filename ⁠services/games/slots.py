import random

SLOT_SYMBOLS = ["🎰", "7️⃣", "💎", "🍋", "🍒", "🔔"]

def spin_slots():
    reel = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
    if reel[0] == reel[1] == reel[2]:
        mult = 10.0 if reel[0] == "7️⃣" else 5.0
    elif reel[0] == reel[1] or reel[1] == reel[2] or reel[0] == reel[2]:
        mult = 1.5
    else:
        mult = 0.0
    return reel, mult
