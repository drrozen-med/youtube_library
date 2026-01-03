# YouTube Downloader → Scrapers-Hub Integration Handover

**Date:** 2026-01-02  
**Status:** Ready for Implementation  
**Priority:** High (IP block bypass solution)

---

## 🎯 Objective

Integrate YouTube Downloader with Scrapers-Hub's professional scraping infrastructure to bypass YouTube IP blocks and enable reliable transcript fetching.

---

## 📋 Current Situation

### YouTube Downloader Status
- **Location:** `apps/youtube_downloader/`
- **Problem:** IP blocked by YouTube (transcript scraping fails)
- **Current Method:** Uses `youtube-transcript-api` library (direct web scraping)
- **Success Rate:** 0% (all recent attempts blocked)
- **Existing Transcripts:** 25 successfully scraped before IP block

### What Works
- ✅ Channel resolution (YouTube Data API v3 with service account)
- ✅ Video metadata collection (YouTube Data API v3)
- ✅ Registry management
- ✅ Markdown generation

### What's Broken
- ❌ Transcript fetching (IP blocked)
- ❌ All scraping attempts fail with `IpBlocked` exception

---

## 🏗️ Scrapers-Hub Infrastructure Available

### Professional Scraping Services
Scrapers-Hub has **production-ready** integration with multiple professional scraping services:

1. **ScrapingBee** (`SCRAPINGBEE_API_KEY`)
   - Premium residential proxies
   - JavaScript rendering
   - Cloudflare bypass
   - Location: `apps/scrapers-hub/job-scrapers/shared/src/scrapers/scrapingbee_scraper.py`

2. **ScrapeNinja** (`SCRAPENINJA_API_KEY`)
   - US proxies
   - Anti-bot bypass
   - Location: `apps/scrapers-hub/job-scrapers/shared/src/scrapers/scrapeninja_scraper.py`

3. **Firecrawl** (`FIRECRAWL_API_KEY`)
   - Most reliable option
   - Location: `apps/scrapers-hub/job-scrapers/core/budget_scraper_integration.py`

4. **ScrapeOps** (`SCRAPEOPS_API_KEY`)
   - Additional fallback option

### Key Components

#### 1. Budget Proxy Manager
**Location:** `apps/scrapers-hub/job-scrapers/core/budget_proxy_manager.py`

**Features:**
- Automatic service selection
- Cost tracking
- Fallback chain management
- Usage monitoring

**Usage Pattern:**
```python
from budget_proxy_manager import BudgetProxyManager

manager = BudgetProxyManager()
content, metadata = await manager.scrape_with_fallback(url, options)
```

#### 2. Budget Scraper Integration
**Location:** `apps/scrapers-hub/job-scrapers/core/budget_scraper_integration.py`

**Features:**
- Unified interface for all scraping services
- Automatic fallback chain
- Quality gates
- Error handling

**Usage Pattern:**
```python
from budget_scraper_integration import BudgetScraperMixin

class YouTubeScraper(BudgetScraperMixin):
    async def fetch_transcript(self, video_id):
        url = f"https://www.youtube.com/watch?v={video_id}"
        html, metadata = await self.scrape_with_budget_service(url, {
            'render_js': True,
            'wait_for': 'transcript-container'  # or appropriate selector
        })
        # Parse transcript from HTML
```

#### 3. Professional Scraping Service
**Location:** `apps/scrapers-hub/scrapers/profile/healthcare/core/professional_scraper.py`

**Features:**
- ScrapeBee integration
- ScrapeNinja integration
- Automatic retry logic
- Cost tracking

---

## 🔧 Implementation Plan

### Phase 1: Integrate Scrapers-Hub Services

**File to Modify:** `apps/youtube_downloader/core/transcript_fetcher.py`

**Changes:**
1. Add Scrapers-Hub dependencies to `requirements.txt`
2. Import scraping services from Scrapers-Hub
3. Replace direct `youtube-transcript-api` calls with proxy-enabled scraping
4. Implement fallback chain: ScrapingBee → ScrapeNinja → Firecrawl → Direct

**Key Integration Points:**

```python
# Option 1: Use BudgetScraperMixin
from apps.scrapers_hub.job_scrapers.core.budget_scraper_integration import BudgetScraperMixin

class YouTubeTranscriptFetcher(BudgetScraperMixin):
    async def fetch_transcript_with_proxy(self, video_id):
        url = f"https://www.youtube.com/watch?v={video_id}"
        html, metadata = await self.scrape_with_budget_service(url, {
            'render_js': True,
            'country_code': 'us',
            'wait': 3000  # Wait for transcript to load
        })
        # Parse transcript from HTML using BeautifulSoup
        # Extract transcript data from page
```

```python
# Option 2: Use BudgetProxyManager directly
from apps.scrapers_hub.job_scrapers.core.budget_proxy_manager import BudgetProxyManager

manager = BudgetProxyManager()
html, metadata = await manager.scrape_with_fallback(url, {
    'render_js': True,
    'country_code': 'us'
})
```

### Phase 2: Environment Configuration

**File:** `apps/youtube_downloader/.env`

**Add:**
```bash
# Scrapers-Hub Integration
SCRAPINGBEE_API_KEY=your_scrapingbee_key
SCRAPENINJA_API_KEY=your_scrapeninja_key
FIRECRAWL_API_KEY=your_firecrawl_key
SCRAPEOPS_API_KEY=your_scrapeops_key
```

**Note:** Keys are already configured in `credentials/env_files/.env.scrapers`

### Phase 3: Transcript Parsing

**Challenge:** Need to parse transcript from HTML instead of using `youtube-transcript-api`

**Solution:**
1. Scrape YouTube video page HTML using proxy services
2. Extract transcript data from page (likely in JSON-LD or embedded script tags)
3. Parse transcript segments
4. Format same as current implementation

**Research Needed:**
- Where exactly is transcript data in YouTube HTML?
- Is it in `<script>` tags with JSON?
- Is it loaded via AJAX after page load?
- What selector to wait for?

### Phase 4: Testing

1. Test with single video using ScrapingBee
2. Test fallback chain (ScrapingBee → ScrapeNinja → Firecrawl)
3. Verify transcript parsing accuracy
4. Test cost tracking
5. Test rate limiting

---

## 📚 Reference Files

### Scrapers-Hub Core Files
- `apps/scrapers-hub/job-scrapers/core/budget_proxy_manager.py` - Main proxy manager
- `apps/scrapers-hub/job-scrapers/core/budget_scraper_integration.py` - Unified scraper interface
- `apps/scrapers-hub/job-scrapers/shared/src/scrapers/scrapingbee_scraper.py` - ScrapingBee implementation
- `apps/scrapers-hub/job-scrapers/shared/src/scrapers/scrapeninja_scraper.py` - ScrapeNinja implementation

### Documentation
- `apps/scrapers-hub/job-scrapers/shared/README.md` - Scrapers overview
- `apps/scrapers-hub/job-scrapers/shared/PROJECT_HISTORY_AND_TECHNICAL_DECISIONS.md` - Architecture decisions
- `apps/scrapers-hub/docs/OPERATIONAL_BLUEPRINT.md` - System architecture

### YouTube Downloader Files
- `apps/youtube_downloader/core/transcript_fetcher.py` - Current transcript fetching (needs modification)
- `apps/youtube_downloader/orchestrator.py` - Main CLI orchestrator
- `apps/youtube_downloader/core/auth_helper.py` - Service account auth (already working)

---

## 🔑 Key Environment Variables

**Already Configured:**
- `SCRAPINGBEE_API_KEY` - In `credentials/env_files/.env.scrapers`
- `SCRAPENINJA_API_KEY` - In `credentials/env_files/.env.scrapers`
- `FIRECRAWL_API_KEY` - In `credentials/env_files/.env.scrapers`
- `SCRAPEOPS_API_KEY` - In `credentials/env_files/.env.scrapers`

**YouTube Downloader Specific:**
- `GOOGLE_SERVICE_ACCOUNT_PATH` - Already configured
- `YT_API_KEY` - Already configured (for metadata)

---

## 🎯 Success Criteria

1. ✅ Transcript fetching works through proxy services
2. ✅ Fallback chain works (try ScrapingBee → ScrapeNinja → Firecrawl)
3. ✅ Cost tracking implemented
4. ✅ No IP blocks (all requests go through proxies)
5. ✅ Transcript quality matches current implementation
6. ✅ Rate limiting respected

---

## 🚨 Important Notes

1. **Cost Awareness:** Track API usage - ScrapingBee/ScrapeNinja are paid services
2. **Rate Limiting:** Still implement delays between requests (even with proxies)
3. **Transcript Parsing:** May need to reverse-engineer YouTube's HTML structure
4. **Testing:** Test with small batches first to verify cost/quality
5. **Fallback:** Keep direct scraping as last resort (if all proxies fail)

---

## 🔍 Research Needed

1. **Where is transcript data in YouTube HTML?**
   - Check page source for transcript JSON
   - Look for `<script>` tags with transcript data
   - Check network requests for transcript endpoints

2. **What selectors to wait for?**
   - Transcript container selector
   - Loading indicators
   - JavaScript execution completion

3. **Transcript format:**
   - Is it JSON?
   - Is it HTML?
   - What's the structure?

---

## 📝 Next Steps

1. **Research:** Analyze YouTube video page HTML to find transcript location
2. **Integrate:** Add Scrapers-Hub dependencies and imports
3. **Implement:** Replace `youtube-transcript-api` with proxy-enabled scraping
4. **Test:** Verify transcript extraction works
5. **Optimize:** Fine-tune selectors, wait times, fallback chain
6. **Deploy:** Test with real channel downloads

---

## 💡 Quick Start Command

Once integrated, test with:
```bash
cd apps/youtube_downloader
source .venv/bin/activate
python orchestrator.py "https://www.youtube.com/@indydevdan" --limit 2
```

---

**Status:** Ready for implementation  
**Estimated Effort:** 2-4 hours  
**Dependencies:** Scrapers-Hub infrastructure (already available)

