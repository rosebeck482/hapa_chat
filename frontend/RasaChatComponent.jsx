import React, { useState, useEffect, useRef } from 'react';
import { createClient } from '@supabase/supabase-js';

// Initialize Supabase client
const supabaseUrl = process.env.REACT_APP_SUPABASE_URL || 'https://sxbmfehjgekagncfgepw.supabase.co';
const supabaseKey = process.env.REACT_APP_SUPABASE_ANON_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

/**
 * RasaChat Component - A chat interface that communicates with Rasa through Supabase Edge Functions
 * @param {string} userId - The user's ID
 * @param {string} chatId - The chat ID
 */
const RasaChat = ({ userId, chatId }) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);
  
  // Scroll to bottom of messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  
  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  
  // Load chat history on component mount
  useEffect(() => {
    const initializeChat = async () => {
      if (!chatId || !userId) return;
      
      try {
        // Fetch existing messages
        const { data, error } = await supabase
          .from('Messages')
          .select('*')
          .eq('chat_id', chatId)
          .order('sent_at', { ascending: true });
        
        if (error) throw error;
        
        if (data && data.length > 0) {
          // Format messages for display
          const formattedMessages = data.map(msg => ({
            id: msg.id,
            text: msg.message_text,
            sender: msg.sender_uid === userId ? 'user' : 'bot',
            timestamp: new Date(msg.sent_at)
          }));
          
          setMessages(formattedMessages);
        } else {
          // If no messages, this is a new chat
          console.log('No existing messages found. Starting new chat.');
        }
      } catch (error) {
        console.error('Error loading chat history:', error);
      }
      
      // Set up real-time subscription for new messages
      const subscription = supabase
        .channel('messages')
        .on('postgres_changes', { 
          event: 'INSERT', 
          schema: 'public', 
          table: 'Messages',
          filter: `chat_id=eq.${chatId}`
        }, (payload) => {
          const newMessage = payload.new;
          
          // Only add the message if it's not from the current user (to avoid duplicates)
          if (newMessage.sender_uid !== userId || !messages.some(m => m.id === newMessage.id)) {
            setMessages(prev => [...prev, {
              id: newMessage.id,
              text: newMessage.message_text,
              sender: newMessage.sender_uid === userId ? 'user' : 'bot',
              timestamp: new Date(newMessage.sent_at)
            }]);
          }
        })
        .subscribe();
      
      // Clean up subscription on unmount
      return () => {
        supabase.removeChannel(subscription);
      };
    };
    
    initializeChat();
  }, [chatId, userId]);
  
  // Save message to Supabase via Edge Function
  const saveMessageToSupabase = async (text, senderUid) => {
    try {
      // Call the messageHandler Edge Function
      const { data, error } = await supabase.functions.invoke('messageHandler', {
        body: {
          record: {
            chat_id: chatId,
            sender_uid: senderUid,
            message_text: text,
            type: 'text',
            sent_at: new Date().toISOString()
          }
        }
      });
      
      if (error) throw error;
      
      return data;
    } catch (error) {
      console.error('Error saving message:', error);
      throw error;
    }
  };
  
  // Handle sending a message
  const handleSendMessage = async (e) => {
    e.preventDefault();
    
    if (!input.trim() || loading) return;
    
    const userMessage = input.trim();
    setInput('');
    setLoading(true);
    
    // Add user message to UI immediately (optimistic update)
    const tempId = Date.now().toString();
    setMessages(prev => [...prev, {
      id: tempId,
      text: userMessage,
      sender: 'user',
      timestamp: new Date()
    }]);
    
    try {
      // Send message to Edge Function, which will forward to Rasa
      await saveMessageToSupabase(userMessage, userId);
      
      // Note: We don't need to manually add the bot response here
      // It will come through the real-time subscription
    } catch (error) {
      console.error('Error sending message:', error);
      
      // Add error message
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        text: 'Sorry, there was an error sending your message. Please try again.',
        sender: 'system',
        timestamp: new Date()
      }]);
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div className="chat-container">
      <div className="messages-container">
        {messages.map(message => (
          <div 
            key={message.id} 
            className={`message ${message.sender === 'user' ? 'user-message' : 'bot-message'}`}
          >
            <div className="message-bubble">
              {message.text}
            </div>
            <div className="message-timestamp">
              {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      
      <form onSubmit={handleSendMessage} className="message-input-form">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          {loading ? 'Sending...' : 'Send'}
        </button>
      </form>
    </div>
  );
};

export default RasaChat; 