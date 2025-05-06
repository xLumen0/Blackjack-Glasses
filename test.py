from inference_sdk import InferenceHTTPClient
from time import time
import json

# Initialize RoboFlow client
CLIENT = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key="FBZWDotevfrL2HPrtRkE"
)

    # Path to the captured image
image_path = "captured_card.jpg"

     # Test inference
try:
   start_time = time()
   result = CLIENT.infer(image_path, model_id="playing-cards-ow27d/4")
   print(f"Time: {time() - start_time:.2f}s")
   print(f"Result: {json.dumps(result, indent=2)}")
except Exception as e:
    print(f"Error: {str(e)}")