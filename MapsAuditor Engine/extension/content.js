// Native Content Script Bridge Listener
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "START_CRAWL") {
    sendResponse({ status: "acknowledged" });
    // Run the scraper asynchronously
    runGoogleMapsFootprintScraper();
  }
  return true;
});

async function runGoogleMapsFootprintScraper() {
  console.log("Starting native content scraper engine loop...");
  
  const scrollContainer = document.querySelector('div[role="feed"]');
  if (!scrollContainer) {
    alert("Could not locate the list view container. Be sure to click into the left search results panel or scroll slightly before hitting run.");
    return;
  }

  // Remove existing stop button if any
  if (document.getElementById('floating-stop-btn')) {
    document.getElementById('floating-stop-btn').remove();
  }

  // Create stop button
  const stopButton = document.createElement('button');
  stopButton.id = 'floating-stop-btn';
  stopButton.innerText = 'STOP SCRAPER';
  stopButton.style.position = 'fixed';
  stopButton.style.top = '20px';
  stopButton.style.left = '50%';
  stopButton.style.transform = 'translateX(-50%)';
  stopButton.style.zIndex = '99999';
  stopButton.style.backgroundColor = '#dc2626';
  stopButton.style.color = 'white';
  stopButton.style.padding = '14px 28px';
  stopButton.style.border = 'none';
  stopButton.style.borderRadius = '8px';
  stopButton.style.cursor = 'pointer';
  stopButton.style.fontWeight = 'bold';
  stopButton.style.fontSize = '14px';
  stopButton.style.boxShadow = '0 4px 14px rgba(0,0,0,0.3)';
  stopButton.style.transition = 'background 0.2s';
  
  document.body.appendChild(stopButton);
  window.scrapingActiveFlag = true;
  
  stopButton.addEventListener('click', () => {
    window.scrapingActiveFlag = false;
    stopButton.innerText = 'Stopping loops safely...';
    stopButton.style.backgroundColor = '#4b5563';
  });

  let processedNames = new Set();
  let maxStallAttempts = 30; 
  let currentStalls = 0;

  // Parse window title for niche and city
  const windowTitle = document.title || "Local Business near USA";
  let nicheGuess = "Local Business";
  let cityGuess = "USA";
  
  if (windowTitle.includes(" - ")) {
    const parts = windowTitle.split(" - ");
    if (parts.length >= 2) {
      nicheGuess = parts[0] || "Local Business";
      cityGuess = parts[1] || "USA";
    }
  } else if (windowTitle.includes(" near ")) {
    const parts = windowTitle.split(" near ");
    nicheGuess = parts[0] || "Local Business";
    cityGuess = parts[1] || "USA";
  } else if (windowTitle.includes(" in ")) {
    const parts = windowTitle.split(" in ");
    nicheGuess = parts[0] || "Local Business";
    cityGuess = parts[1] || "USA";
  }

  nicheGuess = String(nicheGuess).trim();
  cityGuess = String(cityGuess).trim();

  console.log(`Niche: "${nicheGuess}", City: "${cityGuess}"`);

  let scrapedCount = 0;

  while (currentStalls < maxStallAttempts) {
    if (window.scrapingActiveFlag === false) break;

    const cards = Array.from(document.querySelectorAll('a[href*="/maps/place/"], .Nv2y3c, [jsaction*="pane.wfvdC"]'));
    let foundNewThisPass = false;

    for (let card of cards) {
      if (window.scrapingActiveFlag === false) break;

      const titleSpan = card.querySelector('.qBF1Pd, .hfpxzc') || card.querySelector('div[class*="title"]');
      let bName = titleSpan ? titleSpan.innerText.trim() : card.getAttribute('aria-label');
      
      if (!bName && card.innerText) bName = card.innerText.split('\n')[0].trim();
      if (!bName || processedNames.has(bName) || bName.includes("·") || bName.length < 2) continue;

      foundNewThisPass = true;
      processedNames.add(bName);
      
      console.log(`Engaging card entry element: ${bName}`);
      card.scrollIntoView({ block: 'center', behavior: 'smooth' });
      await new Promise(resolve => setTimeout(resolve, 300));
      
      if (titleSpan) { titleSpan.click(); } else { card.click(); }
      await new Promise(resolve => setTimeout(resolve, 3500));

      const websiteElement = document.querySelector('a[data-item-id="authority"]');
      const phoneElement = document.querySelector('button[data-item-id^="phone:tel:"]');
      const ratingElement = document.querySelector('div.F7nice span[aria-hidden="true"]');
      const totalReviewsElement = document.querySelector('div.F7nice button.HH2Xfc') || document.querySelector('span[aria-label*="reviews"]');
      const lastReviewElement = document.querySelector('.rsqYfe, span.rsqYfe, div.MyEned + div');

      let cleanCount = 0;
      if (totalReviewsElement) {
        const numeric = totalReviewsElement.innerText.replace(/[^0-9]/g, '');
        if (numeric) cleanCount = parseInt(numeric, 10);
      }

      let cleanRating = null;
      if (ratingElement) {
        const ratingFloat = parseFloat(ratingElement.innerText.trim());
        if (!isNaN(ratingFloat)) cleanRating = ratingFloat;
      }

      const extractedPayload = {
        name: String(bName).trim(),
        website: websiteElement ? String(websiteElement.getAttribute('href') || '').trim() : "",
        phone: phoneElement ? String(phoneElement.getAttribute('data-item-id') || '').replace("phone:tel:", "").trim() : "",
        rating: cleanRating,
        review_count: cleanCount,
        last_review_date: lastReviewElement ? String(lastReviewElement.innerText || '').trim() : "Recent/Active Profile",
        niche: nicheGuess,
        city: cityGuess
      };

      console.log(`Sending payload for: ${extractedPayload.name}`);
      scrapedCount++;

      // Send message with proper callback handling
      chrome.runtime.sendMessage({
        action: "stream_payload_upstream",
        data: extractedPayload
      }, (response) => {
        if (chrome.runtime.lastError) {
          console.error(`Send error for ${extractedPayload.name}:`, chrome.runtime.lastError.message);
        } else if (response && response.status === "error") {
          console.error(`Server error for ${extractedPayload.name}:`, response.details);
          console.error("Hint:", response.hint || "Start server with: python bridge_server.py");
        } else {
          console.log(`Data sent successfully: ${extractedPayload.name}`);
        }
      });
    }

    // Scroll to load more
    const previousHeight = scrollContainer.scrollHeight;
    scrollContainer.scrollBy(0, 900);
    await new Promise(resolve => setTimeout(resolve, 2500));

    if (scrollContainer.scrollHeight === previousHeight && !foundNewThisPass) {
      currentStalls++;
    } else {
      currentStalls = 0;
    }

    if (document.body.innerText.includes("You've reached the end of the list")) break;
  }
  
  if (document.getElementById('floating-stop-btn')) {
    document.getElementById('floating-stop-btn').remove();
  }
  
  alert(`Crawl complete! Successfully processed ${scrapedCount} profiles.`);
}