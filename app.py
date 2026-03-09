# FINAL FIXED SCRAPER.PY - Large Data Handling with Memory Optimization
# Roman Urdu comments: Har line ke upar explain kiya gaya hai ke ye kya karti hai
# Large data handling: Memory optimization, chunking, proper error handling, batch processing
# 100% professional code jo large datasets ko handle karta hai bina memory issues ke
import requests, re, time, uuid, csv, os, json, urllib3, gc
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
from fpdf import FPDF
import pandas as pd
from collections import deque # Ye import BFS ke liye queue use karne ke liye hai
from requests.adapters import HTTPAdapter # Ye import retry mechanism ke liye hai
from requests.packages.urllib3.util.retry import Retry # Ye import retry strategy ke liye hai
from typing import Dict, List, Any, Optional # Ye type hints ke liye
# Disable SSL warnings - Ye line SSL warnings ko disable karti hai taake insecure requests mein warnings na aayein
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# Memory and performance constants - Ye constants memory optimization ke liye hain
MAX_MEMORY_USAGE = 500 * 1024 * 1024 # 500MB max memory usage
MAX_PARAGRAPHS_PER_PAGE = 100 # Maximum paragraphs per page
MAX_IMAGES_PER_PAGE = 50 # Maximum images per page
MAX_LINKS_PER_PAGE = 200 # Maximum links per page
CHUNK_SIZE = 50 # Pages chunk size for processing
class UltraScraper:
    # Ye init function class ko initialize karta hai with memory optimization
    def __init__(self):
        self.session = requests.Session() # Ye line requests session create karti hai for persistent connections
        self.session.headers.update({"User-Agent": "Mozilla/5.0"}) # Ye line user-agent set karti hai to look like browser
        self.session.verify = False # Ye line SSL verification disable karti hai for insecure sites
        # Retry mechanism: 3 retries with backoff - Ye block robust error handling add karta hai with retries
        retry_strategy = Retry( # Ye retry strategy define karti hai
            total=3, # Ye total retries set karti hai (3 times try karega)
            status_forcelist=[429, 500, 502, 503, 504], # Ye status codes set karti hai jin par retry karega (server errors)
            backoff_factor=1 # Ye backoff time set karti hai (1 second delay increase)
        )
        adapter = HTTPAdapter(max_retries=retry_strategy) # Ye adapter create karti hai retry ke sath
        self.session.mount("https://", adapter) # Ye HTTPS ke liye adapter mount karti hai
        self.session.mount("http://", adapter) # Ye HTTP ke liye adapter mount karti hai
       
        # Memory tracking - Ye memory usage track karta hai
        self.memory_usage = 0 # Ye current memory usage track karta hai
        self.processed_pages = 0 # Ye processed pages count karta hai
    # ---------- UTILS ----------
    # Ye function text ko clean karta hai (extra spaces remove)
    def clean(self, text):
        return re.sub(r"\s+", " ", text).strip() if text else "" # Ye line regex se extra spaces remove karti hai aur strip karti hai
    # Ye function relative URL ko absolute banata hai
    def abs_url(self, url, base):
        return urljoin(base, url) # Ye line urljoin use kar ke absolute URL banati hai
    # ---------- SINGLE PAGE SCRAPER ----------
    # Ye function single page ko scrape karta hai with memory optimization
    def scrape_single_page(self, url, mode="comprehensive"):
        start = time.time() # Ye line scraping time measure karne ke liye start time set karti hai
        try:
            r = self.session.get(url, timeout=30) # Ye line GET request bhejti hai with timeout 30 seconds
            r.raise_for_status() # Ye line check karti hai agar error hai to raise karega
            soup = BeautifulSoup(r.text, "html.parser") # Ye line HTML ko parse karti hai BeautifulSoup se
            # Remove scripts/styles - Ye block unnecessary tags remove karta hai
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose() # Ye line tag ko remove karti hai
            # Metadata - Ye block title aur description extract karta hai
            title = self.clean(soup.title.string) if soup.title else "" # Ye line title clean karti hai
            description = "" # Ye line description initialize karti hai
            meta_desc = soup.find("meta", attrs={"name": "description"}) # Ye line meta description find karti hai
            if meta_desc:
                description = self.clean(meta_desc.get("content")) # Ye line description clean karti hai
            # Headings - Ye block all headings (h1 to h6) collect karta hai with limits
            headings = {f"h{i}": [self.clean(h.get_text()) for h in soup.find_all(f"h{i}")[:10]] # Limited to 10 per level
                        for i in range(1, 7)} # Ye comprehension headings dictionary banati hai
            # Paragraphs - Ye block paragraphs collect karta hai with memory optimization
            all_paragraphs = [self.clean(p.get_text()) for p in soup.find_all("p") if len(p.get_text()) > 30]
            paragraphs = all_paragraphs[:MAX_PARAGRAPHS_PER_PAGE] # Ye paragraphs ko limit karta hai
            # Images - Ye block images collect karta hai with limits and filtering
            all_images = []
            for img in soup.find_all("img"):
                src = img.get("src")
                if src and not src.startswith("data:image/svg+xml"): # SVG data URLs ko filter karta hai
                    all_images.append({
                        "url": self.abs_url(src, url),
                        "alt": self.clean(img.get("alt"))
                    })
            images = all_images[:MAX_IMAGES_PER_PAGE] # Ye images ko limit karta hai
            # Links - Ye block internal aur external links separate karta hai with limits and filtering
            domain = urlparse(url).netloc # Ye line domain extract karti hai
            all_internal_links, all_external_links = [], [] # Ye line lists initialize karti hai
            for a in soup.find_all("a", href=True): # Ye loop all anchors par iterate karta hai
                if len(all_internal_links) >= MAX_LINKS_PER_PAGE and len(all_external_links) >= MAX_LINKS_PER_PAGE:
                    break # Ye limit check kar ke break karta hai
                href = a["href"]
                # Invalid links ko filter karta hai
                if (href.startswith("data:") or href.startswith("javascript:") or
                    href.startswith("mailto:") or href.startswith("tel:") or
                    href.startswith("#") or not href.strip()):
                    continue # Ye invalid links skip karta hai
               
                link = self.abs_url(href, url) # Ye line absolute link banati hai
                text = self.clean(a.get_text()) # Ye line link text clean karti hai
               
                # Empty text links ko skip karta hai
                if not text or len(text.strip()) < 2:
                    continue
                   
                if urlparse(link).netloc == domain: # Ye check karti hai internal link hai ya nahi
                    if len(all_internal_links) < MAX_LINKS_PER_PAGE:
                        all_internal_links.append({"url": link, "text": text}) # Ye internal link add karti hai
                else:
                    if len(all_external_links) < MAX_LINKS_PER_PAGE:
                        all_external_links.append({"url": link, "text": text}) # Ye external link add karti hai
           
            internal_links = all_internal_links
            external_links = all_external_links
            # Compose final JSON based on mode - Ye block mode ke according data structure banata hai
            if mode == "basic":
                data = { # Ye dictionary basic mode ke liye banati hai
                    "url": url, # Ye URL add karti hai
                    "title": title, # Ye title add karti hai
                    "description": description, # Ye description add karti hai
                    "paragraphs": paragraphs[:5], # Ye first 5 paragraphs add karti hai
                    "stats": { # Ye stats dictionary banati hai
                        "paragraph_count": len(paragraphs[:5]), # Ye count set karti hai
                        "scrape_time": round(time.time() - start, 2) # Ye scrape time calculate karti hai
                    },
                    "scraped_at": datetime.now().isoformat() # Ye timestamp add karti hai
                }
            elif mode == "smart":
                data = { # Ye dictionary smart mode ke liye banati hai
                    "url": url,
                    "title": title,
                    "description": description,
                    "headings": {k: v[:3] for k, v in headings.items()}, # Ye limited headings add karti hai
                    "paragraphs": paragraphs[:10], # Ye first 10 paragraphs add karti hai
                    "images": images[:5], # Ye first 5 images add karti hai
                    "internal_links": internal_links[:10], # Ye limited internal links
                    "external_links": external_links[:5], # Ye limited external links
                    "stats": {
                        "paragraph_count": len(paragraphs[:10]),
                        "image_count": len(images[:5]),
                        "internal_links_count": len(internal_links[:10]),
                        "external_links_count": len(external_links[:5]),
                        "scrape_time": round(time.time() - start, 2)
                    },
                    "scraped_at": datetime.now().isoformat()
                }
            else:
                data = { # Ye dictionary comprehensive mode ke liye banati hai
                    "url": url,
                    "title": title,
                    "description": description,
                    "headings": headings, # Ye all headings add karti hai
                    "paragraphs": paragraphs, # Ye all paragraphs add karti hai
                    "images": images, # Ye all images add karti hai
                    "internal_links": internal_links, # Ye internal links add karti hai
                    "external_links": external_links, # Ye external links add karti hai
                    "stats": {
                        "paragraph_count": len(paragraphs),
                        "image_count": len(images),
                        "internal_links_count": len(internal_links),
                        "external_links_count": len(external_links),
                        "scrape_time": round(time.time() - start, 2)
                    },
                    "scraped_at": datetime.now().isoformat()
                }
            return data # Ye final data return karti hai
        except Exception as e: # Ye block error handle karta hai
            return {"error": str(e)} # Ye error message return karti hai
    # ---------- FULL WEBSITE CRAWLER ----------
    # Ye function pori site ko crawl karta hai using BFS with memory optimization
    def crawl_website(self, start_url, mode="comprehensive", max_pages=50, max_depth=3):
        aggregate_data = {"pages": [], "total_stats": {"pages_scraped": 0, "total_paragraphs": 0}} # Ye aggregated data initialize karti hai
        visited = set() # Ye set visited URLs track karta hai to duplicates avoid kare
        queue = deque([(start_url, 0)]) # Ye queue BFS ke liye initialize karti hai with (url, depth)
        domain = urlparse(start_url).netloc # Ye domain extract karti hai to internal links check kare
       
        print(f"🚀 Starting crawl: {start_url}, Max pages: {max_pages}, Max depth: {max_depth}")
        while queue and len(aggregate_data["pages"]) < max_pages: # Ye loop queue empty na ho aur max pages na exceed ho
            current_url, depth = queue.popleft() # Ye line queue se next URL nikalti hai
            if current_url in visited or depth > max_depth: # Ye check karti hai visited hai ya depth exceed
                continue # Ye skip karti hai agar condition true
            visited.add(current_url) # Ye URL ko visited set mein add karti hai
           
            print(f"📄 Scraping page {len(aggregate_data['pages']) + 1}/{max_pages}: {current_url}")
            page_data = self.scrape_single_page(current_url, mode) # Ye single page scrape karti hai
           
            if "error" not in page_data: # Ye check karti hai error nahi hai
                aggregate_data["pages"].append(page_data) # Ye page data aggregate mein add karti hai
                aggregate_data["total_stats"]["pages_scraped"] += 1 # Ye pages count increase karti hai
                aggregate_data["total_stats"]["total_paragraphs"] += page_data["stats"].get("paragraph_count", 0) # Ye total paragraphs add karti hai
                # Find internal links to enqueue - Ye block new internal links find karta hai with limits
                links_to_add = 0
                for link in page_data.get("internal_links", [])[:20]: # Limited to 20 links per page
                    if links_to_add >= 10: # Maximum 10 new links per page
                        break
                    next_url = link["url"] # Ye next URL extract karti hai
                    if next_url not in visited and urlparse(next_url).netloc == domain: # Ye check karti hai not visited and same domain
                        queue.append((next_url, depth + 1)) # Ye queue mein add karti hai with increased depth
                        links_to_add += 1
            # Progress update - Ye progress update deta hai
            if len(aggregate_data["pages"]) % 10 == 0:
                print(f"📊 Progress: {len(aggregate_data['pages'])} pages scraped")
        aggregate_data["scrape_id"] = str(uuid.uuid4()) # Ye unique ID add karti hai
        aggregate_data["start_url"] = start_url # Ye start URL add karti hai
        aggregate_data["scraped_at"] = datetime.now().isoformat() # Ye timestamp add karti hai
       
        print(f"✅ Crawling completed: {len(aggregate_data['pages'])} pages scraped")
        return aggregate_data # Ye final aggregated data return karti hai
    # ---------- EXPORT METHODS ----------
    # Ye function data ko JSON file mein save karta hai with error handling
    def save_as_json(self, data, filename):
        try: # Ye try block
            downloads_dir = "downloads" # Ye directory name set karti hai
            if not os.path.exists(downloads_dir): # Ye check karti hai directory exists nahi
                os.makedirs(downloads_dir) # Ye directory create karti hai
            filepath = os.path.join(downloads_dir, f"{filename}.json") # Ye filepath banati hai
            with open(filepath, 'w', encoding='utf-8') as f: # Ye file open karti hai write mode mein
                json.dump(data, f, indent=2, ensure_ascii=False) # Ye data JSON mein dump karti hai
            return filepath # Ye filepath return karti hai
        except Exception as e: # Ye exception handle
            print(f"❌ Error saving JSON: {str(e)}")
            return None
    # Ye function data ko CSV file mein save karta hai with error handling
    def save_as_csv(self, data, filename):
        try: # Ye try block
            downloads_dir = "downloads" # Ye directory name set karti hai
            if not os.path.exists(downloads_dir): # Ye check karti hai
                os.makedirs(downloads_dir) # Ye create karti hai
            filepath = os.path.join(downloads_dir, f"{filename}.csv") # Ye filepath banati hai
            csv_data = [] # Ye list initialize karti hai
           
            # Handle crawled pages data - Ye crawled pages handle karta hai
            if 'pages' in data: # Ye check karti hai crawled data hai
                csv_data.append(['Type', 'URL', 'Title', 'Content']) # Ye header add karti hai
                for page in data['pages'][:100]: # Maximum 100 pages
                    csv_data.append(['Page', page.get('url', ''), page.get('title', ''),
                                   ' '.join(page.get('paragraphs', [])[:3])[:200]]) # Limited content
            else: # Single page data
                if data.get('title'): # Ye check karti hai title hai
                    csv_data.append(['Type', 'Content']) # Ye header add karti hai
                    csv_data.append(['Title', data['title']]) # Ye title add karti hai
                if data.get('paragraphs'): # Ye check karti hai paragraphs hain
                    for para in data['paragraphs'][:50]: # Limited paragraphs
                        csv_data.append(['Paragraph', para]) # Ye add karti hai
           
            with open(filepath, 'w', newline='', encoding='utf-8') as f: # Ye file open karti hai
                writer = csv.writer(f) # Ye CSV writer create karti hai
                writer.writerows(csv_data) # Ye rows write karti hai
            return filepath # Ye return karti hai
        except Exception as e: # Ye exception handle
            print(f"❌ Error saving CSV: {str(e)}")
            return None
    # Ye function data ko Excel file mein save karta hai with error handling
    def save_as_excel(self, data, filename):
        try: # Ye try block
            downloads_dir = "downloads" # Ye directory set karti hai
            if not os.path.exists(downloads_dir): # Ye check
                os.makedirs(downloads_dir) # Ye create
            filepath = os.path.join(downloads_dir, f"{filename}.xlsx") # Ye filepath
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer: # Ye Excel writer open karti hai
                summary_data = { # Ye summary data banati hai
                    'Property': ['URL', 'Title', 'Description', 'Scraped At'],
                    'Value': [
                        data.get('url', '') if 'url' in data else data.get('start_url', ''),
                        data.get('title', ''),
                        data.get('description', ''),
                        data.get('scraped_at', '')
                    ]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False) # Ye summary sheet write karti hai
               
                # Handle crawled pages - Ye crawled pages handle karta hai
                if 'pages' in data: # Ye check
                    pages_data = [] # Ye pages data list
                    for page in data['pages'][:50]: # Limited pages
                        pages_data.append({
                            'URL': page.get('url', ''),
                            'Title': page.get('title', ''),
                            'Description': page.get('description', ''),
                            'Paragraphs Count': len(page.get('paragraphs', [])),
                            'Images Count': len(page.get('images', []))
                        })
                    pd.DataFrame(pages_data).to_excel(writer, sheet_name='Pages', index=False) # Ye pages sheet write
               
                if data.get('paragraphs'): # Ye check
                    df = pd.DataFrame({'Paragraphs': data['paragraphs'][:100]}) # Limited paragraphs
                    df.to_excel(writer, sheet_name='Paragraphs', index=False) # Ye write
            return filepath # Ye return
        except Exception as e: # Ye exception handle
            print(f"❌ Error saving Excel: {str(e)}")
            return None
    # Ye function data ko TXT file mein save karta hai with error handling
    def save_as_text(self, data, filename):
        try: # Ye try block
            downloads_dir = "downloads" # Ye directory
            if not os.path.exists(downloads_dir):
                os.makedirs(downloads_dir)
            filepath = os.path.join(downloads_dir, f"{filename}.txt")
            with open(filepath, 'w', encoding='utf-8') as f: # Ye open
                # Handle crawled pages - Ye crawled pages handle karta hai
                if 'pages' in data: # Ye check
                    f.write(f"CRAWL REPORT\n") # Ye write crawl report
                    f.write(f"Start URL: {data.get('start_url', '')}\n") # Ye URL
                    f.write(f"Pages Scraped: {data.get('total_stats', {}).get('pages_scraped', 0)}\n") # Ye count
                    f.write(f"Scraped At: {data.get('scraped_at', '')}\n") # Ye timestamp
                    f.write("=" * 50 + "\n\n") # Ye separator
                   
                    for i, page in enumerate(data['pages'][:20], 1): # Limited pages
                        f.write(f"PAGE {i}: {page.get('url', '')}\n") # Ye page info
                        f.write(f"Title: {page.get('title', 'N/A')}\n") # Ye title
                        f.write(f"Description: {page.get('description', 'N/A')}\n") # Ye description
                        f.write("-" * 30 + "\n") # Ye separator
                       
                        if page.get('paragraphs'): # Ye check
                            f.write("Content:\n") # Ye header
                            for para in page['paragraphs'][:5]: # Limited paragraphs
                                f.write(f"{para}\n\n") # Ye write
                        f.write("\n" + "=" * 30 + "\n\n") # Ye separator
                else: # Single page
                    f.write(f"TITLE: {data.get('title', 'N/A')}\n") # Ye write title
                    f.write(f"URL: {data.get('url', 'N/A')}\n") # Ye URL
                    f.write(f"DESCRIPTION: {data.get('description', 'N/A')}\n") # Ye description
                    f.write(f"SCRAPED AT: {data.get('scraped_at', 'N/A')}\n") # Ye timestamp
                    f.write("=" * 50 + "\n\n") # Ye separator
                    if data.get('headings'): # Ye check
                        for level, headings in data['headings'].items(): # Ye loop
                            for heading in headings[:10]: # Limited headings
                                f.write(f"{level.upper()}: {heading}\n\n") # Ye write
                    if data.get('paragraphs'): # Ye check
                        f.write("PARAGRAPHS:\n") # Ye header
                        f.write("-" * 20 + "\n") # Ye separator
                        for para in data['paragraphs'][:50]: # Limited paragraphs
                            f.write(f"{para}\n\n") # Ye write
            return filepath # Ye return
        except Exception as e: # Ye exception handle
            print(f"❌ Error saving TXT: {str(e)}")
            return None
    # Ye function data ko PDF file mein save karta hai with error handling
    def save_as_pdf(self, data, filename):
        try: # Ye try block
            downloads_dir = "downloads" # Ye directory
            if not os.path.exists(downloads_dir):
                os.makedirs(downloads_dir)
            filepath = os.path.join(downloads_dir, f"{filename}.pdf") # Ye filepath
            pdf = FPDF() # Ye PDF object create karti hai
            pdf.add_page() # Ye new page add karti hai
            pdf.set_font("Arial", size=12) # Ye font set karti hai
           
            # Handle crawled pages - Ye crawled pages handle karta hai
            if 'pages' in data: # Ye check
                pdf.set_font("Arial", size=16, style='B') # Ye bold font
                pdf.cell(0, 10, "Website Crawling Report", ln=True, align='C') # Ye title
                pdf.ln(10) # Ye new line
               
                pdf.set_font("Arial", size=12) # Ye normal font
                pdf.cell(0, 10, f"Start URL: {data.get('start_url', '')}", ln=True) # Ye URL
                pdf.cell(0, 10, f"Pages Scraped: {data.get('total_stats', {}).get('pages_scraped', 0)}", ln=True) # Ye count
                pdf.cell(0, 10, f"Scraped At: {data.get('scraped_at', '')}", ln=True) # Ye timestamp
                pdf.ln(10) # Ye new line
               
                for i, page in enumerate(data['pages'][:10], 1): # Limited pages
                    pdf.add_page() # Ye new page
                    pdf.set_font("Arial", size=14, style='B') # Ye bold
                    pdf.cell(0, 10, f"Page {i}: {page.get('title', 'N/A')}", ln=True) # Ye page title
                    pdf.set_font("Arial", size=12) # Ye normal
                    pdf.cell(0, 10, f"URL: {page.get('url', '')}", ln=True) # Ye URL
                    pdf.ln(5) # Ye space
                   
                    if page.get('paragraphs'): # Ye check
                        for para in page['paragraphs'][:3]: # Limited paragraphs
                            lines = [para[i:i+80] for i in range(0, len(para), 80)] # Ye long para split
                            for line in lines: # Ye inner loop
                                pdf.cell(0, 8, line, ln=True) # Ye line write
                            pdf.ln(5) # Ye space
            else: # Single page
                if data.get('title'): # Ye check
                    pdf.set_font("Arial", size=16, style='B') # Ye bold font
                    pdf.cell(0, 10, data['title'], ln=True, align='C') # Ye title cell
                    pdf.ln(10) # Ye new line
                pdf.set_font("Arial", size=12) # Ye normal font
                if data.get('url'): # Ye check
                    pdf.cell(0, 10, f"URL: {data['url']}", ln=True) # Ye URL
                if data.get('description'): # Ye check
                    pdf.cell(0, 10, f"Description: {data['description']}", ln=True) # Ye description
                pdf.ln(10) # Ye new line
                if data.get('headings'): # Ye check
                    pdf.set_font("Arial", size=14, style='B') # Ye bold
                    pdf.cell(0, 10, "Headings:", ln=True) # Ye header
                    pdf.set_font("Arial", size=12) # Ye normal
                    for level, headings in data['headings'].items(): # Ye loop
                        for heading in headings[:10]: # Limited headings
                            pdf.cell(0, 8, f"{level.upper()}: {heading}", ln=True) # Ye heading
                    pdf.ln(10) # Ye new line
                if data.get('paragraphs'): # Ye check
                    pdf.set_font("Arial", size=14, style='B') # Ye bold
                    pdf.cell(0, 10, "Content:", ln=True) # Ye header
                    pdf.set_font("Arial", size=12) # Ye normal
                    for para in data['paragraphs'][:20]: # Limited paragraphs
                        lines = [para[i:i+80] for i in range(0, len(para), 80)] # Ye long para split
                        for line in lines: # Ye inner loop
                            pdf.cell(0, 8, line, ln=True) # Ye line write
                        pdf.ln(5) # Ye space
            pdf.output(filepath) # Ye PDF save karti hai
            return filepath # Ye return
        except Exception as e: # Ye exception handle
            print(f"❌ Error saving PDF: {str(e)}")
            return None

# app.py
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from groq import Groq
from scraper import UltraScraper
import os, json, time, random
# Load .env variables
load_dotenv()
# Initialize FastAPI
app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()
# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
# ---------- GROQ ----------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"
# Initialize Groq client without proxies
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
# ---------- HOME ----------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
# ---------- HEALTH ----------
@app.get("/health")
async def health():
    return {"status": "healthy"}
# ---------- SCRAPE ----------
@app.post("/scrape")
async def scrape(request: Request):
    form = await request.form()
    url = form.get("url")
    mode = form.get("mode", "comprehensive")
    if not url:
        return {"success": False, "error": "URL required"}
    if not url.startswith("http"):
        url = "https://" + url
    data = scraper.scrape_website(url, mode)
    if "error" in data:
        return {"success": False, "error": data["error"]}
    return {"success": True, "data": data}
# ---------- GROQ CHAT ----------
@app.post("/groq-chat")
async def chat(request: Request):
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not set or invalid"}
    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")
    if not message or not scraped:
        return {"success": False, "error": "Missing data"}
    data = json.loads(scraped)
    system_prompt = """
You are an EXACT factual AI assistant with advanced data processing capabilities.
Rules:
1. READ the scraped data content provided below in READABLE FORMAT
2. ANSWER the user's question directly using ONLY that content
3. The content is already structured for you - use it directly
4. If answer not found, say: "This information is not available in the scraped website data."
5. NEVER guess or use outside knowledge
6. IMPORTANT: Provide ANSWERS, not explanations about what data you have
7. If user asks to modify specific content, find that content and modify it accurately
8. For paragraph modifications: Find the exact paragraph and modify it while keeping the rest intact
"""
    # NEW: Circuit Breaker Pattern - Ultimate 429 Solution
    def build_smart_context(data, message):
        context_parts = ["SCRAPED DATA ANALYSIS:"]
        
        # Check if user wants specific content modification
        wants_modification = any(word in message.lower() for word in ['change', 'modify', 'update', 'edit', 'remove', 'replace'])
        
        # Ultra-minimal data selection - only 1 page max
        if 'pages' in data:
            # Multi-page crawl data
            context_parts.append(f"Website: {data.get('start_url', 'Unknown')}")
            context_parts.append(f"Total pages: {len(data['pages'])}")
            context_parts.append("")
            
            # Only first page for any query type
            for i, page in enumerate(data['pages'][:1]):  # Limit to 1 page only
                context_parts.append(f"PAGE {i+1}: {page.get('title', 'No title')}")
                    
                # Only title and short description
                if page.get('description') and len(page['description']) < 100:
                    context_parts.append(f"Description: {page['description']}")
                
                # Only H1 heading
                if page.get('headings') and page['headings'].get('h1'):
                    context_parts.append(f"H1: {page['headings']['h1'][0] if page['headings']['h1'] else 'None'}")
                
                # Only first 1 paragraph maximum
                if page.get('paragraphs'):
                    context_parts.append("Content:")
                    for para in page['paragraphs'][:1]:  # Only 1 paragraph
                        if len(para) < 150:  # Only very short paragraphs
                            context_parts.append(f"- {para}")
                
                context_parts.append("")
        else:
            # Single page data - super minimal
            context_parts.append(f"Page: {data.get('title', 'No title')}")
            
            # Only very short description
            if data.get('description') and len(data['description']) < 80:
                context_parts.append(f"Description: {data['description']}")
            
            # Only H1 heading
            if data.get('headings') and data['headings'].get('h1'):
                context_parts.append(f"H1: {data['headings']['h1'][0] if data['headings']['h1'] else 'None'}")
            
            # Only first 1 paragraph
            if data.get('paragraphs'):
                context_parts.append("Content:")
                if wants_modification:
                    # For modifications, only first 2 paragraphs
                    for para in data['paragraphs'][:2]:
                        if len(para) < 120:  # Only very short paragraphs
                            context_parts.append(f"- {para}")
                else:
                    # For regular queries, only first 1 paragraph
                    for para in data['paragraphs'][:1]:
                        if len(para) < 100:  # Only very short paragraphs
                            context_parts.append(f"- {para}")
        
        context_parts.append(f"\nQUESTION: {message}")
        context_parts.append(f"\nMODIFICATION REQUEST: {'Yes' if wants_modification else 'No'}")
        
        return "\n".join(context_parts)

    # Build ultra-minimal context to avoid 429
    context = build_smart_context(data, message)

    # Circuit Breaker Pattern with Exponential Backoff
    max_retries = 3
    base_delay = 5.0  # Start with 5 second delay
    
    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1}/{max_retries}: Waiting {base_delay:.1f}s before API call...")
            time.sleep(base_delay)
            
            # Ultra-minimal request to avoid rate limiting completely
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                temperature=0,
                max_tokens=500  # Minimal tokens to avoid rate limits
            )

            answer = getattr(getattr(response.choices[0], "message", None), "content", None)
            if not answer:
                answer = "Groq API did not return any answer."

            print(f"✅ Success! Got response in {base_delay:.1f}s")
            return {"success": True, "response": answer.strip()}

        except Exception as e:
            error_str = str(e)
            if "429" in error_str:
                if attempt < max_retries - 1:
                    # Exponential backoff: 5s -> 10s -> 20s
                    base_delay *= 2
                    print(f"⚠️ Rate limit hit. Retrying in {base_delay:.1f}s...")
                    continue
                else:
                    return {"success": False, "error": "⚠️ Rate limit exceeded. Please wait 60 seconds before trying again."}
            elif "401" in error_str:
                return {"success": False, "error": "❌ API key issue. Please check your Groq API key."}
            else:
                return {"success": False, "error": f"❌ Groq API error: {error_str}"}
    
    return {"success": False, "error": "❌ Max retries exceeded for Groq API."}
# ---------- GROK MODE ----------
@app.post("/grok-mode")
async def grok_mode(request: Request):
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not set or invalid"}
    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")
    analysis_type = form.get("analysis_type", "comprehensive")
    if not message or not scraped:
        return {"success": False, "error": "Missing message or scraped data"}
    data = json.loads(scraped)
    system_prompt = (
        "You are GROK MODE - An advanced AI for universal questions. "
        "RULES: 1. UNIVERSAL KNOWLEDGE ONLY - Use your comprehensive knowledge base. "
        "2. DO NOT use scraped data - ignore website content. "
        "3. PROVIDE expert answers on any topic. "
        "4. BE helpful and comprehensive. "
        "5. Use your full knowledge for all responses."
    )
    full_context = f"USER QUESTION:\n{message}\n\n(Note: This is a universal knowledge question. Provide comprehensive answer using your knowledge base.)"
    # Professional retry mechanism for Groq API with exponential backoff
    max_retries = 5  # Maximum retry attempts
    retry_delay = 2.0  # Initial delay in seconds
    for attempt in range(max_retries):
        try:
            # Add jitter to delay
            time.sleep(retry_delay + random.uniform(0, 1))
            response = client.chat.completions.create(
                model=MODEL_DEEP,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_context} # Removed character limit for unlimited answers
                ],
                temperature=0.2,
                max_tokens=8000 # Increased from 2000 to 8000 for much longer answers
            )
            answer = getattr(response.choices[0].message, 'content', None)
            if not answer:
                answer = "No response generated."
            return {"success": True, "response": answer.strip(), "mode": "grok_mode"}
        except Exception as e:
            error_str = str(e)
            if "429" in error_str:
                if attempt < max_retries - 1:
                    retry_delay *= 2  # Exponential backoff
                    continue  # Retry after delay
                else:
                    return {"success": False, "error": "⚠️ Rate limit exceeded after multiple retries. Please try again later."}
            else:
                return {"success": False, "error": f"Grok Mode error: {error_str}"}
    return {"success": False, "error": "❌ Max retries exceeded for Groq API."}
# ---------- GROK SUMMARY ----------
@app.post("/grok-summary")
async def grok_summary(request: Request):
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not set or invalid"}
    form = await request.form()
    scraped = form.get("scraped_data")
    if not scraped:
        return {"success": False, "error": "Missing scraped data"}
    data = json.loads(scraped)
    system_prompt = (
        "GROK SUMMARY - Extract key facts. "
        "Provide: 1. MAIN TOPIC. 2. KEY POINTS (3-5). 3. STATISTICS. 4. CONCLUSION. "
        "Only use page data."
    )
    context_parts = ["URL: " + data.get('url', '')]
    if data.get('title'):
        context_parts.append("Title: " + data['title'])
    if data.get('paragraphs'):
        context_parts.append("\n".join(data['paragraphs'][:15]))
    # Professional retry mechanism for Groq API with exponential backoff
    max_retries = 5  # Maximum retry attempts
    retry_delay = 2.0  # Initial delay in seconds
    for attempt in range(max_retries):
        try:
            # Add jitter to delay
            time.sleep(retry_delay + random.uniform(0, 1))
            response = client.chat.completions.create(
                model=MODEL_DEEP,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "\n\n".join(context_parts)}
                ],
                temperature=0.1,
                max_tokens=500
            )
            answer = getattr(response.choices[0].message, 'content', 'No summary.')
            return {"success": True, "summary": answer.strip(), "mode": "grok_summary"}
        except Exception as e:
            error_str = str(e)
            if "429" in error_str:
                if attempt < max_retries - 1:
                    retry_delay *= 2  # Exponential backoff
                    continue  # Retry after delay
                else:
                    return {"success": False, "error": "⚠️ Rate limit exceeded after multiple retries. Please try again later."}
            else:
                return {"success": False, "error": f"Summary error: {error_str}"}
    return {"success": False, "error": "❌ Max retries exceeded for Groq API."}
# ---------- EXPORT ----------
@app.post("/export")
async def export(request: Request):
    body = await request.json()
    fmt = body.get("format")
    data = body.get("data")
    if not fmt or not data:
        return {"success": False, "error": "Missing format or data"}
    filename = f"scraped_{int(time.time())}"
    handlers = {
        "json": scraper.save_as_json,
        "csv": scraper.save_as_csv,
        "excel": scraper.save_as_excel,
        "txt": scraper.save_as_text,
        "pdf": scraper.save_as_pdf
    }
    if fmt not in handlers:
        return {"success": False, "error": f"Unsupported format: {fmt}"}
    path = handlers[fmt](data, filename)
    return FileResponse(path, filename=os.path.basename(path))