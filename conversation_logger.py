import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Text

logger = logging.getLogger(__name__)

class ConversationLogger:
    """
    A class to log conversations between the bot and users.
    This can be used as a middleware or called directly from actions.
    """
    
    def __init__(self, log_dir: str = "conversation_logs"):
        """
        Initialize the conversation logger.
        
        Args:
            log_dir: Directory to store conversation logs
        """
        self.log_dir = log_dir
        
        # Create log directory if it doesn't exist
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def log_user_message(self, 
                         sender_id: str, 
                         message: str, 
                         intent: Optional[Dict[str, Any]] = None,
                         section: Optional[str] = None) -> None:
        """
        Log a user message.
        
        Args:
            sender_id: The ID of the user
            message: The message text
            intent: Intent information (optional)
            section: Current conversation section (optional)
        """
        conversation_data = self._load_conversation_data(sender_id)
        
        # Create user message entry with enhanced structure
        user_message = {
            'timestamp': datetime.now().isoformat(),
            'section': section or self._determine_section_from_history(conversation_data.get('messages', [])),
            'sender': 'user',
            'content': message,
            'metadata': {
                'intent': intent.get('name', '') if intent else '',
                'confidence': intent.get('confidence', 0.0) if intent else 0.0,
                'entities': intent.get('entities', []) if intent else []
            }
        }
        
        # Add to history and save
        conversation_data['messages'].append(user_message)
        self._save_conversation_data(sender_id, conversation_data)
    
    def log_bot_message(self, 
                        sender_id: str, 
                        message: str, 
                        metadata: Optional[Dict[str, Any]] = None,
                        action: Optional[str] = None,
                        section: Optional[str] = None) -> None:
        """
        Log a bot message.
        
        Args:
            sender_id: The ID of the user
            message: The message text
            metadata: Additional metadata (optional)
            action: The action that generated this message (optional)
            section: Current conversation section (optional)
        """
        conversation_data = self._load_conversation_data(sender_id)
        
        # Create bot message entry with enhanced structure
        bot_message = {
            'timestamp': datetime.now().isoformat(),
            'section': section or self._determine_section_from_history(conversation_data.get('messages', [])),
            'sender': 'bot',
            'content': message,
            'metadata': {
                'action': action or metadata.get('action', '') if metadata else '',
                'data': metadata.get('data', {}) if metadata else {}
            }
        }
        
        # Add to history and save
        conversation_data['messages'].append(bot_message)
        self._save_conversation_data(sender_id, conversation_data)
    
    def log_action(self,
                  sender_id: str,
                  action_name: str,
                  section: Optional[str] = None,
                  slots: Optional[Dict[str, Any]] = None) -> None:
        """
        Log an action execution.
        
        Args:
            sender_id: The ID of the user
            action_name: The name of the action
            section: Current conversation section (optional)
            slots: Slot values that were set (optional)
        """
        conversation_data = self._load_conversation_data(sender_id)
        
        # Create action entry
        action_entry = {
            'timestamp': datetime.now().isoformat(),
            'section': section or self._determine_section_from_history(conversation_data.get('messages', [])),
            'sender': 'system',
            'content': f"Action executed: {action_name}",
            'metadata': {
                'action': action_name,
                'slots_set': slots or {}
            }
        }
        
        # Add to history and save
        conversation_data['messages'].append(action_entry)
        
        # If slots were updated, also update the conversation metadata
        if slots:
            self.update_metadata(sender_id, slots)
        else:
            # Just save the conversation data with the new message
            self._save_conversation_data(sender_id, conversation_data)
    
    def _determine_section_from_history(self, conversation_messages: List[Dict[str, Any]]) -> str:
        """
        Determine the current section based on conversation history.
        
        Args:
            conversation_messages: List of conversation messages
            
        Returns:
            Current section name
        """
        # Try to get the section from the last message
        if conversation_messages:
            last_message = conversation_messages[-1]
            if 'section' in last_message and last_message['section']:
                return last_message['section']
        
        # Default sections based on typical conversation flow
        if len(conversation_messages) < 5:
            return "greeting"
        elif len(conversation_messages) < 15:
            return "personal_data_collection"
        elif len(conversation_messages) < 25:
            return "user_info_collection"
        else:
            return "user_preferences_collection"
    
    def update_section(self, sender_id: str, section: str) -> None:
        """
        Update the current section for a conversation.
        
        Args:
            sender_id: The ID of the user
            section: New section name
        """
        conversation_data = self._load_conversation_data(sender_id)
        
        # Create section change entry
        section_entry = {
            'timestamp': datetime.now().isoformat(),
            'section': section,
            'sender': 'system',
            'content': f"Section changed to: {section}",
            'metadata': {
                'previous_section': self._determine_section_from_history(conversation_data.get('messages', [])),
                'new_section': section
            }
        }
        
        # Add to history and save
        conversation_data['messages'].append(section_entry)
        self._save_conversation_data(sender_id, conversation_data)
    
    def update_metadata(self, sender_id: str, metadata_updates: Dict[str, Any]) -> None:
        """
        Update metadata for a conversation.
        
        Args:
            sender_id: The ID of the user
            metadata_updates: Dictionary of metadata values to update
        """
        conversation_data = self._load_conversation_data(sender_id)
        
        # Update the metadata section of the conversation data
        conversation_data['metadata'].update(metadata_updates)
        
        # Add a metadata update entry to messages
        metadata_entry = {
            'timestamp': datetime.now().isoformat(),
            'section': conversation_data.get('current_section', 'system'),
            'sender': 'system',
            'content': f"Metadata updated: {', '.join(metadata_updates.keys())}",
            'metadata': {
                'metadata_updated': metadata_updates
            }
        }
        
        # Add to history and save
        conversation_data['messages'].append(metadata_entry)
        self._save_conversation_data(sender_id, conversation_data)
    
    def get_conversation_history(self, sender_id: str) -> List[Dict[str, Any]]:
        """
        Get the conversation history for a user.
        
        Args:
            sender_id: The ID of the user
            
        Returns:
            List of conversation messages
        """
        conversation_data = self._load_conversation_data(sender_id)
        return conversation_data.get('messages', [])
    
    def get_metadata(self, sender_id: str) -> Dict[str, Any]:
        """
        Get the metadata for a user's conversation.
        
        Args:
            sender_id: The ID of the user
            
        Returns:
            Dictionary of metadata values
        """
        conversation_data = self._load_conversation_data(sender_id)
        return conversation_data.get('metadata', {})
    
    def _get_log_file_path(self, sender_id: str) -> str:
        """
        Get the path to the log file for a user.
        
        Args:
            sender_id: The ID of the user
            
        Returns:
            Path to the log file
        """
        return os.path.join(self.log_dir, f'conversation_{sender_id}.json')
    
    def _load_conversation_data(self, sender_id: str) -> Dict[str, Any]:
        """
        Load the conversation data for a user.
        
        Args:
            sender_id: The ID of the user
            
        Returns:
            Dictionary containing conversation data
        """
        log_file = self._get_log_file_path(sender_id)
        
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r') as f:
                    conversation_data = json.load(f)
                    # Ensure the expected structure exists
                    if 'messages' not in conversation_data:
                        conversation_data['messages'] = []
                    if 'metadata' not in conversation_data:
                        conversation_data['metadata'] = {}
                    return conversation_data
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON from {log_file}. Starting with empty data.")
        
        # Return a new conversation data structure
        return {
            'conversation_id': sender_id,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'metadata': {},
            'messages': []
        }
    
    def _save_conversation_data(self, sender_id: str, conversation_data: Dict[str, Any]) -> None:
        """
        Save the conversation data for a user.
        
        Args:
            sender_id: The ID of the user
            conversation_data: Dictionary containing conversation data
        """
        log_file = self._get_log_file_path(sender_id)
        
        # Update the last modified timestamp
        conversation_data['updated_at'] = datetime.now().isoformat()
        
        try:
            with open(log_file, 'w') as f:
                json.dump(conversation_data, f, indent=2)
            logger.info(f"Conversation data logged to {log_file}")
        except Exception as e:
            logger.error(f"Error writing conversation data to {log_file}: {str(e)}")
    
    def export_conversation(self, sender_id: str, format: str = 'json') -> Dict[str, Any]:
        """
        Export the conversation in various formats.
        
        Args:
            sender_id: The ID of the user
            format: Export format ('json' or 'text')
            
        Returns:
            Exported conversation
        """
        conversation_data = self._load_conversation_data(sender_id)
        
        if format == 'json':
            return conversation_data
        elif format == 'text':
            text_conversation = []
            text_conversation.append(f"CONVERSATION ID: {sender_id}")
            text_conversation.append(f"CREATED: {conversation_data.get('created_at', '')}")
            text_conversation.append(f"UPDATED: {conversation_data.get('updated_at', '')}")
            text_conversation.append("\nMETADATA:")
            
            # Add metadata section
            metadata = conversation_data.get('metadata', {})
            for key, value in metadata.items():
                text_conversation.append(f"  {key}: {value}")
            
            text_conversation.append("\nMESSAGES:")
            for message in conversation_data.get('messages', []):
                timestamp = message.get('timestamp', '')
                section = message.get('section', '')
                sender = message.get('sender', '')
                content = message.get('content', '')
                
                # Format the timestamp for better readability
                try:
                    dt = datetime.fromisoformat(timestamp)
                    formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    formatted_time = timestamp
                
                # Add metadata if available
                metadata_str = ""
                if 'metadata' in message:
                    metadata = message['metadata']
                    if sender == 'user' and 'intent' in metadata and metadata['intent']:
                        metadata_str = f" [Intent: {metadata['intent']}]"
                    elif sender == 'bot' and 'action' in metadata and metadata['action']:
                        metadata_str = f" [Action: {metadata['action']}]"
                
                text_conversation.append(f"[{formatted_time}] [{section}] {sender.upper()}: {content}{metadata_str}")
            
            return {
                'conversation_id': sender_id,
                'text': '\n'.join(text_conversation)
            }
        else:
            raise ValueError(f"Unsupported format: {format}") 