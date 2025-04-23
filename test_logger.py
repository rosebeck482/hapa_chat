import os
import json
from datetime import datetime
from conversation_logger import ConversationLogger

def main():
    print("Starting test of ConversationLogger...")
    
    # Create a logger instance
    logger = ConversationLogger()
    
    # Test user ID
    test_user_id = "test_user_3"
    
    # Create test metadata
    test_metadata = {
        "name": "Test User 3",
        "age": 25,
        "gender": "female",
        "test_timestamp": datetime.now().isoformat(),
        "direct_test": True
    }
    
    # Update metadata
    print(f"Updating metadata for user {test_user_id}...")
    logger.update_metadata(test_user_id, test_metadata)
    
    # Also create direct test file
    direct_test_path = os.path.join("conversation_logs", "direct_script_test.json")
    with open(direct_test_path, "w") as f:
        json.dump({"test": True, "timestamp": datetime.now().isoformat()}, f, indent=2)
    
    print(f"Direct test file created at: {direct_test_path}")
    
    # List files in conversation_logs
    files = os.listdir("conversation_logs")
    print(f"Files in conversation_logs: {files}")
    
    print("Test completed successfully!")

if __name__ == "__main__":
    main() 