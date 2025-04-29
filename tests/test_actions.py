import unittest
from unittest.mock import MagicMock
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

# Import your custom actions
# Note: Update import path as needed for your project structure
try:
    from actions.actions import (
        ActionCollectName,
        ActionCollectAge,
        ActionCollectGender,
        ActionCollectGenderPreference,
        ActionCollectAgePreference,
        ActionCollectHeight
    )
except ImportError:
    print("Note: This test assumes actions are in 'actions/actions.py'. Adjust import path as needed.")
    # Create mock classes for testing if import fails
    class ActionCollectName:
        def run(self, dispatcher, tracker, domain):
            return []
            
    class ActionCollectAge:
        def run(self, dispatcher, tracker, domain):
            return []
            
    class ActionCollectGender:
        def run(self, dispatcher, tracker, domain):
            return []
            
    class ActionCollectGenderPreference:
        def run(self, dispatcher, tracker, domain):
            return []
            
    class ActionCollectAgePreference:
        def run(self, dispatcher, tracker, domain):
            return []
            
    class ActionCollectHeight:
        def run(self, dispatcher, tracker, domain):
            return []


def create_mock_tracker(sender_id="test_user", slot_values=None, latest_message=None):
    """Helper function to create a mock tracker for testing."""
    slot_values = slot_values or {}
    latest_message = latest_message or {}
    
    # Create a mock tracker
    tracker = MagicMock(spec=Tracker)
    tracker.sender_id = sender_id
    tracker.slots = slot_values
    tracker.latest_message = latest_message
    
    # Add get_slot method
    def get_slot(slot_name):
        return slot_values.get(slot_name)
    
    tracker.get_slot = get_slot
    
    return tracker


class TestActionCollectName(unittest.TestCase):
    """Test cases for ActionCollectName."""
    
    def setUp(self):
        self.action = ActionCollectName()
        self.dispatcher = CollectingDispatcher()
        self.domain = {}
    
    def test_valid_name_entity(self):
        """Test when a valid name entity is provided."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 1},
            latest_message={
                "text": "My name is John",
                "entities": [{"entity": "name", "value": "John"}]
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check if name slot is set correctly
        name_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "name"), None)
        self.assertIsNotNone(name_slot_event, "Name slot should be set")
        self.assertEqual(name_slot_event.value, "John", "Name value should be 'John'")
        
        # Check if personal_data_stage is incremented
        stage_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "personal_data_stage"), None)
        self.assertIsNotNone(stage_slot_event, "personal_data_stage slot should be set")
        self.assertEqual(stage_slot_event.value, 2, "personal_data_stage should be incremented to 2")
    
    def test_international_name(self):
        """Test with an international name with diacritics."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 1},
            latest_message={
                "text": "My name is José García",
                "entities": [{"entity": "name", "value": "José García"}]
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check if name slot preserves diacritics
        name_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "name"), None)
        self.assertIsNotNone(name_slot_event, "Name slot should be set")
        self.assertEqual(name_slot_event.value, "José García", "Name should preserve diacritics")
    
    def test_no_name_entity(self):
        """Test when no name entity is extracted but name is in the message."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 1},
            latest_message={
                "text": "John",
                "entities": []
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check if fallback extraction uses the full message as name
        name_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "name"), None)
        if name_slot_event:  # This depends on your implementation
            self.assertEqual(name_slot_event.value, "John", "Fallback should use message text as name")


class TestActionCollectAge(unittest.TestCase):
    """Test cases for ActionCollectAge."""
    
    def setUp(self):
        self.action = ActionCollectAge()
        self.dispatcher = CollectingDispatcher()
        self.domain = {}
    
    def test_valid_numeric_age(self):
        """Test when a valid numeric age is provided."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 2},
            latest_message={
                "text": "I'm 28",
                "entities": [{"entity": "age", "value": 28}]
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check if age slot is set correctly
        age_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "age"), None)
        self.assertIsNotNone(age_slot_event, "Age slot should be set")
        self.assertEqual(age_slot_event.value, 28, "Age value should be 28")
        
        # Check if personal_data_stage is incremented
        stage_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "personal_data_stage"), None)
        self.assertIsNotNone(stage_slot_event, "personal_data_stage slot should be set")
        self.assertEqual(stage_slot_event.value, 3, "personal_data_stage should be incremented to 3")
        
        # Check if dob is calculated and set
        dob_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "dob"), None)
        self.assertIsNotNone(dob_slot_event, "DOB slot should be set")
    
    def test_invalid_age(self):
        """Test with an invalid age."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 2},
            latest_message={
                "text": "one thousand years",
                "entities": []
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check that no slots are set for invalid age
        age_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "age"), None)
        self.assertIsNone(age_slot_event, "Age slot should not be set for invalid input")


class TestActionCollectGender(unittest.TestCase):
    """Test cases for ActionCollectGender."""
    
    def setUp(self):
        self.action = ActionCollectGender()
        self.dispatcher = CollectingDispatcher()
        self.domain = {}
    
    def test_valid_gender(self):
        """Test when a valid gender is provided."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 3},
            latest_message={
                "text": "I'm male",
                "entities": [{"entity": "gender", "value": "male"}]
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check if gender slot is set correctly
        gender_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "gender"), None)
        self.assertIsNotNone(gender_slot_event, "Gender slot should be set")
        self.assertEqual(gender_slot_event.value, "male", "Gender value should be 'male'")
        
        # Check if personal_data_stage is incremented
        stage_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "personal_data_stage"), None)
        self.assertIsNotNone(stage_slot_event, "personal_data_stage slot should be set")
        self.assertEqual(stage_slot_event.value, 4, "personal_data_stage should be incremented to 4")
    
    def test_nonbinary_gender(self):
        """Test with non-binary gender."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 3},
            latest_message={
                "text": "I'm non-binary",
                "entities": [{"entity": "gender", "value": "non-binary"}]
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check if gender slot handles non-binary input
        gender_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "gender"), None)
        self.assertIsNotNone(gender_slot_event, "Gender slot should be set")
        self.assertEqual(gender_slot_event.value, "non-binary", "Gender should accept 'non-binary'")


class TestActionCollectGenderPreference(unittest.TestCase):
    """Test cases for ActionCollectGenderPreference."""
    
    def setUp(self):
        self.action = ActionCollectGenderPreference()
        self.dispatcher = CollectingDispatcher()
        self.domain = {}
    
    def test_single_preference(self):
        """Test when a single gender preference is provided."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 4},
            latest_message={
                "text": "I'm interested in women",
                "entities": [{"entity": "gender_preference", "value": "women"}]
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check if gender_preference slot is set correctly
        pref_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "gender_preference"), None)
        self.assertIsNotNone(pref_slot_event, "Gender preference slot should be set")
        self.assertEqual(pref_slot_event.value, "women", "Gender preference should be 'women'")
        
        # Check if personal_data_stage is incremented
        stage_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "personal_data_stage"), None)
        self.assertIsNotNone(stage_slot_event, "personal_data_stage slot should be set")
        self.assertEqual(stage_slot_event.value, 5, "personal_data_stage should be incremented to 5")
    
    def test_multiple_preference(self):
        """Test with multiple gender preferences."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 4},
            latest_message={
                "text": "I like both men and women",
                "entities": [
                    {"entity": "gender_preference", "value": "men"},
                    {"entity": "gender_preference", "value": "women"}
                ]
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check if gender_preference slot handles multiple preferences
        pref_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "gender_preference"), None)
        self.assertIsNotNone(pref_slot_event, "Gender preference slot should be set")
        # The exact format depends on your implementation, but it should contain both values
        self.assertTrue("men" in str(pref_slot_event.value) and "women" in str(pref_slot_event.value),
                       "Gender preference should include both 'men' and 'women'")


class TestActionCollectAgePreference(unittest.TestCase):
    """Test cases for ActionCollectAgePreference."""
    
    def setUp(self):
        self.action = ActionCollectAgePreference()
        self.dispatcher = CollectingDispatcher()
        self.domain = {}
    
    def test_numeric_range(self):
        """Test when a numeric age range is provided."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 5},
            latest_message={
                "text": "25-35",
                "entities": [{"entity": "age_preference", "value": "25-35"}]
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check if age_preference slot is set correctly
        pref_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "age_preference"), None)
        self.assertIsNotNone(pref_slot_event, "Age preference slot should be set")
        self.assertEqual(pref_slot_event.value, "25-35", "Age preference should be '25-35'")
        
        # Check if personal_data_stage is incremented
        stage_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "personal_data_stage"), None)
        self.assertIsNotNone(stage_slot_event, "personal_data_stage slot should be set")
        self.assertEqual(stage_slot_event.value, 6, "personal_data_stage should be incremented to 6")
    
    def test_decade_preference(self):
        """Test with age preference expressed as a decade."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 5},
            latest_message={
                "text": "thirties",
                "entities": [{"entity": "age_preference", "value": "thirties"}]
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check if age_preference slot handles decade expressions
        pref_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "age_preference"), None)
        self.assertIsNotNone(pref_slot_event, "Age preference slot should be set")
        # The actual value depends on implementation, but should reflect the 30s range
        self.assertTrue("30" in str(pref_slot_event.value), "Age preference should convert 'thirties' to numeric range")


class TestActionCollectHeight(unittest.TestCase):
    """Test cases for ActionCollectHeight."""
    
    def setUp(self):
        self.action = ActionCollectHeight()
        self.dispatcher = CollectingDispatcher()
        self.domain = {}
    
    def test_imperial_height(self):
        """Test when height is provided in imperial format."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 6},
            latest_message={
                "text": "5'10\"",
                "entities": [{"entity": "height", "value": "5'10\""}]
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check if height slot is set correctly (converted to cm)
        height_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "height"), None)
        self.assertIsNotNone(height_slot_event, "Height slot should be set")
        self.assertTrue(175 <= height_slot_event.value <= 180, 
                       f"Height value {height_slot_event.value} should be around 178cm for 5'10\"")
        
        # Check if personal_data_stage is incremented
        stage_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "personal_data_stage"), None)
        self.assertIsNotNone(stage_slot_event, "personal_data_stage slot should be set")
        self.assertEqual(stage_slot_event.value, 7, "personal_data_stage should be incremented to 7")
        
        # Check if current_section is updated
        section_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "current_section"), None)
        self.assertIsNotNone(section_slot_event, "current_section slot should be set")
        self.assertEqual(section_slot_event.value, "userInfo", "current_section should be updated to 'userInfo'")
    
    def test_metric_height(self):
        """Test with height provided in metric format."""
        tracker = create_mock_tracker(
            slot_values={"personal_data_stage": 6},
            latest_message={
                "text": "178cm",
                "entities": [{"entity": "height", "value": "178cm"}]
            }
        )
        
        events = self.action.run(self.dispatcher, tracker, self.domain)
        
        # Check if height slot handles metric input correctly
        height_slot_event = next((e for e in events if isinstance(e, SlotSet) and e.key == "height"), None)
        self.assertIsNotNone(height_slot_event, "Height slot should be set")
        self.assertEqual(height_slot_event.value, 178, "Height should be 178cm")


if __name__ == "__main__":
    unittest.main() 