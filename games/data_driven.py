import random

GAMES_CONFIG = {
    "dice": {"name": "🎲 Кости", "win_rate": 0.48, "mult": 1.9},
    "coin": {"name": "🪙 Монетка", "win_rate": 0.50, "mult": 1.95},
    "roulette": {"name": "🎰 Рулетка", "win_rate": 0.45, "mult": 2.0},
}

def play_generic_game(game_key: str):
    game = GAMES_CONFIG.get(game_key)
    if not game:
        return False, 0.0
    win = random.random() < game["win_rate"]
    mult = game["mult"] if win else 0.0
    return win, mult
