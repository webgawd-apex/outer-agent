// background.js - Fixed version with proper async handling

// Keep track of active connections
let activeConnections = new Map();

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "stream_payload_upstream") {
    console.log("Service worker forwarding data to Python server for:", message.data.name);

    // Use a single reliable URL
    const url = 'http://127.0.0.1:5000/api/lead';
    
    // Generate a unique ID for this request
    const requestId = Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    activeConnections.set(requestId, sendResponse);
    
    console.log(`[${requestId}] Connecting to: ${url}`);
    
    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify(message.data)
    })
    .then(async response => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const data = await response.json();
      return data;
    })
    .then(resData => {
      console.log(`[${requestId}] Server response:`, resData);
      // Send success response
      const callback = activeConnections.get(requestId);
      if (callback) {
        callback({ status: "success", backend: resData });
        activeConnections.delete(requestId);
      }
    })
    .catch(err => {
      console.error(`[${requestId}] Connection error:`, err.message);
      // Send error response
      const callback = activeConnections.get(requestId);
      if (callback) {
        callback({ 
          status: "error", 
          details: err.message,
          hint: "Make sure bridge_server.py is running on port 5000"
        });
        activeConnections.delete(requestId);
      }
    });

    // Return true to keep the message channel open for async response
    return true;
  }
});

// Clean up old connections periodically
setInterval(() => {
  const now = Date.now();
  for (const [id, callback] of activeConnections) {
    const timestamp = parseInt(id.split('-')[0]);
    if (now - timestamp > 30000) { // 30 seconds timeout
      console.log(`Cleaning up stale connection: ${id}`);
      callback({ status: "error", details: "Request timeout" });
      activeConnections.delete(id);
    }
  }
}, 10000);

console.log("Background service worker loaded successfully");