from flask import Flask, request
from inference_sdk import InferenceHTTPClient
from io import BytesIO
from PIL import Image
from time import time
import random

app = Flask(__name__)

# Initialize RoboFlow client
CLIENT = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key="FBZWDotevfrL2HPrtRkE"
)

# Store game state
player_hand = []
dealer_hand = []
game_active = False  # Tracks if a game is in progress

def get_card_value(card_name):
    """Extract card value from RoboFlow label (e.g., 'KC' -> 10, '10C' -> 10, 'AC' -> 11)."""
    rank_map = {
        'A': 'Ace', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7', '8': '8', '9': '9', '10': '10',
        'J': 'Jack', 'Q': 'Queen', 'K': 'King'
    }
    rank = card_name[:-1] if card_name[-1] in 'CDHS' else card_name.split(' of ')[0]
    rank = rank_map.get(rank, rank)
    if rank in ["Jack", "Queen", "King"]:
        return 10
    elif rank == "Ace":
        return 11
    else:
        try:
            return int(rank)
        except ValueError:
            print(f"[ERROR] Invalid card rank: {rank}")
            return 0

def calculate_hand_value(hand):
    """Calculate blackjack hand value, adjusting for Aces."""
    value = 0
    num_aces = 0
    for card in hand:
        card_value = get_card_value(card)
        if card_value == 11:
            num_aces += 1
        value += card_value
    while value > 21 and num_aces > 0:
        value -= 10
        num_aces -= 1
    return value

def get_strategy_recommendation(player_value, dealer_upcard_value):
    """Return hit/stand recommendation based on basic blackjack strategy."""
    if player_value >= 17:
        return "Stand"
    elif player_value <= 11:
        return "Hit"
    elif player_value in [12, 13, 14, 15, 16]:
        if dealer_upcard_value >= 7 or (player_value == 12 and dealer_upcard_value in [2, 3]):
            return "Hit"
        return "Stand"
    elif player_value in [13, 14, 15, 16] and dealer_upcard_value <= 6:
        return "Stand"
    return "Hit"  # Default for edge cases

def deal_initial_cards():
    """Start a new game and prompt for dealer's upcard."""
    global player_hand, dealer_hand, game_active
    player_hand = []
    dealer_hand = []
    game_active = True
    print("=== New Game Started ===")
    print("Please set dealer's upcard: Invoke-WebRequest -Uri http://192.168.1.89:5000/set_dealer_upcard -Method POST -Body '{\"upcard\":\"KC\"}' -ContentType 'application/json'")

def dealer_play():
    """Dealer hits until hand value is 17 or higher."""
    while calculate_hand_value(dealer_hand) < 17:
        dealer_card = random.choice(['2C', '3C', '4C', '5C', '6C', '7C', '8C', '9C', '10C', 'JC', 'QC', 'KC', 'AC'])
        dealer_hand.append(dealer_card)
        print(f"Dealer draws: {dealer_card}")
    return calculate_hand_value(dealer_hand)

def determine_outcome():
    """Determine game outcome based on player and dealer hands."""
    player_value = calculate_hand_value(player_hand)
    dealer_value = dealer_play()
    print("=== Game Outcome ===")
    print(f"Player Hand: {player_hand} (Value: {player_value})")
    print(f"Dealer Hand: {dealer_hand} (Value: {dealer_value})")

    if player_value > 21:
        outcome = "Player busts! Dealer wins."
    elif dealer_value > 21:
        outcome = "Dealer busts! Player wins."
    elif player_value == dealer_value:
        outcome = "Push! It's a tie."
    elif player_value == 21 and len(player_hand) == 2:
        outcome = "Blackjack! Player wins."
    elif player_value > dealer_value:
        outcome = "Player wins!"
    else:
        outcome = "Dealer wins."
    print(f"Outcome: {outcome}")
    return outcome

@app.route('/set_dealer_upcard', methods=['POST'])
def set_dealer_upcard():
    global dealer_hand
    try:
        data = request.get_json()
        upcard = data.get('upcard')
        if not upcard:
            return {"error": "Upcard not provided"}, 400
        if get_card_value(upcard) == 0:
            return {"error": f"Invalid upcard: {upcard}"}, 400
        dealer_hand = [upcard]
        print(f"Dealer's upcard set to: {upcard}")
        return {"message": f"Dealer's upcard set to {upcard}", "dealer_hand": dealer_hand}, 200
    except Exception as e:
        print(f"[ERROR] Setting upcard: {str(e)}")
        return {"error": str(e)}, 500

@app.route('/upload', methods=['POST'])
def upload_image():
    global game_active, player_hand, dealer_hand
    try:
        start_time = time()
        image_data = request.get_data()
        image = Image.open(BytesIO(image_data)).convert("RGB")
        image.save("captured_card.jpg", "JPEG", quality=95)

        result = CLIENT.infer("captured_card.jpg", model_id="playing-cards-ow27d/4")
        predictions = result.get("predictions", [])
        if not predictions:
            print("[ERROR] No card detected")
            return {"error": "No card detected"}, 400

        card = max(predictions, key=lambda x: x["confidence"])
        card_name = card["class"]

        if not game_active:
            deal_initial_cards()

        if not player_hand or player_hand[-1] != card_name:
            player_hand.append(card_name)
        else:
            print(f"Duplicate card {card_name} ignored")
            return {
                "card_detected": card_name,
                "confidence": card["confidence"],
                "hand": player_hand,
                "hand_value": calculate_hand_value(player_hand),
                "status": "Active",
                "message": "Duplicate card ignored"
            }, 200

        player_value = calculate_hand_value(player_hand)
        print("=== Game State ===")
        print(f"Player Hand: {player_hand} (Value: {player_value})")

        if not dealer_hand:
            print("Please set dealer's upcard: Invoke-WebRequest -Uri http://192.168.1.89:5000/set_dealer_upcard -Method POST -Body '{\"upcard\":\"KC\"}' -ContentType 'application/json'")
            return {
                "card_detected": card_name,
                "confidence": card["confidence"],
                "hand": player_hand,
                "hand_value": player_value,
                "status": "Active",
                "message": "Set dealer's upcard to continue"
            }, 200

        dealer_upcard = dealer_hand[0]
        dealer_upcard_value = get_card_value(dealer_upcard)
        recommendation = get_strategy_recommendation(player_value, dealer_upcard_value)
        print(f"Dealer Upcard: {dealer_upcard} (Value: {dealer_upcard_value})")
        print(f"*** RECOMMENDATION: {recommendation.upper()} ***")

        status = "Bust" if player_value > 21 else "Active"
        if status == "Bust":
            outcome = determine_outcome()
            game_active = False
            return {
                "card_detected": card_name,
                "confidence": card["confidence"],
                "hand": player_hand,
                "hand_value": player_value,
                "dealer_hand": dealer_hand,
                "dealer_value": dealer_value,
                "status": "Bust",
                "outcome": outcome
            }, 200

        return {
            "card_detected": card_name,
            "confidence": card["confidence"],
            "hand": player_hand,
            "hand_value": player_value,
            "dealer_upcard": dealer_upcard,
            "recommendation": recommendation,
            "status": status
        }, 200

    except Exception as e:
        print(f"[ERROR] Upload: {str(e)}")
        return {"error": str(e)}, 500

@app.route('/stand', methods=['POST'])
def player_stand():
    global game_active
    if not game_active:
        print("[ERROR] No active game")
        return {"error": "No active game. Upload a card to start."}, 400
    if not dealer_hand:
        print("[ERROR] Dealer's upcard not set")
        return {"error": "Dealer's upcard not set. Use /set_dealer_upcard."}, 400
    outcome = determine_outcome()
    game_active = False
    return {
        "message": "Player stands",
        "hand": player_hand,
        "hand_value": calculate_hand_value(player_hand),
        "dealer_hand": dealer_hand,
        "dealer_value": calculate_hand_value(dealer_hand),
        "outcome": outcome
    }, 200

@app.route('/reset', methods=['POST'])
def reset_hand():
    global player_hand, dealer_hand, game_active
    player_hand = []
    dealer_hand = []
    game_active = False
    print("=== Game Reset ===")
    print("Start a new game by scanning a card.")
    return {"message": "Hand reset", "hand": player_hand, "dealer_hand": dealer_hand}, 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)