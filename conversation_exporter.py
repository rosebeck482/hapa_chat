#!/usr/bin/env python3
"""
Conversation Exporter Utility

This script exports Rasa conversation logs to various formats.
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Text

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_conversation(conversation_id: str, log_dir: str = "conversation_logs") -> List[Dict[str, Any]]:
    """
    Load a conversation from the logs.
    
    Args:
        conversation_id: The ID of the conversation
        log_dir: Directory containing conversation logs
        
    Returns:
        List of conversation messages
    """
    log_file = os.path.join(log_dir, f'conversation_{conversation_id}.json')
    
    if not os.path.exists(log_file):
        logger.error(f"Conversation log file not found: {log_file}")
        return []
    
    try:
        with open(log_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {log_file}")
        return []

def export_to_json(conversation_history: List[Dict[str, Any]], conversation_id: str, output_file: Optional[str] = None) -> None:
    """
    Export conversation to JSON format.
    
    Args:
        conversation_history: List of conversation messages
        conversation_id: The ID of the conversation
        output_file: Output file path (optional)
    """
    export_data = {
        'conversation_id': conversation_id,
        'timestamp': datetime.now().isoformat(),
        'messages': conversation_history
    }
    
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2)
        logger.info(f"Conversation exported to JSON: {output_file}")
    else:
        print(json.dumps(export_data, indent=2))

def export_to_text(conversation_history: List[Dict[str, Any]], conversation_id: str, output_file: Optional[str] = None) -> None:
    """
    Export conversation to plain text format.
    
    Args:
        conversation_history: List of conversation messages
        conversation_id: The ID of the conversation
        output_file: Output file path (optional)
    """
    text_lines = [f"Conversation ID: {conversation_id}", f"Exported: {datetime.now().isoformat()}", ""]
    
    for message in conversation_history:
        timestamp = message.get('timestamp', '')
        section = message.get('section', '')
        sender = message.get('sender', '')
        content = message.get('content', '')
        metadata = message.get('metadata', {})
        
        # Format the timestamp for better readability
        try:
            dt = datetime.fromisoformat(timestamp)
            formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            formatted_time = timestamp
        
        # Format the sender (capitalize and pad)
        formatted_sender = sender.upper().ljust(6)
        
        # Add metadata if available
        metadata_str = ""
        if sender == 'user' and 'intent' in metadata and metadata['intent']:
            metadata_str = f" [Intent: {metadata['intent']}]"
        elif sender in ['bot', 'system'] and 'action' in metadata and metadata['action']:
            metadata_str = f" [Action: {metadata['action']}]"
        
        # Format the section
        section_str = f"[{section}]" if section else ""
        
        text_lines.append(f"[{formatted_time}] {section_str} {formatted_sender}: {content}{metadata_str}")
    
    text_output = '\n'.join(text_lines)
    
    if output_file:
        with open(output_file, 'w') as f:
            f.write(text_output)
        logger.info(f"Conversation exported to text: {output_file}")
    else:
        print(text_output)

def export_to_csv(conversation_history: List[Dict[str, Any]], conversation_id: str, output_file: Optional[str] = None) -> None:
    """
    Export conversation to CSV format.
    
    Args:
        conversation_history: List of conversation messages
        conversation_id: The ID of the conversation
        output_file: Output file path (optional)
    """
    import csv
    
    # Prepare CSV rows
    headers = ['timestamp', 'section', 'sender', 'content', 'intent', 'action', 'confidence', 'slots_set']
    rows = []
    
    for message in conversation_history:
        # Extract metadata
        metadata = message.get('metadata', {})
        intent = metadata.get('intent', '') if message.get('sender') == 'user' else ''
        action = metadata.get('action', '') if message.get('sender') in ['bot', 'system'] else ''
        confidence = metadata.get('confidence', '') if message.get('sender') == 'user' else ''
        slots_set = json.dumps(metadata.get('slots_set', {})) if 'slots_set' in metadata else ''
        
        row = {
            'timestamp': message.get('timestamp', ''),
            'section': message.get('section', ''),
            'sender': message.get('sender', ''),
            'content': message.get('content', ''),
            'intent': intent,
            'action': action,
            'confidence': confidence,
            'slots_set': slots_set
        }
        rows.append(row)
    
    if output_file:
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Conversation exported to CSV: {output_file}")
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

def list_conversations(log_dir: str = "conversation_logs") -> List[str]:
    """
    List all available conversations.
    
    Args:
        log_dir: Directory containing conversation logs
        
    Returns:
        List of conversation IDs
    """
    if not os.path.exists(log_dir):
        logger.error(f"Log directory not found: {log_dir}")
        return []
    
    conversation_ids = []
    for filename in os.listdir(log_dir):
        if filename.startswith('conversation_') and filename.endswith('.json'):
            conversation_id = filename[len('conversation_'):-len('.json')]
            conversation_ids.append(conversation_id)
    
    return conversation_ids

def main():
    """Main function to run the exporter."""
    parser = argparse.ArgumentParser(description='Export Rasa conversation logs to various formats')
    
    parser.add_argument('--list', action='store_true', help='List all available conversations')
    parser.add_argument('--id', type=str, help='Conversation ID to export')
    parser.add_argument('--format', type=str, choices=['json', 'text', 'csv'], default='json', help='Export format')
    parser.add_argument('--output', type=str, help='Output file path')
    parser.add_argument('--log-dir', type=str, default='conversation_logs', help='Directory containing conversation logs')
    
    args = parser.parse_args()
    
    # List conversations if requested
    if args.list:
        conversation_ids = list_conversations(args.log_dir)
        if conversation_ids:
            print("Available conversations:")
            for conversation_id in conversation_ids:
                print(f"  - {conversation_id}")
        else:
            print("No conversations found.")
        return
    
    # Check if conversation ID is provided
    if not args.id:
        parser.error("Please provide a conversation ID with --id or use --list to see available conversations")
    
    # Load conversation
    conversation_history = load_conversation(args.id, args.log_dir)
    
    if not conversation_history:
        logger.error(f"No conversation found for ID: {args.id}")
        return
    
    # Export conversation
    if args.format == 'json':
        export_to_json(conversation_history, args.id, args.output)
    elif args.format == 'text':
        export_to_text(conversation_history, args.id, args.output)
    elif args.format == 'csv':
        export_to_csv(conversation_history, args.id, args.output)

if __name__ == '__main__':
    main() 