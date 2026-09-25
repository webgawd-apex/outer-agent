document.getElementById('scrapeBtn').addEventListener('click', async () => {
  const statusDiv = document.getElementById('status');
  statusDiv.innerText = "Triggering native loop on tab window...";

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) {
    statusDiv.innerText = "Error: Active window context lost. Reload the page.";
    return;
  }

  // Sends an internal execution signal directly down to our active content script listener
  chrome.tabs.sendMessage(tab.id, { action: "START_CRAWL" }, (response) => {
    if (chrome.runtime.lastError) {
      statusDiv.innerText = "Error: Please refresh your Google Maps page first, then click Run!";
      console.error("Extension error:", chrome.runtime.lastError);
    } else {
      statusDiv.innerText = "Crawl active! You can close this popup menu window safely.";
    }
  });
});

// Optional: Add a stop button in popup if needed
document.getElementById('stopBtn').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) {
    chrome.tabs.sendMessage(tab.id, { action: "STOP_CRAWL" });
    document.getElementById('status').innerText = "Stop signal sent to crawler.";
  }
});