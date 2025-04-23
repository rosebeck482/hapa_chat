/**
 * Rasa Client - A simple client for communicating with a Rasa server
 */

class RasaClient {
  /**
   * Create a new Rasa client
   * @param {string} serverUrl - The URL of the Rasa server (default: http://localhost:5005)
   */
  constructor(serverUrl = 'http://localhost:5005') {
    this.serverUrl = serverUrl;
    this.sessionId = null;
    this.metadata = {};
  }

  /**
   * Set the session ID for this client
   * @param {string} sessionId - The session ID to use
   */
  setSessionId(sessionId) {
    this.sessionId = sessionId;
  }

  /**
   * Set metadata to be sent with each message
   * @param {Object} metadata - The metadata to send
   */
  setMetadata(metadata) {
    this.metadata = metadata || {};
  }

  /**
   * Send a message to the Rasa server
   * @param {string} message - The message to send
   * @returns {Promise<Object>} - The response from the Rasa server
   */
  async sendMessage(message) {
    if (!this.sessionId) {
      throw new Error('Session ID not set. Call setSessionId() first.');
    }

    try {
      const response = await fetch(`${this.serverUrl}/webhooks/rest/webhook`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          sender: this.sessionId,
          message: message,
          metadata: this.metadata
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return this.processResponse(data);
    } catch (error) {
      console.error('Error sending message to Rasa:', error);
      throw error;
    }
  }

  /**
   * Process the response from the Rasa server
   * @param {Array} responseData - The response data from the Rasa server
   * @returns {Object} - The processed response
   */
  processResponse(responseData) {
    if (!Array.isArray(responseData)) {
      return { messages: [], metadata: null };
    }

    // Extract text messages
    const messages = responseData
      .filter(item => item.text)
      .map(item => item.text);

    // Extract custom payloads
    const customPayloads = responseData
      .filter(item => item.custom)
      .map(item => item.custom);

    return {
      messages: messages,
      metadata: customPayloads.length > 0 ? customPayloads[0] : null
    };
  }

  /**
   * Initialize a new conversation
   * @param {string} sessionId - The session ID to use
   * @param {Object} initialMetadata - Initial metadata for the conversation
   * @returns {Promise<Object>} - The response from the Rasa server
   */
  async startConversation(sessionId, initialMetadata = {}) {
    this.setSessionId(sessionId);
    this.setMetadata(initialMetadata);

    // Send an initial message to start the conversation
    return this.sendMessage('/start');
  }
}

// Export the client for use in browser or Node.js
if (typeof module !== 'undefined' && module.exports) {
  module.exports = RasaClient;
} else {
  window.RasaClient = RasaClient;
} 