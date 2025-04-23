import requests
import json

def test_rasa():
    """Test the Rasa API by sending a message and printing the response."""
    url = "http://localhost:5005/webhooks/rest/webhook"
    headers = {"Content-Type": "application/json"}
    data = {
        "sender": "test_user",
        "message": "Hello"
    }
    
    print(f"Sending message to Rasa: {data['message']}")
    response = requests.post(url, headers=headers, data=json.dumps(data))
    
    print(f"Status code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 200:
        responses = response.json()
        if responses:
            for resp in responses:
                print(f"Bot: {resp.get('text', '')}")
        else:
            print("Bot didn't respond with any messages.")
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    test_rasa() 