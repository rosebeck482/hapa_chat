from typing import Any, Dict, Text
import sys
import asyncio
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from actions.actions import ActionUpdateMetadata

def create_dummy_tracker(sender_id="test_user_4"):
    """Create a dummy tracker with some slots for testing"""
    
    class DummySlot:
        def __init__(self, name, value):
            self.name = name
            self.value = value
            
    class DummyTracker:
        def __init__(self, sender_id, slots):
            self.sender_id = sender_id
            self._slots = {slot.name: slot for slot in slots}
        
        def get_slot(self, slot_name):
            if slot_name in self._slots:
                return self._slots[slot_name].value
            return None
            
        def current_slot_values(self):
            return {name: slot.value for name, slot in self._slots.items()}
            
    # Create some dummy slots
    slots = [
        DummySlot("name", "Test User 4"),
        DummySlot("age", 30),
        DummySlot("gender", "male"),
        DummySlot("interests", "coding, testing"),
        DummySlot("assistant_id", "testing_assistant"),
        DummySlot("personal_data_stage", 7),
    ]
    
    return DummyTracker(sender_id, slots)

async def run_test():
    print("Starting direct test of ActionUpdateMetadata...")
    
    # Create the action instance
    action = ActionUpdateMetadata()
    
    # Create a dummy tracker
    tracker = create_dummy_tracker()
    
    # Create a dummy dispatcher
    class DummyDispatcher:
        def __init__(self):
            self.messages = []
            
        def utter_message(self, **kwargs):
            self.messages.append(kwargs)
            print(f"Dispatcher received message: {kwargs}")
    
    dispatcher = DummyDispatcher()
    
    # Create dummy domain
    domain = {}
    
    # Run the action
    print(f"Running action for user {tracker.sender_id}...")
    result = await action.run(dispatcher, tracker, domain)
    
    print(f"Action returned: {result}")
    print("Test completed!")

def main():
    # Run the async test
    asyncio.run(run_test())

if __name__ == "__main__":
    main() 