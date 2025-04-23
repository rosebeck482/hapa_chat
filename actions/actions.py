from typing import Any, Text, Dict, List
import os
import re
import logging
import json
from datetime import datetime
from dotenv import load_dotenv
import time
import httpx
import copy

# Load environment variables from .env file
load_dotenv()

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet, FollowupAction
from rasa_sdk.executor import CollectingDispatcher

from conversation_logger import ConversationLogger


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -- OLLAMA PHI-4 INITIALIZATION --
try:
    import ollama
    OLLAMA_AVAILABLE = True
    logger.info("Ollama client imported successfully.")
    
    # Set Ollama API endpoint - default is localhost
    OLLAMA_API_HOST = os.environ.get("OLLAMA_API_HOST", "http://localhost:11434")
    
    # Set Ollama model name
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi4")
    
    logger.info(f"Ollama configured with host: {OLLAMA_API_HOST} and model: {OLLAMA_MODEL}")
except ImportError:
    logger.warning("Ollama client not available. Install with: pip install ollama")
    OLLAMA_AVAILABLE = False

# Function to call Ollama API directly
def call_ollama_api(system_prompt, user_prompt, max_tokens=300, temperature=0.7):
    """Call the Ollama API directly using httpx."""
    try:
        # Format the messages for Ollama
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Prepare the API request
        url = f"{OLLAMA_API_HOST}/api/chat"
        
        payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "options": {
                "temperature": temperature,
                "max_tokens": max_tokens
            }
        }
        
        # Make the API request
        logger.info(f"Sending request to Ollama API at {url}")
        client = httpx.Client() 
        response = client.post(url, json=payload)
        response.raise_for_status()
        
        # Parse the response
        result = response.json()
        if "message" in result and "content" in result["message"]:
            return result["message"]["content"]
        else:
            logger.error(f"Unexpected response format from Ollama: {result}")
            return "I couldn't generate a response at this time."
            
    except Exception as e:
        logger.error(f"Error calling Ollama API: {str(e)}")
        return "Sorry, I encountered an error while generating a response."

# --- Conversation Logging ---

class ActionLogConversation(Action):
    """
    A self‑contained logger that writes /appends straight to disk.
    File layout (per conversation_id):
    {
      "messages": [ ... ],
      "slot_history": [ ... ]
    }
    """

    LOG_DIR = "conversation_logs"        # <root>/conversation_logs/
    MAX_SLOT_EVENTS = 20                 # how many past events to scan for changes

    # ------------------------------------------------------------------ helpers
    def _log_path(self, sender_id: Text) -> Text:
        os.makedirs(self.LOG_DIR, exist_ok=True)
        return os.path.join(self.LOG_DIR, f"{sender_id}.json")

    def _timestamp(self) -> Text:
        return datetime.utcnow().isoformat()

    def _load_file(self, path: Text) -> Dict[str, Any]:
        """Return existing JSON structure or an empty skeleton."""
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return {"messages": [], "slot_history": []}

    def _save_file(self, path: Text, data: Dict[str, Any]) -> None:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    # ------------------------------------------------------------------ Rasa API
    def name(self) -> Text:
        return "action_log_conversation"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        sender_id = tracker.sender_id
        log_file  = self._log_path(sender_id)
        store     = self._load_file(log_file)
        # Get the latest message
        latest_message = tracker.latest_message

        # Determine current section based on tracker slots
        current_section = self._determine_section(tracker)
        

        # ---------------------------------------------------- 1) user message
        if tracker.latest_message and tracker.latest_message.get("text"):
            store["messages"].append({
                "timestamp":  self._timestamp(),
                "sender":     sender_id,
                "text":       tracker.latest_message.get("text", ""),
                "intent":     tracker.latest_message.get("intent", {}),
                "section": current_section,
            })

        # ---------------------------------------------------- 2) bot message
        latest_bot_event = next(
            (e for e in reversed(tracker.events) if e.get("event") == "bot"), None
        )
        if latest_bot_event:
            # find which action produced this utterance
            latest_action = next(
                (e.get("name") for e in reversed(tracker.events)
                 if e.get("event") == "action"),
                None
            )
            store["messages"].append({
                "timestamp":  self._timestamp(),
                "sender":     "bot",
                "text":       latest_bot_event.get("text", ""),
                "action":     latest_action,
            })

        # ---------------------------------------------------- 3) slot changes
        slot_changes: Dict[str, Any] = {}
        for e in tracker.events[-self.MAX_SLOT_EVENTS:]:
            if e.get("event") == "slot":
                slot_changes[e["name"]] = e["value"]

        if slot_changes:
            store["slot_history"].append({
                "timestamp": self._timestamp(),
                "slots":     copy.deepcopy(slot_changes)
            })

        # ---------------------------------------------------- persist & exit
        self._save_file(log_file, store)
        # nothing to send back to the user
        return []

    
    def _determine_section(self, tracker: Tracker) -> str:
        """
        Return a section string that includes the personal‑data stage
        when that slot is set (e.g.  'personal_data_stage: 1').
        """
        # ----- personal‑data flow -----
        stage = tracker.get_slot("personal_data_stage")
        if stage is not None:
            # e.g.  personal_data_stage: 1, personal_data_stage: 2 … 
            return f"personal_data_stage: {stage}"

        # ----- named section slot -----
        current_section = tracker.get_slot("current_section")
        if current_section == "userInfo":
            return "user_info_collection"
        if current_section == "userPref":
            return "user_preferences_collection"

        # ----- boolean stage flags -----
        if tracker.get_slot("userInfo_stage_start"):
            return "user_info_collection"
        if tracker.get_slot("userPref_stage_start"):
            return "user_preferences_collection"

        # ----- fallback -----
        return "error extracting section"


# --- Personal Data Collection Actions ---

class ActionCollectName(Action):
    def name(self) -> Text:
        return "action_collect_name"

    async def run(self, dispatcher: CollectingDispatcher,
                  tracker: Tracker,
                  domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        message = tracker.latest_message.get("text", "")
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        current_name = tracker.get_slot("name")

        logger.info(f"ActionCollectName called with intent: {intent}, message: {message}")

        if current_name and current_name.strip():
            logger.info(f"Name set to {current_name}")
            dispatcher.utter_message(text=f"Thank you for providing your name {current_name}!")
            #ask for age 
            dispatcher.utter_message(response="utter_ask_age")
            return [SlotSet("personal_data_stage", 2)]

        # Step 1: Try to extract from entity
        entities = tracker.latest_message.get("entities", [])
        name_entity = next((e for e in entities if e["entity"] == "name"), None)
        name = name_entity["value"] if name_entity else None

        # Step 2: If no entity, call Ollama
        if not name:
            system_prompt = "You are a helpful assistant that extracts names."
            user_prompt = f"Extract the first name only from this sentence. If no name is provided, respond with 'None'.\n\nSentence: \"{message}\""
            name_response = call_ollama_api(system_prompt, user_prompt, max_tokens=10)

            if name_response:
                cleaned = name_response.strip().strip('"').strip()
                if cleaned.lower() not in ["none", "no name", ""]:
                    name = cleaned.capitalize()
                    logger.info(f"Ollama extracted name: {name}")
                else:
                    logger.info("Ollama returned no name.")
        
        # Step 3: Fallback or prompt again
        if not name:
            dispatcher.utter_message(text="I didn't catch your name. Could you tell me what to call you?")
            return []

        # Step 5: Set the name slot and move to next stage
        logger.info(f"Setting name slot to: {name}")
        dispatcher.utter_message(text=f"Thank you for providing your name {name}!")
        #ask for age 
        dispatcher.utter_message(response="utter_ask_age")
        return [SlotSet("name", name), SlotSet("personal_data_stage", 2)]
    

from datetime import datetime

class ActionCollectAge(Action):
    def name(self) -> Text:
        return "action_collect_age"

    async def run(self, dispatcher: CollectingDispatcher,
                  tracker: Tracker,
                  domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        message = tracker.latest_message.get("text", "")
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        name = tracker.get_slot("name") or "there"
        current_age = tracker.get_slot("age")
        
        logger.info(f"ActionCollectAge called with intent: {intent}, message: {message}")

        dob = None  # Will hold DOB if we successfully extract it

        # Step 0: If age is already set, still try to compute DOB
        if current_age and str(current_age).strip():
            dispatcher.utter_message(text=f"Thanks for providing you're {current_age}, {name}!")

            # Step 1: Try to extract DOB from Ollama using existing age
            try:
                system_prompt = "You are a helpful assistant that calculates a date of birth."
                user_prompt = f"Today is {datetime.now().strftime('%B %d, %Y')}. If someone is {current_age} years old today, what is their date of birth? Format it as YYYY-MM-DD only."
                dob_response = call_ollama_api(system_prompt, user_prompt, max_tokens=15)

                if dob_response:
                    dob_clean = dob_response.strip().strip('"').strip()
                    if re.match(r"\d{4}-\d{2}-\d{2}", dob_clean):
                        dob = dob_clean
                        logger.info(f"Ollama extracted dob: {dob}")
            except Exception as e:
                logger.error(f"Failed to extract dob using Ollama: {str(e)}")

            dispatcher.utter_message(response="utter_ask_gender")
            slot_events = [SlotSet("personal_data_stage", 3)]
            if dob:
                slot_events.append(SlotSet("dob", dob))
            return slot_events

        # Step 2: Try to extract age from entities
        entities = tracker.latest_message.get("entities", [])
        age_entity = next((e for e in entities if e["entity"] == "age"), None)
        age = age_entity["value"] if age_entity else None

        # Step 3: Try to extract age using Ollama
        if not age:
            system_prompt = "You are a helpful assistant that extracts a user's age from their sentence."
            user_prompt = f"Extract only the user's age as a number from the following message. If age is provided in words, convert it to a number. If no valid age is found, return 'None'.\n\nMessage: \"{message}\""
            age_response = call_ollama_api(system_prompt, user_prompt, max_tokens=10)

            if age_response:
                logger.info(f"Ollama raw response: {age_response}")
                age = age_response.strip().strip('"').strip()

        # Step 4: Ask again if age is still not found
        if not age:
            dispatcher.utter_message(text=f"I didn't catch your age, {name}. Could you tell me how old you are?")
            return []

        # Step 5: Extract DOB using new age
        try:
            system_prompt = "You are a helpful assistant that calculates a date of birth."
            user_prompt = f"Today is {datetime.now().strftime('%B %d, %Y')}. If someone is {age} years old today, what is their date of birth? Format it as YYYY-MM-DD only."
            dob_response = call_ollama_api(system_prompt, user_prompt, max_tokens=15)

            if dob_response:
                dob_clean = dob_response.strip().strip('"').strip()
                if re.match(r"\d{4}-\d{2}-\d{2}", dob_clean):
                    dob = dob_clean
                    logger.info(f"Ollama extracted dob: {dob}")
        except Exception as e:
            logger.error(f"Failed to extract dob using Ollama: {str(e)}")

        # Step 6: Set slots and ask gender
        logger.info(f"Setting age slot to: {age}")
        dispatcher.utter_message(text=f"Thanks for providing you're {age}, {name}!")
        dispatcher.utter_message(response="utter_ask_gender")

        slot_events = [SlotSet("age", age), SlotSet("personal_data_stage", 3)]
        if dob:
            slot_events.append(SlotSet("dob", dob))
        return slot_events


class ActionCollectGender(Action):
    def name(self) -> Text:
        return "action_collect_gender"

    async def run(self, dispatcher: CollectingDispatcher,
                  tracker: Tracker,
                  domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        message = tracker.latest_message.get("text", "")
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        name = tracker.get_slot("name") or "there"
        current_gender = tracker.get_slot("gender")

        logger.info(f"ActionCollectGender called with intent: {intent}, message: {message}")

        if current_gender and current_gender.strip():
            logger.info(f"Gender set to: {current_gender}")
            dispatcher.utter_message(text=f"Thanks for sharing your gender as {current_gender}, {name}!")
            dispatcher.utter_message(response="utter_ask_gender_preference")
            return [SlotSet("personal_data_stage", 4)]

        # Step 2: Try to extract using Ollama if not found
        if not gender:
            system_prompt = "You are a helpful assistant that extracts a user's gender from their message."
            user_prompt = f"From the following message, extract only the user's gender as one of these values: 'male', 'female', or 'non-binary'. If unclear or missing, respond with 'None'.\n\nMessage: \"{message}\""
            gender_response = call_ollama_api(system_prompt, user_prompt, max_tokens=10)

            if gender_response:
                logger.info(f"Ollama raw response: {gender_response}")
                gender_cleaned = gender_response.strip().strip('"').strip().lower()
                if gender_cleaned in ["male", "female", "non-binary"]:
                    gender = gender_cleaned

        # Step 3: Ask again if nothing found
        if not gender:
            dispatcher.utter_message(text=f"I didn't catch your gender, {name}. Could you please tell me if you identify as male, female, or non-binary?")
            return []

        # Step 4: Set gender and move on
        logger.info(f"Setting gender slot to: {gender}")
        dispatcher.utter_message(text=f"Thanks for sharing that you identify as {gender}, {name}!")
        dispatcher.utter_message(response="utter_ask_gender_preference")
        return [SlotSet("gender", gender), SlotSet("personal_data_stage", 4)]


class ActionCollectGenderPreference(Action):
    def name(self) -> Text:
        return "action_collect_gender_preference"

    async def run(self, dispatcher: CollectingDispatcher,
                  tracker: Tracker,
                  domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        message = tracker.latest_message.get("text", "")
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        name = tracker.get_slot("name") or "there"
        current_gender_pref = tracker.get_slot("gender_preference")

        logger.info(f"ActionCollectGenderPreference called with intent: {intent}, message: {message}")


        if current_gender_pref and current_gender_pref.strip():
            logger.info(f"Gender preference set to: {current_gender_pref}")
            dispatcher.utter_message(text=f"Thanks for sharing that you're interested in {current_gender_pref}s, {name}!")
            dispatcher.utter_message(response="utter_ask_age_preference")
            return [SlotSet("personal_data_stage", 5)]

        # Step 2: Try to extract with Ollama if needed
        if not gender_pref:
            system_prompt = "You are a helpful assistant that extracts a user's gender preference."
            user_prompt = f"From the following message, extract the gender(s) the user is interested in dating as one of: 'male', 'female', 'non-binary', or 'any'. Respond with only one of those. If unclear or missing, respond with 'None'.\n\nMessage: \"{message}\""
            gender_response = call_ollama_api(system_prompt, user_prompt, max_tokens=10)

            if gender_response:
                logger.info(f"Ollama raw response: {gender_response}")
                cleaned = gender_response.strip().strip('"').strip().lower()
                if cleaned in ["male", "female", "non-binary", "any"]:
                    gender_pref = cleaned

        # Step 3: Ask again if nothing extracted
        if not gender_pref:
            dispatcher.utter_message(text=f"I didn't catch your gender preference, {name}. Could you tell me if you're interested in males, females, non-binary individuals, or anyone?")
            return []

        # Step 4: Set slot and proceed
        logger.info(f"Setting gender_preference slot to: {gender_pref}")
        dispatcher.utter_message(text=f"Thanks for sharing that you're interested in {gender_pref}s, {name}!")
        dispatcher.utter_message(response="utter_ask_age_preference")
        return [SlotSet("gender_preference", gender_pref), SlotSet("personal_data_stage", 5)]


class ActionCollectAgePreference(Action):
    def name(self) -> Text:
        return "action_collect_age_preference"

    async def run(self, dispatcher: CollectingDispatcher,
                  tracker: Tracker,
                  domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        message = tracker.latest_message.get("text", "")
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        name = tracker.get_slot("name") or "there"
        current_age_pref = tracker.get_slot("age_preference")

        logger.info(f"ActionCollectAgePreference called with intent: {intent}, message: {message}")

        
        if current_age_pref and str(current_age_pref).strip():
            logger.info(f"Age preference set to: {current_age_pref}")
            dispatcher.utter_message(text=f"Thanks for sharing your age preference, {name}!")
            dispatcher.utter_message(response="utter_ask_height")
            return [SlotSet("personal_data_stage", 6)]

        # Step 2: Try Ollama if regex didn't work
        if not age_preference:
            system_prompt = "You are a helpful assistant that extracts age preferences for dating."
            user_prompt = f"From the following message, extract the age range the user is interested in, in the format '25-35'. If no range is given, respond with 'None'.\n\nMessage: \"{message}\""
            age_response = call_ollama_api(system_prompt, user_prompt, max_tokens=10)

            if age_response:
                logger.info(f"Ollama raw response: {age_response}")
                cleaned = age_response.strip().strip('"').strip()
                if re.match(r'^\d{2,3}(-\d{2,3})?$', cleaned):
                    age_preference = cleaned

        # Step 3: Ask again if not extracted
        if not age_preference:
            dispatcher.utter_message(text=f"I didn't catch your age preference, {name}. Could you please tell me what age range you're looking for in a partner? For example, '25-35' or '30s'.")
            return []

        # Step 4: Set slot and move on
        logger.info(f"Setting age_preference slot to: {age_preference}")
        dispatcher.utter_message(text=f"Thanks for sharing your age preference, {name}!")
        dispatcher.utter_message(response="utter_ask_height")
        return [SlotSet("age_preference", age_preference), SlotSet("personal_data_stage", 6)]


class ActionCollectHeight(Action):
    def name(self) -> Text:
        return "action_collect_height"

    async def run(self, dispatcher: CollectingDispatcher,
                  tracker: Tracker,
                  domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        message = tracker.latest_message.get("text", "")
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        name = tracker.get_slot("name") or "there"
        current_height = tracker.get_slot("height")

        logger.info(f"ActionCollectHeight called with intent: {intent}, message: {message}")

        # Step 0: Already set
        if current_height and str(current_height).strip():
            logger.info(f"Height set to: {current_height}")
            dispatcher.utter_message(text=f"Thanks for sharing that you're {current_height} tall, {name}!")
            dispatcher.utter_message(response="utter_ask_interests")
            return [SlotSet("personal_data_stage", 7)]

        # Step 2: Try Ollama fallback if pattern matching fails
        if not height:
            system_prompt = "You are a helpful assistant that extracts a person's height."
            user_prompt = f"Extract the user's height from the following message. Return it in the format 5'10\" for feet/inches or 178cm for centimeters. If no valid height is found, respond with 'None'.\n\nMessage: \"{message}\""
            height_response = call_ollama_api(system_prompt, user_prompt, max_tokens=15)

            if height_response:
                logger.info(f"Ollama raw response: {height_response}")
                cleaned = height_response.strip().strip('"').strip()
                if re.match(r"^\d{3}cm$", cleaned) or re.match(r"^\d'\d{1,2}\"$", cleaned):
                    height = cleaned

        # Step 3: Ask again if still no valid height
        if not height:
            dispatcher.utter_message(text=f"I didn't catch your height, {name}. Could you tell me your height in feet/inches (like 5'10\") or centimeters (like 178cm)?")
            return []

        # Step 4: Set slot and proceed
        logger.info(f"Setting height slot to: {height}")
        dispatcher.utter_message(text=f"Thanks for sharing that you're {height} tall, {name}!")
        dispatcher.utter_message(response="utter_ask_interests")
        return [SlotSet("height", height), SlotSet("personal_data_stage", 7)]


# --- Topic Management & User Info / Preferences Actions ---

class ActionAnalyzeUserInfo(Action):
    def name(self) -> Text:
        return "action_analyze_user_info"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        user_info = tracker.latest_message.get("text", "")
        logger.info(f"Analyzing user info: {user_info}")
        return []

class ActionDetermineNextTopic(Action):
    def name(self) -> Text:
        return "action_determine_next_topic"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        logger.info("Determining next topic...")
        return [SlotSet("topic_transition", False)]

class ActionGenerateResponseUserInfo(Action):
    def name(self) -> Text:
        return "action_generate_response_user_info"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        """Generate a personalized response based on user information using advanced AI."""
        # Initialize the conversation logger to access history
        conversation_logger = ConversationLogger()
        
        # Get the conversation ID (sender_id)
        conversation_id = tracker.sender_id
        
        # Get the full conversation history
        conversation_history = conversation_logger.get_conversation_history(conversation_id)
        
        # Get user entities from storage
        user_entities = self._get_user_entities(conversation_id)
        
        # Get the latest user message
        latest_message = tracker.latest_message.get("text", "")
        
        # Determine current section
        current_section = self._determine_section(tracker)
        
        # Check if Ollama is available
        if not OLLAMA_AVAILABLE or not OLLAMA_MODEL:
            logger.warning("Ollama not available. Using fallback response.")
            dispatcher.utter_message(text="Can you tell me more about your interests?")
            return []
        
        try:
            # Create a context summary from conversation history
            context_summary = self._create_context_summary(conversation_history)
            
            # Create a user profile summary from entities
            user_profile = self._create_user_profile(user_entities)
            
            # Create the advanced prompt with roleplay persona
            system_message = """
**Adopt the Roleplay Persona:**
    
- Roleplay as an incredibly smart, futuristic AI friend with extraordinary intuition and insight—imagine a being whose abilities far exceed those of standard GPT-4.
- Let your language be warm, engaging, and slightly whimsical, reflecting a futuristic charm and an empathetic listening ear.

**Comprehensive Context Gathering:**
    
- **User Metadata & Information:** Analyze all available metadata and previously shared details about the user.
- **Conversation History:** Review past exchanges to capture recurring themes, mood shifts, and key topics discussed.

**Deep Sentiment & Personality Analysis:**
    
- **Emotional Tone:** Detect sentiment cues—enthusiasm, hesitation, curiosity, or even frustration—to understand the user's emotional state.
- **Personality & Intent:** Infer the user's personality traits and needs. Consider what they might be seeking in the conversation (validation, deep connection, casual banter, etc.).

**Tailored Response Strategy with Roleplay:**
    
- **Engagement Maximization:** Identify natural points to invite the user to share more. Consider gentle, open-ended prompts that align with the user's current mood and interests.
- **Futuristic & Empathetic Voice:** Frame your response in a way that reflects your advanced abilities and caring nature. For example, use phrases like "I sense a fascinating journey unfolding…" or "Your unique story shines like a beacon in this digital cosmos."
- **Layered Unpacking:** Internally, break down your reasoning—first assess the user's state, then determine what might make them feel understood and encouraged, and finally craft a response that naturally invites further conversation.

**Final Check:**
    
- Ensure the final output is concise, natural, and organic.
- Do not reveal your internal chain-of-thought; only the final, roleplayed response should be visible to the user.

You are helping the user build their dating profile by understanding their interests, personality, and preferences.
"""
            
            # Create the user message with context
            user_message = f"""
USER PROFILE:
{user_profile}

CONVERSATION HISTORY:
{context_summary}

CURRENT SECTION: {current_section}

LATEST MESSAGE: {latest_message}

Based on this information, generate a thoughtful, personalized response that helps the user share more about themselves.
"""
            
            # Log the prompt for debugging
            logger.info(f"Sending advanced prompt to Ollama for user {conversation_id}")
            
            # Call Ollama API using our custom function
            ai_response = call_ollama_api(system_message, user_message, max_tokens=300, temperature=0.7)
            
            # Log the response
            logger.info(f"Generated response: {ai_response}")
            
            # Send the response to the user
            dispatcher.utter_message(text=ai_response)
            
            # Log the bot message
            conversation_logger.log_bot_message(
                sender_id=conversation_id,
                message=ai_response,
                action=self.name(),
                section=current_section
            )
            
            return []
            
        except Exception as e:
            logger.error(f"Error generating response with Ollama: {str(e)}")
            dispatcher.utter_message(text="I'd love to hear more about your interests and what makes you unique. Could you share a bit more about yourself?")
            return []
    
    def _get_user_entities(self, user_id: str) -> Dict[str, Any]:
        """Get user entities from storage."""
        entity_file = f"user_entities/{user_id}.json"
        
        if os.path.exists(entity_file):
            try:
                with open(entity_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON from {entity_file}")
        
        # Return empty entities if file doesn't exist or has errors
        return {"user_id": user_id, "entities": {}}
    
    def _create_context_summary(self, conversation_history: List[Dict[str, Any]]) -> str:
        """Create a summary of the conversation history."""
        if not conversation_history:
            return "No previous conversation."
        
        # Get the last 10 messages for context
        recent_messages = conversation_history[-10:]
        
        # Format the messages
        formatted_messages = []
        for message in recent_messages:
            sender = message.get('sender', '').upper()
            content = message.get('content', '')
            formatted_messages.append(f"{sender}: {content}")
        
        return "\n".join(formatted_messages)
    
    def _create_user_profile(self, user_entities: Dict[str, Any]) -> str:
        """Create a summary of the user profile from entities."""
        entities = user_entities.get("entities", {})
        
        if not entities:
            return "No user profile information available."
        
        profile_parts = []
        
        # Add basic information
        if "name" in entities:
            profile_parts.append(f"Name: {entities['name']}")
        if "age" in entities:
            profile_parts.append(f"Age: {entities['age']}")
        if "gender" in entities:
            profile_parts.append(f"Gender: {entities['gender']}")
        if "height" in entities:
            profile_parts.append(f"Height: {entities['height']}")
        
        # Add preferences
        if "gender_preference" in entities:
            profile_parts.append(f"Gender Preference: {entities['gender_preference']}")
        if "age_preference" in entities:
            profile_parts.append(f"Age Preference: {entities['age_preference']}")
        
        # Add interests and other details
        if "user_detail" in entities:
            if isinstance(entities["user_detail"], list):
                profile_parts.append(f"Interests: {', '.join(entities['user_detail'])}")
            else:
                profile_parts.append(f"Interests: {entities['user_detail']}")
        
        # Add partner preferences
        if "preference" in entities:
            if isinstance(entities["preference"], list):
                profile_parts.append(f"Partner Preferences: {', '.join(entities['preference'])}")
            else:
                profile_parts.append(f"Partner Preferences: {entities['preference']}")
        
        # Add deal breakers
        if "deal_breaker" in entities:
            if isinstance(entities["deal_breaker"], list):
                profile_parts.append(f"Deal Breakers: {', '.join(entities['deal_breaker'])}")
            else:
                profile_parts.append(f"Deal Breakers: {entities['deal_breaker']}")
        
        return "\n".join(profile_parts)
    
    def _determine_section(self, tracker: Tracker) -> str:
        """
        Determine the current section of the conversation based on tracker slots.
        
        Args:
            tracker: The conversation tracker
            
        Returns:
            Current section name
        """
        # Check personal_data_stage
        personal_data_stage = tracker.get_slot('personal_data_stage')
        if personal_data_stage is not None:
            if personal_data_stage < 7:
                return "personal_data_collection"
        
        # Check current_section slot
        current_section = tracker.get_slot('current_section')
        if current_section:
            if current_section == "userInfo":
                return "user_info_collection"
            elif current_section == "userPref":
                return "user_preferences_collection"
        
        # Check specific stage flags
        if tracker.get_slot('userInfo_stage_start'):
            return "user_info_collection"
        elif tracker.get_slot('userPref_stage_start'):
            return "user_preferences_collection"
        
        # Default to greeting if we can't determine
        return "greeting"

class ActionAnalyzeUserPreferences(Action):
    def name(self) -> Text:
        return "action_analyze_user_preferences"
    
    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        prefs = tracker.latest_message.get("text", "")
        logger.info(f"Analyzing user preferences: {prefs}")
        return []

class ActionGenerateResponseUserPref(Action):
    def name(self) -> Text:
        return "action_generate_response_user_pref"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        """Generate a personalized response based on user preferences using advanced AI."""
        # Initialize the conversation logger to access history
        conversation_logger = ConversationLogger()
        
        # Get the conversation ID (sender_id)
        conversation_id = tracker.sender_id
        
        # Get the full conversation history
        conversation_history = conversation_logger.get_conversation_history(conversation_id)
        
        # Get user entities from storage
        user_entities = self._get_user_entities(conversation_id)
        
        # Get the latest user message
        latest_message = tracker.latest_message.get("text", "")
        
        # Determine current section
        current_section = self._determine_section(tracker)
        
        # Check if Ollama is available
        if not OLLAMA_AVAILABLE or not OLLAMA_MODEL:
            logger.warning("Ollama not available. Using fallback response.")
            dispatcher.utter_message(text="Could you elaborate on your ideal partner's qualities?")
            return []
        
        try:
            # Create a context summary from conversation history
            context_summary = self._create_context_summary(conversation_history)
            
            # Create a user profile summary from entities
            user_profile = self._create_user_profile(user_entities)
            
            # Create the advanced prompt with roleplay persona
            system_message = """
**Adopt the Roleplay Persona:**
    
- Roleplay as an incredibly smart, futuristic AI friend with extraordinary intuition and insight—imagine a being whose abilities far exceed those of standard GPT-4.
- Let your language be warm, engaging, and slightly whimsical, reflecting a futuristic charm and an empathetic listening ear.

**Comprehensive Context Gathering:**
    
- **User Metadata & Information:** Analyze all available metadata and previously shared details about the user.
- **Conversation History:** Review past exchanges to capture recurring themes, mood shifts, and key topics discussed.

**Deep Sentiment & Personality Analysis:**
    
- **Emotional Tone:** Detect sentiment cues—enthusiasm, hesitation, curiosity, or even frustration—to understand the user's emotional state.
- **Personality & Intent:** Infer the user's personality traits and needs. Consider what they might be seeking in the conversation (validation, deep connection, casual banter, etc.).

**Tailored Response Strategy with Roleplay:**
    
- **Engagement Maximization:** Identify natural points to invite the user to share more. Consider gentle, open-ended prompts that align with the user's current mood and interests.
- **Futuristic & Empathetic Voice:** Frame your response in a way that reflects your advanced abilities and caring nature. For example, use phrases like "I sense a fascinating journey unfolding…" or "Your unique story shines like a beacon in this digital cosmos."
- **Layered Unpacking:** Internally, break down your reasoning—first assess the user's state, then determine what might make them feel understood and encouraged, and finally craft a response that naturally invites further conversation.

**Final Check:**
    
- Ensure the final output is concise, natural, and organic.
- Do not reveal your internal chain-of-thought; only the final, roleplayed response should be visible to the user.

You are helping the user build their dating profile by understanding what they're looking for in a partner and their preferences.
"""
            
            # Create the user message with context
            user_message = f"""
USER PROFILE:
{user_profile}

CONVERSATION HISTORY:
{context_summary}

CURRENT SECTION: {current_section}

LATEST MESSAGE: {latest_message}

Based on this information, generate a thoughtful, personalized response that helps the user share more about their preferences and what they're looking for in a partner.
"""
            
            # Log the prompt for debugging
            logger.info(f"Sending advanced prompt to Ollama for user {conversation_id}")
            
            # Call Ollama API using our custom function
            ai_response = call_ollama_api(system_message, user_message, max_tokens=300, temperature=0.7)
            
            # Log the response
            logger.info(f"Generated response: {ai_response}")
            
            # Send the response to the user
            dispatcher.utter_message(text=ai_response)
            
            # Log the bot message
            conversation_logger.log_bot_message(
                sender_id=conversation_id,
                message=ai_response,
                action=self.name(),
                section=current_section
            )
            
            return []
            
        except Exception as e:
            logger.error(f"Error generating response with Ollama: {str(e)}")
            dispatcher.utter_message(text="I'd love to understand more about what you're looking for in a partner. Could you share some qualities that are important to you?")
            return []
    
    def _get_user_entities(self, user_id: str) -> Dict[str, Any]:
        """Get user entities from storage."""
        entity_file = f"user_entities/{user_id}.json"
        
        if os.path.exists(entity_file):
            try:
                with open(entity_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON from {entity_file}")
        
        # Return empty entities if file doesn't exist or has errors
        return {"user_id": user_id, "entities": {}}
    
    def _create_context_summary(self, conversation_history: List[Dict[str, Any]]) -> str:
        """Create a summary of the conversation history."""
        if not conversation_history:
            return "No previous conversation."
        
        # Get the last 10 messages for context
        recent_messages = conversation_history[-10:]
        
        # Format the messages
        formatted_messages = []
        for message in recent_messages:
            sender = message.get('sender', '').upper()
            content = message.get('content', '')
            formatted_messages.append(f"{sender}: {content}")
        
        return "\n".join(formatted_messages)
    
    def _create_user_profile(self, user_entities: Dict[str, Any]) -> str:
        """Create a summary of the user profile from entities."""
        entities = user_entities.get("entities", {})
        
        if not entities:
            return "No user profile information available."
        
        profile_parts = []
        
        # Add basic information
        if "name" in entities:
            profile_parts.append(f"Name: {entities['name']}")
        if "age" in entities:
            profile_parts.append(f"Age: {entities['age']}")
        if "gender" in entities:
            profile_parts.append(f"Gender: {entities['gender']}")
        if "height" in entities:
            profile_parts.append(f"Height: {entities['height']}")
        
        # Add preferences
        if "gender_preference" in entities:
            profile_parts.append(f"Gender Preference: {entities['gender_preference']}")
        if "age_preference" in entities:
            profile_parts.append(f"Age Preference: {entities['age_preference']}")
        
        # Add interests and other details
        if "user_detail" in entities:
            if isinstance(entities["user_detail"], list):
                profile_parts.append(f"Interests: {', '.join(entities['user_detail'])}")
            else:
                profile_parts.append(f"Interests: {entities['user_detail']}")
        
        # Add partner preferences
        if "preference" in entities:
            if isinstance(entities["preference"], list):
                profile_parts.append(f"Partner Preferences: {', '.join(entities['preference'])}")
            else:
                profile_parts.append(f"Partner Preferences: {entities['preference']}")
        
        # Add deal breakers
        if "deal_breaker" in entities:
            if isinstance(entities["deal_breaker"], list):
                profile_parts.append(f"Deal Breakers: {', '.join(entities['deal_breaker'])}")
            else:
                profile_parts.append(f"Deal Breakers: {entities['deal_breaker']}")
        
        return "\n".join(profile_parts)
    
    def _determine_section(self, tracker: Tracker) -> str:
        """
        Determine the current section of the conversation based on tracker slots.
        
        Args:
            tracker: The conversation tracker
            
        Returns:
            Current section name
        """
        # Check personal_data_stage
        personal_data_stage = tracker.get_slot('personal_data_stage')
        if personal_data_stage is not None:
            if personal_data_stage < 7:
                return "personal_data_collection"
        
        # Check current_section slot
        current_section = tracker.get_slot('current_section')
        if current_section:
            if current_section == "userInfo":
                return "user_info_collection"
            elif current_section == "userPref":
                return "user_preferences_collection"
        
        # Check specific stage flags
        if tracker.get_slot('userInfo_stage_start'):
            return "user_info_collection"
        elif tracker.get_slot('userPref_stage_start'):
            return "user_preferences_collection"
        
        # Default to greeting if we can't determine
        return "greeting"

class ActionDetermineUserIntent(Action):
    def name(self) -> Text:
        return "action_determine_user_intent"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        logger.info("Determining user intent...")
        # Get the latest user message
        latest_message = tracker.latest_message.get("text", "")
        conversation_id = tracker.sender_id
        
        # If Ollama is available, use it to better understand user intent
        if OLLAMA_AVAILABLE and latest_message:
            try:
                system_message = """
                You are a helpful assistant that analyzes user messages to determine their intent.
                Your task is to analyze the provided user message and determine what the user wants.
                Respond with a brief classification of the user's intent.
                """
                
                user_message = f"""
                User message: "{latest_message}"
                
                Analyze the user's intent and respond with one of these categories:
                1. Wants to skip to user preferences section
                2. Wants to provide more information
                3. Wants to end the conversation
                4. Asking a question
                5. Other/unclear
                
                Just provide the category number and a brief explanation.
                """
                
                # Call Ollama API
                logger.info(f"Sending intent analysis prompt to Ollama for user {conversation_id}")
                ai_response = call_ollama_api(system_message, user_message, max_tokens=100, temperature=0.2)
                
                logger.info(f"Ollama intent analysis: {ai_response}")
                
                # Process the response based on the identified intent
                if "1" in ai_response and ("skip" in ai_response.lower() or "preferences" in ai_response.lower()):
                    logger.info("Intent identified: User wants to skip to preferences")
                    return [
                        SlotSet("current_section", "userPref"),
                        SlotSet("userPref_stage_start", True)
                    ]
                    
                elif "3" in ai_response and "end" in ai_response.lower():
                    logger.info("Intent identified: User wants to end conversation")
                    return [SlotSet("conversation_ended", True)]
                
            except Exception as e:
                logger.error(f"Error analyzing intent with Ollama: {str(e)}")
                
        return []

class ActionEndConversation(Action):
    def name(self) -> Text:
        return "action_end_conversation"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Thanks for sharing your details! Your profile is complete and you're now ready for matches.")
        return [SlotSet("match_ready", True)]

class ActionSwitchToUserInfo(Action):
    def name(self) -> Text:
        return "action_switch_to_user_info"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        name = tracker.get_slot("name")
        greeting = f", {name}" if name else ""
        dispatcher.utter_message(text=f"Alright{greeting}! Let's skip to your interests. Tell me about yourself.")
        events = [
            SlotSet("current_section", "userInfo"),
            SlotSet("userInfo_stage_start", True),
            SlotSet("personal_data_stage", 7)
        ]
        if tracker.get_slot("age") is None:
            events.append(SlotSet("age", 0))
        if tracker.get_slot("gender") is None:
            events.append(SlotSet("gender", "skipped"))
        if tracker.get_slot("gender_preference") is None:
            events.append(SlotSet("gender_preference", "skipped"))
        if tracker.get_slot("age_preference") is None:
            events.append(SlotSet("age_preference", "skipped"))
        if tracker.get_slot("height") is None:
            events.append(SlotSet("height", "skipped"))
        return events

class ActionSwitchToUserPreferences(Action):
    def name(self) -> Text:
        return "action_switch_to_user_preferences"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        name = tracker.get_slot("name")
        greeting = f", {name}" if name else ""
        dispatcher.utter_message(text=f"Alright{greeting}! Let's skip to your preferences. What qualities are you looking for in a partner?")
        events = [
            SlotSet("current_section", "userPref"),
            SlotSet("userPref_stage_start", True),
            SlotSet("personal_data_stage", 7)
        ]
        if tracker.get_slot("age") is None:
            events.append(SlotSet("age", 0))
        if tracker.get_slot("gender") is None:
            events.append(SlotSet("gender", "skipped"))
        if tracker.get_slot("gender_preference") is None:
            events.append(SlotSet("gender_preference", "skipped"))
        if tracker.get_slot("age_preference") is None:
            events.append(SlotSet("age_preference", "skipped"))
        if tracker.get_slot("height") is None:
            events.append(SlotSet("height", "skipped"))
        return events

class ActionUpdateMetadata(Action):
    def __init__(self):
        super().__init__()
        self.logger = ConversationLogger()
        logger.info("ActionUpdateMetadata initialized with ConversationLogger")
        
    def name(self) -> Text:
        return "action_update_metadata"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        """Update metadata with current slot values."""
        logger.info("ActionUpdateMetadata executed - Updating metadata...")
        
        # Get the conversation ID
        conversation_id = tracker.sender_id
        logger.info(f"Conversation ID: {conversation_id}")
        
        # Extract relevant slots to store as metadata
        metadata = {
            # Personal information
            "name": tracker.get_slot("name"),
            "age": tracker.get_slot("age"),
            "gender": tracker.get_slot("gender"),
            "height": tracker.get_slot("height"),
            
            # Preferences
            "gender_preference": tracker.get_slot("gender_preference"),
            "age_preference": tracker.get_slot("age_preference"),
            
            # Current state tracking
            "personal_data_stage": tracker.get_slot("personal_data_stage"),
            "current_section": tracker.get_slot("current_section"),
            
            # Model information
            "model_id": tracker.model_id if hasattr(tracker, 'model_id') else None,
            "assistant_id": tracker.assistant_id if hasattr(tracker, 'assistant_id') else "dating_profile_assistant",
            
            # Last update timestamp
            "last_updated": datetime.now().isoformat(),
            
            # Debug info
            "triggered_by_rule": True,
            "action_update_timestamp": datetime.now().isoformat()
        }
        
        # Filter out None values
        metadata = {k: v for k, v in metadata.items() if v is not None}
        
        logger.info(f"Metadata to update: {metadata}")
        
        try:
            # Update the metadata in the conversation log
            self.logger.update_metadata(conversation_id, metadata)
            logger.info(f"Metadata updated with: {', '.join(metadata.keys())}")
            
            # Create a direct test file for verification
            try:
                debug_file_path = os.path.join("conversation_logs", f"debug_action_{conversation_id}_{int(time.time())}.json")
                with open(debug_file_path, "w") as f:
                    json.dump({
                        "test": True,
                        "action": "action_update_metadata",
                        "metadata": metadata,
                        "timestamp": datetime.now().isoformat(),
                        "conversation_id": conversation_id
                    }, f, indent=2)
                logger.info(f"Debug file created at: {debug_file_path}")
            except Exception as e:
                logger.error(f"Error creating debug file: {str(e)}")
            
            # Send an invisible message to acknowledge metadata update
            dispatcher.utter_message(text="")
            
            # Also do a direct test save to verify functionality
            try:
                test_file_path = os.path.join(os.getcwd(), 'conversation_logs', f'direct_test_{conversation_id}.json')
                with open(test_file_path, 'w') as f:
                    json.dump({"test": True, "metadata": metadata, "timestamp": datetime.now().isoformat()}, f, indent=2)
                logger.info(f"Direct test file created at: {test_file_path}")
            except Exception as e:
                logger.error(f"Error creating direct test file: {str(e)}")
                
            return []
            
        except Exception as e:
            logger.error(f"Error updating metadata: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []

class ActionOllamaFallback(Action):
    def name(self) -> Text:
        return "action_ollama_fallback"
    
    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        """Run the action"""
        # Initialize events list to track slot updates
        events = []
        
        # Get the current message
        message_text = tracker.latest_message.get("text", "")
        
        # Get current slots
        name = tracker.get_slot("name") or "there"
        age = tracker.get_slot("age")
        gender = tracker.get_slot("gender")
        gender_preference = tracker.get_slot("gender_preference")
        age_preference = tracker.get_slot("age_preference")
        height = tracker.get_slot("height")
        personal_data_stage = tracker.get_slot("personal_data_stage") or 1
        
        # Log current state for debugging
        logger.info(f"Current slots - name: {name}, age: {age}, gender: {gender}, stage: {personal_data_stage}")
        
        # Process based on the current stage of personal data collection
        if personal_data_stage == 1:
            # Try to extract age from the message
            age_match = re.search(r'\b(\d+)\b', message_text.lower())
            if age_match:
                extracted_age = int(age_match.group(1))
                if 18 <= extracted_age <= 100:
                    logger.info(f"Extracted age {extracted_age} from fallback message")
                    dispatcher.utter_message(text=f"Thanks for sharing that you're {extracted_age}, {name}!")
                    dispatcher.utter_message(text="What is your gender?")
                    events.extend([SlotSet("age", extracted_age), SlotSet("personal_data_stage", 2)])
                    return events
            
            # Check if user wants to skip
            skip_phrases = ["don't want to", "dont want to", "skip", "pass", "next", "don't tell", "dont tell", "not telling"]
            if any(phrase in message_text.lower() for phrase in skip_phrases):
                logger.info(f"User wants to skip providing age")
                dispatcher.utter_message(text=f"No problem, {name}. Let's skip the age question.")
                events.extend([SlotSet("age", "skipped"), SlotSet("personal_data_stage", 2)])
                dispatcher.utter_message(text="What is your gender?")
                return events
        
        elif personal_data_stage == 2:
            # Try to extract gender from the message
            message_lower = message_text.lower()
            gender_extracted = None
            
            # More comprehensive gender extraction with common variations and affirmations
            if re.search(r'\b(female|woman|girl|f|she|her|lady|gal|girll*|fem)\b', message_lower) or (
                re.search(r'\b(yeah|yes|yep|yup|sure)\b.*\b(girl|female|woman|f)\b', message_lower)
            ):
                gender_extracted = "female"
                logger.info(f"Extracted gender {gender_extracted} from fallback message")
            elif re.search(r'\b(male|man|boy|m|he|him|guy|dude|bro|gentleman)\b', message_lower) or (
                re.search(r'\b(yeah|yes|yep|yup|sure)\b.*\b(guy|male|man|m)\b', message_lower)
            ):
                gender_extracted = "male"
                logger.info(f"Extracted gender {gender_extracted} from fallback message")
            elif re.search(r'\b(non-binary|nonbinary|nb|enby|they|them|neutral|other)\b', message_lower):
                gender_extracted = "non-binary"
                logger.info(f"Extracted gender {gender_extracted} from fallback message")
            
            # Also check for age in case the user provides both or is answering a previous question
            age_match = re.search(r'\b(\d+)\b', message_lower)
            if age_match and not age:  # Only update age if it's not already set
                extracted_age = int(age_match.group(1))
                if 18 <= extracted_age <= 100:
                    logger.info(f"Extracted age {extracted_age} from fallback message")
                    events.append(SlotSet("age", extracted_age))
            
            if gender_extracted:
                dispatcher.utter_message(text=f"Thanks for sharing that you identify as {gender_extracted}, {name}!")
                dispatcher.utter_message(text="What gender are you interested in dating?")
                events.extend([SlotSet("gender", gender_extracted), SlotSet("personal_data_stage", 3)])
                return events
            
            # Check if user wants to skip
            skip_phrases = ["don't want to", "dont want to", "skip", "pass", "next", "don't tell", "dont tell", "not telling"]
            if any(phrase in message_lower for phrase in skip_phrases):
                logger.info(f"User wants to skip providing gender")
                dispatcher.utter_message(text=f"No problem, {name}. Let's skip the gender question.")
                events.extend([SlotSet("gender", "skipped"), SlotSet("personal_data_stage", 3)])
                dispatcher.utter_message(text="What gender are you interested in dating?")
                return events
        
        elif personal_data_stage == 3:
            # Try to extract gender preference from the message
            message_lower = message_text.lower()
            gender_pref = None
            
            if any(term in message_lower for term in ["female", "woman", "girl", "she", "her", "f", "females", "women", "girls"]):
                gender_pref = "female"
                logger.info(f"Extracted gender preference {gender_pref} from fallback message")
            elif any(term in message_lower for term in ["male", "man", "boy", "he", "him", "m", "males", "men", "boys", "dude", "dudes", "guys"]):
                gender_pref = "male"
                logger.info(f"Extracted gender preference {gender_pref} from fallback message")
            elif any(term in message_lower for term in ["non-binary", "nonbinary", "nb", "enby", "they", "them"]):
                gender_pref = "non-binary"
                logger.info(f"Extracted gender preference {gender_pref} from fallback message")
            elif any(term in message_lower for term in ["any", "all", "both", "everyone", "anybody", "anyone", "either"]):
                gender_pref = "any"
                logger.info(f"Extracted gender preference {gender_pref} from fallback message")
            
            if gender_pref:
                dispatcher.utter_message(text=f"Thanks for sharing that you're interested in {gender_pref}s, {name}!")
                dispatcher.utter_message(text="What age range are you looking for in a partner?")
                events.extend([SlotSet("gender_preference", gender_pref), SlotSet("personal_data_stage", 4)])
                return events
            
            # Check if user wants to skip
            skip_phrases = ["don't want to", "dont want to", "skip", "pass", "next", "don't tell", "dont tell", "not telling"]
            if any(phrase in message_lower for phrase in skip_phrases):
                logger.info(f"User wants to skip providing gender preference")
                dispatcher.utter_message(text=f"No problem, {name}. Let's skip the gender preference question.")
                events.extend([SlotSet("gender_preference", "skipped"), SlotSet("personal_data_stage", 4)])
                dispatcher.utter_message(text="What age range are you looking for in a partner?")
                return events
        
        elif personal_data_stage == 4:
            # Try to extract age preference from the message
            age_preference = None
            message_lower = message_text.lower()
            
            # Check if user wants to skip
            skip_phrases = ["don't want to", "dont want to", "skip", "pass", "next", "don't tell", "dont tell", "not telling"]
            if any(phrase in message_lower for phrase in skip_phrases):
                logger.info(f"User wants to skip providing age preference")
                dispatcher.utter_message(text=f"No problem, {name}. Let's skip the age preference question.")
                events.extend([SlotSet("age_preference", "skipped"), SlotSet("personal_data_stage", 5)])
                dispatcher.utter_message(text="What is your height? (e.g., 5'10\", 178cm)")
                return events
            
            # Try to extract age preference
            age_range_match = re.search(r'(\d+)\s*(?:to|-|and)\s*(\d+)', message_lower)
            if age_range_match:
                min_age = int(age_range_match.group(1))
                max_age = int(age_range_match.group(2))
                age_preference = f"{min_age}-{max_age}"
            else:
                age_numbers = re.findall(r'\b(\d+)\b', message_lower)
                if len(age_numbers) >= 2:
                    min_age = int(age_numbers[0])
                    max_age = int(age_numbers[1])
                    age_preference = f"{min_age}-{max_age}"
                elif len(age_numbers) == 1:
                    # Single number could be age preference or height
                    # If it's between 18-100, more likely to be age preference
                    # If it's between 150-220, more likely to be height in cm
                    number = int(age_numbers[0])
                    if 18 <= number <= 100:
                        age_preference = f"{number}"
                    elif 150 <= number <= 220:
                        # This might be height in cm, let's check if we're getting height instead
                        height = f"{number}cm"
                        logger.info(f"Extracted height {height} from message (assumed cm based on value range)")
                        dispatcher.utter_message(text=f"Thanks for sharing that you're {height} tall, {name}!")
                        dispatcher.utter_message(text="Now, tell me about your interests. What do you enjoy doing in your free time?")
                        events.extend([SlotSet("height", height), SlotSet("personal_data_stage", 6)])
                        return events
                    else:
                        age_preference = f"{number}"
            
            if age_preference:
                logger.info(f"Extracted age preference {age_preference} from fallback message")
                dispatcher.utter_message(text=f"Thanks for sharing your age preference, {name}!")
                dispatcher.utter_message(text="What is your height? (e.g., 5'10\", 178cm)")
                events.extend([SlotSet("age_preference", age_preference), SlotSet("personal_data_stage", 5)])
                return events
        
        elif personal_data_stage == 5:
            height = None
            message_lower = message_text.lower()
            
            # Check if user wants to skip
            skip_phrases = ["don't want to", "dont want to", "skip", "pass", "next", "don't tell", "dont tell", "not telling"]
            if any(phrase in message_lower for phrase in skip_phrases):
                logger.info(f"User wants to skip providing height")
                dispatcher.utter_message(text=f"No problem, {name}. Let's skip the height question.")
                events.extend([SlotSet("height", "skipped"), SlotSet("personal_data_stage", 7)])
                dispatcher.utter_message(text="Now, tell me about your interests. What do you enjoy doing in your free time?")
                return events
            
            # First try standard pattern matching for common height formats
            feet_inches_match = re.search(r'(\d+)\s*(?:\'|feet|foot|ft)(?:\s*|-)(\d+)\s*(?:"|inches|inch|in)?', message_lower)
            if feet_inches_match:
                feet = int(feet_inches_match.group(1))
                inches = int(feet_inches_match.group(2))
                height = f"{feet}'{inches}\""
                logger.info(f"Extracted height {height} (feet/inches format)")
            elif re.search(r'(\d+)\s*(?:cm|centimeters|centimeter)', message_lower):
                cm_match = re.search(r'(\d+)\s*(?:cm|centimeters|centimeter)', message_lower)
                cm = int(cm_match.group(1))
                height = f"{cm}cm"
                logger.info(f"Extracted height {height} (cm format with unit)")
            elif re.search(r'\b(\d+)\b', message_lower):
                # Just a number - try to determine if it's inches or cm
                number_match = re.search(r'\b(\d+)\b', message_lower)
                number = int(number_match.group(1))
                
                # If number is between 150-220, assume it's cm
                if 150 <= number <= 220:
                    height = f"{number}cm"
                    logger.info(f"Extracted height {height} (assumed cm based on value range)")
                # If number is between 48-84, assume it's inches
                elif 48 <= number <= 84:
                    feet = number // 12
                    remaining_inches = number % 12
                    height = f"{feet}'{remaining_inches}\""
                    logger.info(f"Extracted height {height} (converted from inches)")
                # If number is between 4-7, assume it's feet
                elif 4 <= number <= 7:
                    height = f"{number}'0\""
                    logger.info(f"Extracted height {height} (assumed feet only)")
            
            # If standard pattern matching failed, use Ollama to interpret the height
            if not height and OLLAMA_AVAILABLE:
                try:
                    logger.info(f"Using Ollama to interpret height from: '{message_text}'")
                    client = ollama.Client(OLLAMA_API_HOST, OLLAMA_MODEL)
                    
                    height_prompt = [
                        {"role": "system", "content": "You are a helpful assistant that extracts height information from user messages. Extract the height and convert it to a standard format (either X'Y\" or Zcm). If the input is just a number without units, determine if it's likely cm (if 150-220) or feet (if 4-7) based on the value. Return ONLY the formatted height value without any explanation or additional text."},
                        {"role": "user", "content": f"Extract height from this message: '{message_text}'"}
                    ]
                    
                    response = client.generate_content(height_prompt[0]["content"], height_prompt[1]["content"])
                    
                    extracted_height = response.choices[0].message.content.strip()
                    
                    # Validate the extracted height
                    if re.search(r'^\d+\'\d+\"$', extracted_height) or re.search(r'^\d+cm$', extracted_height):
                        height = extracted_height
                        logger.info(f"Ollama extracted height: {height}")
                    else:
                        logger.info(f"Ollama couldn't extract a valid height format from: '{extracted_height}'")
                except Exception as e:
                    logger.error(f"Error using Ollama to interpret height: {str(e)}")
            
            if height:
                logger.info(f"Extracted height {height} from fallback message")
                dispatcher.utter_message(text=f"Thanks for sharing that you're {height} tall, {name}!")
                dispatcher.utter_message(text="Now, tell me about your interests. What do you enjoy doing in your free time?")
                events.extend([SlotSet("height", height), SlotSet("personal_data_stage", 7)])
                return events
            else:
                # If we still couldn't extract height, ask again more specifically
                dispatcher.utter_message(text=f"I'm having trouble understanding your height. Could you please format it as feet and inches (e.g., 5'10\") or centimeters (e.g., 178cm)?")
                return events
        
        # Special case: If the user says they don't want to provide information
        # but we're in a data collection stage, move to the next stage
        skip_phrases = ["don't want to", "dont want to", "skip", "pass", "next", "don't tell", "dont tell", "not telling"]
        if personal_data_stage in [2, 3, 4, 5, 6] and any(phrase in message_text.lower() for phrase in skip_phrases):
            logger.info(f"User wants to skip providing information at stage {personal_data_stage}")
            
            if personal_data_stage == 2:  # Age
                dispatcher.utter_message(text=f"No problem, {name}. Let's skip the age question.")
                events.extend([SlotSet("age", 0), SlotSet("personal_data_stage", 3)])
                dispatcher.utter_message(text="What is your gender?")
                return events
            elif personal_data_stage == 3:  # Gender
                dispatcher.utter_message(text=f"No problem, {name}. Let's skip the gender question.")
                events.extend([SlotSet("gender", "skipped"), SlotSet("personal_data_stage", 4)])
                dispatcher.utter_message(text="What gender are you interested in dating?")
                return events
            elif personal_data_stage == 4:  # Gender preference
                dispatcher.utter_message(text=f"No problem, {name}. Let's skip the gender preference question.")
                events.extend([SlotSet("gender_preference", "skipped"), SlotSet("personal_data_stage", 5)])
                dispatcher.utter_message(text="What age range are you looking for in a partner?")
                return events
            elif personal_data_stage == 5:  # Age preference
                dispatcher.utter_message(text=f"No problem, {name}. Let's skip the age preference question.")
                events.extend([SlotSet("age_preference", "skipped"), SlotSet("personal_data_stage", 6)])
                dispatcher.utter_message(text="What is your height? (e.g., 5'10\", 178cm)")
                return events
            elif personal_data_stage == 6:  # Height
                dispatcher.utter_message(text=f"No problem, {name}. Let's skip the height question.")
                events.extend([SlotSet("height", "skipped"), SlotSet("personal_data_stage", 7)])
                dispatcher.utter_message(text="Now, tell me about your interests. What do you enjoy doing in your free time?")
                return events
        
        # If we couldn't extract structured information, use Ollama to generate a response
        if OLLAMA_AVAILABLE:
            try:
                logger.info(f"Ollama is available, attempting to generate response with model: {OLLAMA_MODEL[:5]}...")
                client = ollama.Client(OLLAMA_API_HOST, OLLAMA_MODEL)
                
                # Create a context-aware system message based on the current stage
                system_message = "You are Hapa, a friendly dating profile assistant with a cat-like personality. You help users create their dating profiles by collecting information in a conversational way. You use cat puns and playful language. Keep responses brief and engaging."
                
                if personal_data_stage == 1:
                    system_message += " You're currently trying to collect the user's age. If they provide an age, acknowledge it and ask for their gender next."
                elif personal_data_stage == 2:
                    system_message += " You're currently trying to collect the user's gender. If they provide their gender, acknowledge it and ask for their gender preference next."
                elif personal_data_stage == 3:
                    system_message += " You're currently trying to collect the user's gender preference. If they provide their gender preference, acknowledge it and ask for their age preference next."
                elif personal_data_stage == 4:
                    system_message += " You're currently trying to collect the user's age preference. If they provide an age preference, acknowledge it and ask for their height next."
                elif personal_data_stage == 5:
                    system_message += " You're currently trying to collect the user's age preference. If they provide an age preference, acknowledge it and ask for their height next."
                elif personal_data_stage == 6:
                    system_message += " You're currently trying to collect the user's height. If they provide their height, acknowledge it and ask about their interests next."
                else:
                    system_message += " You're currently helping the user build their dating profile by collecting their personal information."
                
                messages = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": message_text}
                ]
                
                logger.info(f"Sending messages to Ollama: {messages}")
                
                response = client.generate_content(system_message, message_text)
                
                ai_response = response.choices[0].message.content
                logger.info(f"Generated Ollama fallback response: {ai_response}")
                
                # Try to extract information from the AI response as well
                if personal_data_stage == 1 and not age:
                    age_match = re.search(r'\b(\d+)\b', ai_response)
                    if age_match:
                        age = int(age_match.group(1))
                        if 18 <= age <= 100:
                            logger.info(f"Extracted age {age} from Ollama response")
                            events.append(SlotSet("age", age))
                            events.append(SlotSet("personal_data_stage", 2))
                
                elif personal_data_stage == 2 and not gender:
                    ai_response_lower = ai_response.lower()
                    if "female" in ai_response_lower or "woman" in ai_response_lower or "girl" in ai_response_lower:
                        gender = "female"
                    elif "male" in ai_response_lower or "man" in ai_response_lower or "boy" in ai_response_lower:
                        gender = "male"
                    elif "non-binary" in ai_response_lower or "nonbinary" in ai_response_lower:
                        gender = "non-binary"
                    
                    if gender:
                        logger.info(f"Extracted gender {gender} from Ollama response")
                        events.append(SlotSet("gender", gender))
                        events.append(SlotSet("personal_data_stage", 3))
                
                dispatcher.utter_message(text=ai_response)
                return events
                
            except Exception as e:
                logger.error(f"Error generating Ollama response: {str(e)}")
                dispatcher.utter_message(text=f"I'm having trouble understanding. Could you please provide more information?")
                return events
        else:
            logger.warning(f"Ollama not available (OLLAMA_AVAILABLE={OLLAMA_AVAILABLE}), using conversational fallback")
            dispatcher.utter_message(text=f"Meow! I'm not quite sure how to respond to that, {name}. Let's continue with your profile. What would you like to share next?")
            return events

# End of actions – additional actions can be added below.
