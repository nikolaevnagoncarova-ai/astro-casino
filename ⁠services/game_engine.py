import random

class GameEngine:
    @staticmethod
    def calculate_payout(bet: int, multiplier: float) -> int:
        return int(bet * multiplier)

    @staticmethod
    def roll_dice(sides: int = 6) -> int:
        return random.randint(1, sides)
