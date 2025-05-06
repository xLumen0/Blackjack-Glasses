from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from inference_sdk import InferenceHTTPClient
from io import BytesIO
from PIL import Image
import os
import logging
import cv2
import numpy as np
from time import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["http://127.0.0.1:3000", "http://192.168.1.89:5000"]}})

# Initialize RoboFlow client
CLIENT = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key="FBZWDotevfrL2HPrtRkE"
)

# Game state
player_hand = []
dealer_hand = []
used_cards = set()
game_active = False

def get_card_value(card_name):
    """Extract card value from RoboFlow label."""
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
            logging.error(f"Invalid card rank: {rank}")
            return 0

def calculate_hand_value(hand):
    """Calculate blackjack hand value."""
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
    """Return hit/stand recommendation."""
    if not dealer_upcard_value:
        return "Add dealer card"
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
    return "Hit"

def deal_initial_cards():
    """Start a new game."""
    global player_hand, dealer_hand, used_cards, game_active
    player_hand = []
    dealer_hand = []
    used_cards = set()
    game_active = True
    logging.info("New Game Started")
    logging.info("Please add a dealer card: Invoke-WebRequest -Uri http://192.168.1.89:5000/add_dealer_card -Method POST -Body '{\"card\":\"KC\"}' -ContentType 'application/json'")

def dealer_play(temp_hand=None):
    """Use provided dealer hand."""
    if temp_hand is None:
        temp_hand = dealer_hand.copy()
    return temp_hand, calculate_hand_value(temp_hand)

def determine_outcome():
    """Determine game outcome."""
    player_value = calculate_hand_value(player_hand)
    temp_dealer_hand, dealer_value = dealer_play()
    logging.info("=== Game Outcome ===")
    logging.info(f"Player Hand: {player_hand} (Value: {player_value})")
    logging.info(f"Dealer Hand: {temp_dealer_hand} (Value: {dealer_value})")

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
    logging.info(f"Outcome: {outcome}")
    return outcome, temp_dealer_hand, dealer_value

@app.route('/')
def index():
    """Serve GUI."""
    logging.info("Serving index.html")
    return render_template('index.html')

@app.route('/game_state', methods=['GET'])
def game_state():
    """Return game state."""
    logging.info("Fetching game state")
    player_value = calculate_hand_value(player_hand)
    dealer_value = calculate_hand_value(dealer_hand)
    dealer_upcard_value = get_card_value(dealer_hand[0]) if dealer_hand else 0
    recommendation = get_strategy_recommendation(player_value, dealer_upcard_value)
    status = "Bust" if player_value > 21 else ("Active" if game_active else "Game Over")
    
    outcome = None
    dealer_hand_for_response = dealer_hand if dealer_hand else []
    
    if status == "Bust":
        outcome, temp_dealer_hand, dealer_value = determine_outcome()
        dealer_hand_for_response = temp_dealer_hand
    
    response = {
        "player_hand": player_hand,
        "player_value": player_value,
        "dealer_hand": dealer_hand_for_response,
        "dealer_value": dealer_value,
        "recommendation": recommendation,
        "status": status,
        "outcome": outcome
    }
    logging.info(f"Game state response: {response}")
    return jsonify(response)

@app.route('/captured_card', methods=['GET'])
def captured_card():
    """Serve captured card image."""
    image_path = os.path.join(os.getcwd(), "captured_card.jpg")
    logging.info(f"Serving captured_card.jpg from: {image_path}")
    if os.path.exists(image_path):
        logging.info("Image found, sending")
        return send_file(image_path, mimetype='image/jpeg')
    logging.error(f"captured_card.jpg not found at: {image_path}")
    return jsonify({"error": "No card image available"}), 404

@app.route('/add_dealer_card', methods=['POST'])
def add_dealer_card():
    """Add a card to dealer's hand."""
    global dealer_hand, used_cards
    try:
        data = request.get_json(silent=True)
        logging.info(f"add_dealer_card request received: {data}")
        if not data:
            logging.error("No JSON data provided")
            return jsonify({"error": "No JSON data provided"}), 400
        card = data.get('card')
        if not card:
            logging.error("Card not provided")
            return jsonify({"error": "Card not provided"}), 400
        if get_card_value(card) == 0:
            logging.error(f"Invalid card: {card}")
            return jsonify({"error": f"Invalid card: {card}"}), 400
        if card in used_cards:
            logging.error(f"Duplicate card rejected: {card}")
            return jsonify({"error": f"Duplicate card {card} not allowed in single deck"}), 400
        dealer_hand.append(card)
        used_cards.add(card)
        logging.info(f"Added card to dealer's hand: {card}, New hand: {dealer_hand}, Used cards: {used_cards}")
        return jsonify({"message": f"Added card {card} to dealer's hand", "dealer_hand": dealer_hand}), 200
    except Exception as e:
        logging.error(f"Adding dealer card: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_image():
    """Handle ESP32 image upload."""
    global game_active, player_hand, dealer_hand, used_cards
    try:
        start_time = time()
        image_data = request.get_data()
        logging.info(f"Received image data: {len(image_data)} bytes")
        if not image_data:
            logging.error("No image data received")
            return jsonify({"error": "No image data received"}), 400

        # Preprocess image with OpenCV
        image = Image.open(BytesIO(image_data)).convert("RGB")
        image_np = np.array(image)
        
        # Split into RGB channels
        channels = cv2.split(image_np)
        
        # Apply CLAHE to each channel for contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        clahe_channels = [clahe.apply(ch) for ch in channels]
        
        # Merge channels back
        enhanced = cv2.merge(clahe_channels)
        
        # Reduce noise with Gaussian blur
        blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
        
        # Sharpen image
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(blurred, -1, kernel)
        
        # Adjust brightness (reduce to avoid glare)
        hsv = cv2.cvtColor(sharpened, cv2.COLOR_RGB2HSV)
        hsv[:, :, 2] = hsv[:, :, 2] * 0.9  # Reduce brightness by 10%
        processed = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
        
        # Resize to 640x480
        processed = cv2.resize(processed, (640, 480))
        
        # Save processed image
        image_path = os.path.join(os.getcwd(), "captured_card.jpg")
        cv2.imwrite(image_path, cv2.cvtColor(processed, cv2.COLOR_RGB2BGR))
        logging.info(f"Saved captured_card.jpg to: {image_path}")

        # Call Roboflow API
        try:
            result = CLIENT.infer(image_path, model_id="playing-cards-ow27d/4")
            logging.info(f"Roboflow API response: {result}")
        except Exception as api_error:
            logging.error(f"Roboflow API failed: {str(api_error)}")
            return jsonify({
                "error": "Failed to detect card due to API error",
                "roboflow_error": str(api_error),
                "hand": player_hand,
                "hand_value": calculate_hand_value(player_hand),
                "status": "Active" if game_active else "Game Over",
                "message": "Image saved, but card detection failed"
            }), 200

        predictions = result.get("predictions", [])
        if not predictions:
            logging.error("No card detected")
            return jsonify({
                "error": "No card detected",
                "roboflow_response": result,
                "hand": player_hand,
                "hand_value": calculate_hand_value(player_hand),
                "status": "Active" if game_active else "Game Over",
                "message": "Image saved, but no card detected"
            }), 200

        card = max(predictions, key=lambda x: x["confidence"])
        card_name = card["class"]
        logging.info(f"Detected card: {card_name}")

        if card_name in used_cards:
            logging.error(f"Duplicate card rejected: {card_name}")
            return jsonify({
                "error": f"Duplicate card {card_name} not allowed in single deck",
                "hand": player_hand,
                "hand_value": calculate_hand_value(player_hand),
                "status": "Active" if game_active else "Game Over",
                "message": "Please scan a different card"
            }), 200

        if not game_active:
            deal_initial_cards()

        player_hand.append(card_name)
        used_cards.add(card_name)
        player_value = calculate_hand_value(player_hand)

        logging.info("=== Game State ===")
        logging.info(f"Player Hand: {player_hand} (Value: {player_value})")
        logging.info(f"Used cards: {used_cards}")

        if not dealer_hand:
            logging.info("Please add a dealer card")
            return jsonify({
                "card_detected": card_name,
                "confidence": card["confidence"],
                "hand": player_hand,
                "hand_value": player_value,
                "status": "Active",
                "message": "Add a dealer card to continue"
            }), 200

        dealer_upcard_value = get_card_value(dealer_hand[0]) if dealer_hand else 0
        recommendation = get_strategy_recommendation(player_value, dealer_upcard_value)
        logging.info(f"Dealer Hand: {dealer_hand} (Value: {calculate_hand_value(dealer_hand)})")
        logging.info(f"*** RECOMMENDATION: {recommendation.upper()} ***")

        status = "Bust" if player_value > 21 else "Active"
        if status == "Bust":
            outcome, temp_dealer_hand, dealer_value = determine_outcome()
            game_active = False
            return jsonify({
                "card_detected": card_name,
                "confidence": card["confidence"],
                "hand": player_hand,
                "hand_value": player_value,
                "dealer_hand": temp_dealer_hand,
                "dealer_value": dealer_value,
                "status": "Bust",
                "outcome": outcome
            }), 200

        return jsonify({
            "card_detected": card_name,
            "confidence": card["confidence"],
            "hand": player_hand,
            "hand_value": player_value,
            "dealer_hand": dealer_hand,
            "recommendation": recommendation,
            "status": status,
            "message": "Card added"
        }), 200

    except Exception as e:
        logging.error(f"Upload error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/stand', methods=['POST'])
def player_stand():
    """Handle stand action."""
    global game_active, dealer_hand
    logging.info("Received stand request")
    if not game_active:
        logging.error("No active game")
        return jsonify({"error": "No active game. Upload a card to start."}), 400
    if not dealer_hand:
        logging.error("Dealer's cards not set")
        return jsonify({"error": "Dealer's cards not set."}), 400
    outcome, temp_dealer_hand, dealer_value = determine_outcome()
    dealer_hand = temp_dealer_hand
    game_active = False
    logging.info(f"Player stood, outcome: {outcome}")
    return jsonify({
        "message": "Player stands",
        "hand": player_hand,
        "hand_value": calculate_hand_value(player_hand),
        "dealer_hand": dealer_hand,
        "dealer_value": dealer_value,
        "outcome": outcome
    }), 200

@app.route('/reset', methods=['POST'])
def reset_hand():
    """Reset game."""
    global player_hand, dealer_hand, used_cards, game_active
    logging.info("Received reset request")
    player_hand = []
    dealer_hand = []
    used_cards = set()
    game_active = False
    logging.info("=== Game Reset ===")
    logging.info("Start a new game by scanning a card.")
    return jsonify({"message": "Hand reset", "hand": player_hand, "dealer_hand": dealer_hand}), 200

if __name__ == '__main__':
    logging.info("Starting Flask server on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)