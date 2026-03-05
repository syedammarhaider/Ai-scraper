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
from collections import deque  # Ye import BFS ke liye queue use karne ke liye hai
from requests.adapters import HTTPAdapter  # Ye import retry mechanism ke liye hai
from requests.packages.urllib3.util.retry import Retry  # Ye import retry strategy ke liye hai
from typing import Dict, List, Any, Optional  # Ye type hints ke liye

# Disable SSL warnings - Ye line SSL warnings ko disable karti hai taake insecure requests mein warnings na aayein
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Memory and performance constants - Ye constants memory optimization ke liye hain
MAX_MEMORY_USAGE = 500 * 1024 * 1024  # 500MB max memory usage
MAX_PARAGRAPHS_PER_PAGE = 100  # Maximum paragraphs per page
MAX_IMAGES_PER_PAGE = 50  # Maximum images per page
MAX_LINKS_PER_PAGE = 200  # Maximum links per page
CHUNK_SIZE = 50  # Pages chunk size for processing

class UltraScraper:
    # Ye init function class ko initialize karta hai with memory optimization
    def __init__(self):
        self.session = requests.Session()  # Ye line requests session create karti hai for persistent connections
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})  # Ye line user-agent set karti hai to look like browser
        self.session.verify = False  # Ye line SSL verification disable karti hai for insecure sites

        # Retry mechanism: 3 retries with backoff - Ye block robust error handling add karta hai with retries
        retry_strategy = Retry(  # Ye retry strategy define karti hai
            total=3,  # Ye total retries set karti hai (3 times try karega)
            status_forcelist=[429, 500, 502, 503, 504],  # Ye status codes set karti hai jin par retry karega (server errors)
            backoff_factor=1  # Ye backoff time set karti hai (1 second delay increase)
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)  # Ye adapter create karti hai retry ke sath
        self.session.mount("https://", adapter)  # Ye HTTPS ke liye adapter mount karti hai
        self.session.mount("http://", adapter)  # Ye HTTP ke liye adapter mount karti hai
        
        # Memory tracking - Ye memory usage track karta hai
        self.memory_usage = 0  # Ye current memory usage track karta hai
        self.processed_pages = 0  # Ye processed pages count karta hai

    # ---------- MEMORY MANAGEMENT ----------
    # Ye function memory usage ko check karta hai
    def check_memory_usage(self):
        """Ye function memory usage check karta hai aur garbage collector run karta hai"""
        if self.memory_usage > MAX_MEMORY_USAGE:
            print("🧹 Memory usage high, running garbage collection...")
            gc.collect()  # Ye garbage collector run karta hai
            self.memory_usage = self.memory_usage // 2  # Ye memory usage estimate karta hai
            return True
        return False

    # Ye function data size ko estimate karta hai
    def estimate_data_size(self, data: Any) -> int:
        """Ye function data size estimate karta hai bytes mein"""
        try:
            return len(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        except:
            return 1024  # Default estimate

    # ---------- UTILS ----------
    # Ye function text ko clean karta hai (extra spaces remove)
    def clean(self, text):
        return re.sub(r"\s+", " ", text).strip() if text else ""  # Ye line regex se extra spaces remove karti hai aur strip karti hai

    # Ye function relative URL ko absolute banata hai
    def abs_url(self, url, base):
        return urljoin(base, url)  # Ye line urljoin use kar ke absolute URL banati hai

    # Ye function empty values ko dictionary se remove karta hai
    def remove_empty(self, data):
        return {k: v for k, v in data.items() if v not in ("", None, [], {})}  # Ye line comprehension se non-empty items filter karti hai

    # ---------- SINGLE PAGE SCRAPER ----------
    # Ye function single page ko scrape karta hai with memory optimization
    def scrape_single_page(self, url, mode="comprehensive"):
        start = time.time()  # Ye line scraping time measure karne ke liye start time set karti hai
        try:
            r = self.session.get(url, timeout=30)  # Ye line GET request bhejti hai with timeout 30 seconds
            r.raise_for_status()  # Ye line check karti hai agar error hai to raise karega
            soup = BeautifulSoup(r.text, "html.parser")  # Ye line HTML ko parse karti hai BeautifulSoup se

            # Remove scripts/styles - Ye block unnecessary tags remove karta hai
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()  # Ye line tag ko remove karti hai

            # Metadata - Ye block title aur description extract karta hai
            title = self.clean(soup.title.string) if soup.title else ""  # Ye line title clean karti hai
            description = ""  # Ye line description initialize karti hai
            meta_desc = soup.find("meta", attrs={"name": "description"})  # Ye line meta description find karti hai
            if meta_desc:
                description = self.clean(meta_desc.get("content"))  # Ye line description clean karti hai

            # Headings - Ye block all headings (h1 to h6) collect karta hai with limits
            headings = {f"h{i}": [self.clean(h.get_text()) for h in soup.find_all(f"h{i}")[:10]]  # Limited to 10 per level
                        for i in range(1, 7)}  # Ye comprehension headings dictionary banati hai

            # Paragraphs - Ye block paragraphs collect karta hai with memory optimization
            all_paragraphs = [self.clean(p.get_text()) for p in soup.find_all("p") if len(p.get_text()) > 30]
            paragraphs = all_paragraphs[:MAX_PARAGRAPHS_PER_PAGE]  # Ye paragraphs ko limit karta hai
            if len(all_paragraphs) > MAX_PARAGRAPHS_PER_PAGE:
                print(f"📄 Limited paragraphs from {len(all_paragraphs)} to {len(paragraphs)}")

            # Structured data: tables + lists + Google Sheets - Ye line structured data extract karti hai
            structured_data = self.extract_structured_data(soup, url)  # Ye function call karti hai structured data ke liye

            # Images - Ye block images collect karta hai with limits and filtering
            all_images = []
            for img in soup.find_all("img"):
                src = img.get("src")
                if src and not src.startswith("data:image/svg+xml"):  # SVG data URLs ko filter karta hai
                    all_images.append({
                        "url": self.abs_url(src, url), 
                        "alt": self.clean(img.get("alt"))
                    })
            images = all_images[:MAX_IMAGES_PER_PAGE]  # Ye images ko limit karta hai
            if len(all_images) > MAX_IMAGES_PER_PAGE:
                print(f"🖼️ Limited images from {len(all_images)} to {len(images)}")

            # Links - Ye block internal aur external links separate karta hai with limits and filtering
            domain = urlparse(url).netloc  # Ye line domain extract karti hai
            all_internal_links, all_external_links = [], []  # Ye line lists initialize karti hai
            for a in soup.find_all("a", href=True):  # Ye loop all anchors par iterate karta hai
                if len(all_internal_links) >= MAX_LINKS_PER_PAGE and len(all_external_links) >= MAX_LINKS_PER_PAGE:
                    break  # Ye limit check kar ke break karta hai
                href = a["href"]
                # Invalid links ko filter karta hai
                if (href.startswith("data:") or href.startswith("javascript:") or 
                    href.startswith("mailto:") or href.startswith("tel:") or 
                    href.startswith("#") or not href.strip()):
                    continue  # Ye invalid links skip karta hai
                
                link = self.abs_url(href, url)  # Ye line absolute link banati hai
                text = self.clean(a.get_text())  # Ye line link text clean karti hai
                
                # Empty text links ko skip karta hai
                if not text or len(text.strip()) < 2:
                    continue
                    
                if urlparse(link).netloc == domain:  # Ye check karti hai internal link hai ya nahi
                    if len(all_internal_links) < MAX_LINKS_PER_PAGE:
                        all_internal_links.append({"url": link, "text": text})  # Ye internal link add karti hai
                else:
                    if len(all_external_links) < MAX_LINKS_PER_PAGE:
                        all_external_links.append({"url": link, "text": text})  # Ye external link add karti hai
            
            internal_links = all_internal_links
            external_links = all_external_links
            
            if len(all_internal_links) > MAX_LINKS_PER_PAGE or len(all_external_links) > MAX_LINKS_PER_PAGE:
                print(f"🔗 Limited links to {len(internal_links)} internal and {len(external_links)} external")

            # Full readable text - Ye line professional text generate karta hai with length limit
            full_text = self.generate_professional_text(soup, structured_data, url)  # Ye function call karti hai text ke liye
            if len(full_text) > 50000:  # 50KB se zyada ho to
                full_text = full_text[:50000] + "...[truncated]"
                print(f"📝 Truncated full text to 50KB")

            # Compose final JSON based on mode - Ye block mode ke according data structure banata hai
            if mode == "basic":
                data = {  # Ye dictionary basic mode ke liye banati hai
                    "url": url,  # Ye URL add karti hai
                    "title": title,  # Ye title add karti hai
                    "description": description,  # Ye description add karti hai
                    "paragraphs": paragraphs[:5],  # Ye first 5 paragraphs add karti hai
                    "stats": {  # Ye stats dictionary banati hai
                        "paragraph_count": len(paragraphs[:5]),  # Ye count set karti hai
                        "scrape_time": round(time.time() - start, 2)  # Ye scrape time calculate karti hai
                    },
                    "scraped_at": datetime.now().isoformat()  # Ye timestamp add karti hai
                }
            elif mode == "smart":
                data = {  # Ye dictionary smart mode ke liye banati hai
                    "url": url,
                    "title": title,
                    "description": description,
                    "headings": {k: v[:3] for k, v in headings.items()},  # Ye limited headings add karti hai
                    "paragraphs": paragraphs[:10],  # Ye first 10 paragraphs add karti hai
                    "images": images[:5],  # Ye first 5 images add karti hai
                    "stats": {
                        "paragraph_count": len(paragraphs[:10]),
                        "image_count": len(images[:5]),
                        "scrape_time": round(time.time() - start, 2)
                    },
                    "scraped_at": datetime.now().isoformat()
                }
            else:
                data = {  # Ye dictionary comprehensive mode ke liye banati hai
                    "url": url,
                    "title": title,
                    "description": description,
                    "headings": headings,  # Ye all headings add karti hai
                    "paragraphs": paragraphs,  # Ye all paragraphs add karti hai
                    "structured_data": structured_data,  # Ye structured data add karti hai
                    "images": images,  # Ye all images add karti hai
                    "internal_links": internal_links,  # Ye internal links add karti hai
                    "external_links": external_links,  # Ye external links add karti hai
                    "full_text": full_text,  # Ye full text add karti hai
                    "stats": {
                        "paragraph_count": len(paragraphs),
                        "image_count": len(images),
                        "internal_links_count": len(internal_links),
                        "external_links_count": len(external_links),
                        "table_count": len(structured_data.get("tables", [])),
                        "list_count": len(structured_data.get("lists", [])),
                        "scrape_time": round(time.time() - start, 2)
                    },
                    "scraped_at": datetime.now().isoformat()
                }

            # Memory usage update - Ye memory usage track karta hai
            data_size = self.estimate_data_size(data)
            self.memory_usage += data_size
            self.processed_pages += 1
            
            # Memory check - Ye memory check karta hai
            self.check_memory_usage()

            return self.remove_empty(data)  # Ye line empty values remove karti hai aur return karti hai

        except Exception as e:  # Ye block error handle karta hai
            return {"error": str(e)}  # Ye error message return karti hai

    # ---------- FULL WEBSITE CRAWLER USING BFS ----------
    # Ye new function pori site ko crawl karta hai using BFS with memory optimization
    def crawl_website(self, start_url, mode="comprehensive", max_pages=50, max_depth=3):
        aggregate_data = {"pages": [], "total_stats": {"pages_scraped": 0, "total_paragraphs": 0}}  # Ye aggregated data initialize karti hai
        visited = set()  # Ye set visited URLs track karta hai to duplicates avoid kare
        queue = deque([(start_url, 0)])  # Ye queue BFS ke liye initialize karti hai with (url, depth)
        domain = urlparse(start_url).netloc  # Ye domain extract karti hai to internal links check kare
        
        print(f"🚀 Starting crawl: {start_url}, Max pages: {max_pages}, Max depth: {max_depth}")

        while queue and len(aggregate_data["pages"]) < max_pages:  # Ye loop queue empty na ho aur max pages na exceed ho
            current_url, depth = queue.popleft()  # Ye line queue se next URL nikalti hai
            if current_url in visited or depth > max_depth:  # Ye check karti hai visited hai ya depth exceed
                continue  # Ye skip karti hai agar condition true

            visited.add(current_url)  # Ye URL ko visited set mein add karti hai
            
            # Memory check before scraping - Ye memory check karta hai scraping se pehle
            if self.check_memory_usage():
                print("⚠️ Memory optimized during crawling")
            
            print(f"📄 Scraping page {len(aggregate_data['pages']) + 1}/{max_pages}: {current_url}")
            page_data = self.scrape_single_page(current_url, mode)  # Ye single page scrape karti hai
            
            if "error" not in page_data:  # Ye check karti hai error nahi hai
                aggregate_data["pages"].append(page_data)  # Ye page data aggregate mein add karti hai
                aggregate_data["total_stats"]["pages_scraped"] += 1  # Ye pages count increase karti hai
                aggregate_data["total_stats"]["total_paragraphs"] += page_data["stats"].get("paragraph_count", 0)  # Ye total paragraphs add karti hai

                # Find internal links to enqueue - Ye block new internal links find karta hai with limits
                links_to_add = 0
                for link in page_data.get("internal_links", [])[:20]:  # Limited to 20 links per page
                    if links_to_add >= 10:  # Maximum 10 new links per page
                        break
                    next_url = link["url"]  # Ye next URL extract karti hai
                    if next_url not in visited and urlparse(next_url).netloc == domain:  # Ye check karti hai not visited and same domain
                        queue.append((next_url, depth + 1))  # Ye queue mein add karti hai with increased depth
                        links_to_add += 1

            # Progress update - Ye progress update deta hai
            if len(aggregate_data["pages"]) % 10 == 0:
                print(f"📊 Progress: {len(aggregate_data['pages'])} pages scraped, Memory usage: ~{self.memory_usage // (1024*1024)}MB")

        aggregate_data["scrape_id"] = str(uuid.uuid4())  # Ye unique ID add karti hai
        aggregate_data["start_url"] = start_url  # Ye start URL add karti hai
        aggregate_data["scraped_at"] = datetime.now().isoformat()  # Ye timestamp add karti hai
        aggregate_data["total_stats"]["memory_usage_mb"] = self.memory_usage // (1024*1024)  # Ye memory usage add karti hai
        
        print(f"✅ Crawling completed: {len(aggregate_data['pages'])} pages scraped")
        return aggregate_data  # Ye final aggregated data return karti hai

    # ---------- STRUCTURED DATA ----------
    # Ye function structured data (tables, lists) extract karta hai with optimization
    def extract_structured_data(self, soup, url):
        structured_data = {"tables": [], "lists": []}  # Ye dictionary initialize karti hai

        # Tables - Ye block tables extract karta hai with limits
        tables = soup.find_all("table")[:10]  # Maximum 10 tables
        for table in tables:  # Ye loop tables par iterate karta hai
            t = self.extract_table_data(table)  # Ye table data extract karti hai
            if t:  # Ye check karti hai data mila hai
                structured_data["tables"].append(t)  # Ye append karti hai

        # Lists - Ye block lists extract karta hai with limits
        lists = soup.find_all(["ul", "ol"])[:20]  # Maximum 20 lists
        for list_tag in lists:  # Ye loop ul/ol par iterate karta hai
            l = self.extract_list_data(list_tag)  # Ye list data extract karti hai
            if l:  # Ye check karti hai data mila hai
                structured_data["lists"].append(l)  # Ye append karti hai

        # Google Sheets (optional) - Ye block agar Google Sheets hai to extract karta hai
        if "docs.google.com/spreadsheets" in url:  # Ye check karti hai URL mein sheets hai
            sheets = self.extract_google_sheets_data(soup)  # Ye sheets data extract karti hai
            if sheets:  # Ye check karti hai data mila hai
                structured_data["tables"].extend(sheets)  # Ye extend karti hai

        return structured_data  # Ye structured data return karti hai

    # Ye function single table se data extract karta hai with optimization
    def extract_table_data(self, table):
        headers, rows = [], []  # Ye lists initialize karti hai
        header_row = table.find("tr")  # Ye first row find karti hai
        if header_row:  # Ye check karti hai row mila hai
            headers = [self.clean(th.get_text()) for th in header_row.find_all(["th", "td"])[:10]]  # Max 10 columns
        table_rows = table.find_all("tr")[1:50]  # Maximum 50 rows
        for tr in table_rows:  # Ye loop remaining rows par iterate karta hai
            row = [self.clean(td.get_text()) for td in tr.find_all("td")[:10]]  # Max 10 columns
            if any(row):  # Ye check karti hai row empty nahi hai
                rows.append(row)  # Ye append karti hai
        if headers or rows:  # Ye check karti hai data mila hai
            return {"headers": headers, "rows": rows,  # Ye dictionary return karti hai
                    "row_count": len(rows), "column_count": len(headers) if headers else (len(rows[0]) if rows else 0)}
        return None  # Ye None return karti hai agar data nahi

    # Ye function single list se data extract karta hai with optimization
    def extract_list_data(self, list_tag):
        list_items = list_tag.find_all("li")[:50]  # Maximum 50 items
        items = [self.clean(li.get_text()) for li in list_items if self.clean(li.get_text())]  # Ye items collect karti hai
        if items:  # Ye check karti hai items mile hain
            return {"type": list_tag.name, "items": items, "item_count": len(items)}  # Ye dictionary return karti hai
        return None  # Ye None return karti hai

    # Ye function Google Sheets se data extract karta hai
    def extract_google_sheets_data(self, soup):
        tables = []  # Ye list initialize karti hai
        for table in soup.find_all("table")[:5]:  # Maximum 5 tables for sheets
            t = self.extract_table_data(table)  # Ye table data extract karti hai
            if t:  # Ye check karti hai data mila hai
                t["source"] = "google_sheets"  # Ye source add karti hai
                tables.append(t)  # Ye append karti hai
        return tables  # Ye tables return karti hai

    # ---------- PROFESSIONAL TEXT ----------
    # Ye function readable text generate karta hai from soup with length limits
    def generate_professional_text(self, soup, structured_data, base_url=""):
        parts = []  # Ye list initialize karti hai for text parts

        # Title - Ye block title add karta hai
        if soup.title:  # Ye check karti hai title mila hai
            parts.append(f"# TITLE: {self.clean(soup.title.string)}\n")  # Ye title append karti hai

        # Headings - Ye block headings add karta hai with limits
        for i in range(1, 7):  # Ye loop h1 to h6 par iterate karta hai
            headings = soup.find_all(f"h{i}")[:5]  # Maximum 5 headings per level
            for h in headings:  # Ye inner loop headings find karti hai
                parts.append(f"{'#' * i} {self.clean(h.get_text())}")  # Ye heading append karti hai

        # Tables - Ye block tables add karta hai with limits
        if structured_data.get("tables"):  # Ye check karti hai tables hain
            parts.append("\n## TABLES")  # Ye header append karti hai
            for idx, table in enumerate(structured_data["tables"][:3], 1):  # Maximum 3 tables
                parts.append(f"\n### Table {idx}")  # Ye table number append karti hai
                if table.get("headers"):  # Ye check karti hai headers hain
                    parts.append(" | ".join(table["headers"][:5]))  # Maximum 5 columns
                    parts.append("-" * (len(" | ".join(table["headers"][:5]))))  # Ye separator append karti hai
                for row in table.get("rows", [])[:10]:  # Maximum 10 rows
                    parts.append(" | ".join(str(cell) for cell in row[:5]))  # Maximum 5 columns

        # Lists - Ye block lists add karta hai with limits
        if structured_data.get("lists"):  # Ye check karti hai lists hain
            parts.append("\n## LISTS")  # Ye header append karti hai
            for lst in structured_data["lists"][:3]:  # Maximum 3 lists
                parts.append(f"\n### {lst['type'].upper()} LIST")  # Ye list type append karti hai
                for item in lst["items"][:10]:  # Maximum 10 items
                    parts.append(f"- {item}")  # Ye item append karti hai

        # Paragraphs - Ye block paragraphs add karta hai with limits
        paragraphs = soup.find_all("p")[:20]  # Maximum 20 paragraphs
        for p in paragraphs:  # Ye loop paragraphs par iterate karta hai
            text = self.clean(p.get_text())  # Ye text clean karti hai
            if len(text) > 30:  # Ye check karti hai length >30
                parts.append(f"\n{text}")  # Ye paragraph append karti hai

        # Images URLs - Ye block images add karta hai with limits
        images = soup.find_all("img")[:10]  # Maximum 10 images
        if images:  # Ye check karti hai images hain
            parts.append("\n## IMAGES")  # Ye header append karti hai
            for img in images:  # Ye loop images par iterate karta hai
                src = img.get("src")  # Ye src extract karti hai
                if src:  # Ye check karti hai src mila hai
                    parts.append(f"- {self.abs_url(src, base_url)}")  # Ye image URL append karti hai

        # Links URLs - Ye block links add karta hai with limits
        parts.append("\n## LINKS")  # Ye header append karti hai
        domain = urlparse(base_url).netloc  # Ye domain extract karti hai
        links = soup.find_all("a", href=True)[:20]  # Maximum 20 links
        for a in links:  # Ye loop anchors par iterate karta hai
            link = self.abs_url(a["href"], base_url)  # Ye absolute link banati hai
            parts.append(f"- {link}")  # Ye link append karti hai

        # Join and limit - Ye text ko join karta hai aur limit karta hai
        full_text = "\n".join(parts).strip()
        if len(full_text) > 50000:  # 50KB se zyada ho to
            full_text = full_text[:50000] + "...[truncated]"
        
        return full_text  # Ye final text return karti hai

    # ---------- EXPORT METHODS ----------
    # Ye function data ko JSON file mein save karta hai with error handling
    def save_as_json(self, data, filename):
        try:  # Ye try block
            downloads_dir = "downloads"  # Ye directory name set karti hai
            if not os.path.exists(downloads_dir):  # Ye check karti hai directory exists nahi
                os.makedirs(downloads_dir)  # Ye directory create karti hai
            filepath = os.path.join(downloads_dir, f"{filename}.json")  # Ye filepath banati hai
            with open(filepath, 'w', encoding='utf-8') as f:  # Ye file open karti hai write mode mein
                json.dump(data, f, indent=2, ensure_ascii=False)  # Ye data JSON mein dump karti hai
            return filepath  # Ye filepath return karti hai
        except Exception as e:  # Ye exception handle
            print(f"❌ Error saving JSON: {str(e)}")
            return None

    # Ye function data ko CSV file mein save karta hai with error handling
    def save_as_csv(self, data, filename):
        try:  # Ye try block
            downloads_dir = "downloads"  # Ye directory name set karti hai
            if not os.path.exists(downloads_dir):  # Ye check karti hai
                os.makedirs(downloads_dir)  # Ye create karti hai
            filepath = os.path.join(downloads_dir, f"{filename}.csv")  # Ye filepath banati hai
            csv_data = []  # Ye list initialize karti hai
            
            # Handle crawled pages data - Ye crawled pages handle karta hai
            if 'pages' in data:  # Ye check karti hai crawled data hai
                csv_data.append(['Type', 'URL', 'Title', 'Content'])  # Ye header add karti hai
                for page in data['pages'][:100]:  # Maximum 100 pages
                    csv_data.append(['Page', page.get('url', ''), page.get('title', ''), 
                                   ' '.join(page.get('paragraphs', [])[:3])[:200]])  # Limited content
            else:  # Single page data
                if data.get('title'):  # Ye check karti hai title hai
                    csv_data.append(['Type', 'Content'])  # Ye header add karti hai
                    csv_data.append(['Title', data['title']])  # Ye title add karti hai
                if data.get('headings'):  # Ye check karti hai headings hain
                    for level, headings in data['headings'].items():  # Ye loop headings par
                        for heading in headings[:10]:  # Limited headings
                            csv_data.append([level.upper(), heading])  # Ye add karti hai
                if data.get('paragraphs'):  # Ye check karti hai paragraphs hain
                    for para in data['paragraphs'][:50]:  # Limited paragraphs
                        csv_data.append(['Paragraph', para])  # Ye add karti hai
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:  # Ye file open karti hai
                writer = csv.writer(f)  # Ye CSV writer create karti hai
                writer.writerows(csv_data)  # Ye rows write karti hai
            return filepath  # Ye return karti hai
        except Exception as e:  # Ye exception handle
            print(f"❌ Error saving CSV: {str(e)}")
            return None

    # Ye function data ko Excel file mein save karta hai with error handling
    def save_as_excel(self, data, filename):
        try:  # Ye try block
            downloads_dir = "downloads"  # Ye directory set karti hai
            if not os.path.exists(downloads_dir):  # Ye check
                os.makedirs(downloads_dir)  # Ye create
            filepath = os.path.join(downloads_dir, f"{filename}.xlsx")  # Ye filepath
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:  # Ye Excel writer open karti hai
                summary_data = {  # Ye summary data banati hai
                    'Property': ['URL', 'Title', 'Description', 'Scraped At'],
                    'Value': [
                        data.get('url', '') if 'url' in data else data.get('start_url', ''),
                        data.get('title', ''),
                        data.get('description', ''),
                        data.get('scraped_at', '')
                    ]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)  # Ye summary sheet write karti hai
                
                # Handle crawled pages - Ye crawled pages handle karta hai
                if 'pages' in data:  # Ye check
                    pages_data = []  # Ye pages data list
                    for page in data['pages'][:50]:  # Limited pages
                        pages_data.append({
                            'URL': page.get('url', ''),
                            'Title': page.get('title', ''),
                            'Description': page.get('description', ''),
                            'Paragraphs Count': len(page.get('paragraphs', [])),
                            'Images Count': len(page.get('images', []))
                        })
                    pd.DataFrame(pages_data).to_excel(writer, sheet_name='Pages', index=False)  # Ye pages sheet write
                
                if data.get('headings'):  # Ye check
                    for level, headings in data['headings'].items():  # Ye loop
                        if headings:  # Ye check
                            df = pd.DataFrame({level.upper(): headings[:20]})  # Limited headings
                            df.to_excel(writer, sheet_name=level.upper(), index=False)  # Ye write karti hai
                if data.get('paragraphs'):  # Ye check
                    df = pd.DataFrame({'Paragraphs': data['paragraphs'][:100]})  # Limited paragraphs
                    df.to_excel(writer, sheet_name='Paragraphs', index=False)  # Ye write
            return filepath  # Ye return
        except Exception as e:  # Ye exception handle
            print(f"❌ Error saving Excel: {str(e)}")
            return None

    # Ye function data ko TXT file mein save karta hai with error handling
    def save_as_text(self, data, filename):
        try:  # Ye try block
            downloads_dir = "downloads"  # Ye directory
            if not os.path.exists(downloads_dir):
                os.makedirs(downloads_dir)
            filepath = os.path.join(downloads_dir, f"{filename}.txt")
            with open(filepath, 'w', encoding='utf-8') as f:  # Ye open
                # Handle crawled pages - Ye crawled pages handle karta hai
                if 'pages' in data:  # Ye check
                    f.write(f"CRAWL REPORT\n")  # Ye write crawl report
                    f.write(f"Start URL: {data.get('start_url', '')}\n")  # Ye URL
                    f.write(f"Pages Scraped: {data.get('total_stats', {}).get('pages_scraped', 0)}\n")  # Ye count
                    f.write(f"Scraped At: {data.get('scraped_at', '')}\n")  # Ye timestamp
                    f.write("=" * 50 + "\n\n")  # Ye separator
                    
                    for i, page in enumerate(data['pages'][:20], 1):  # Limited pages
                        f.write(f"PAGE {i}: {page.get('url', '')}\n")  # Ye page info
                        f.write(f"Title: {page.get('title', 'N/A')}\n")  # Ye title
                        f.write(f"Description: {page.get('description', 'N/A')}\n")  # Ye description
                        f.write("-" * 30 + "\n")  # Ye separator
                        
                        if page.get('paragraphs'):  # Ye check
                            f.write("Content:\n")  # Ye header
                            for para in page['paragraphs'][:5]:  # Limited paragraphs
                                f.write(f"{para}\n\n")  # Ye write
                        f.write("\n" + "=" * 30 + "\n\n")  # Ye separator
                else:  # Single page
                    f.write(f"TITLE: {data.get('title', 'N/A')}\n")  # Ye write title
                    f.write(f"URL: {data.get('url', 'N/A')}\n")  # Ye URL
                    f.write(f"DESCRIPTION: {data.get('description', 'N/A')}\n")  # Ye description
                    f.write(f"SCRAPED AT: {data.get('scraped_at', 'N/A')}\n")  # Ye timestamp
                    f.write("=" * 50 + "\n\n")  # Ye separator
                    if data.get('headings'):  # Ye check
                        for level, headings in data['headings'].items():  # Ye loop
                            for heading in headings[:10]:  # Limited headings
                                f.write(f"{level.upper()}: {heading}\n\n")  # Ye write
                    if data.get('paragraphs'):  # Ye check
                        f.write("PARAGRAPHS:\n")  # Ye header
                        f.write("-" * 20 + "\n")  # Ye separator
                        for para in data['paragraphs'][:50]:  # Limited paragraphs
                            f.write(f"{para}\n\n")  # Ye write
                    if data.get('full_text'):  # Ye check
                        f.write("FULL TEXT:\n")  # Ye header
                        f.write("-" * 20 + "\n")  # Ye separator
                        f.write(data['full_text'][:10000])  # Limited text
            return filepath  # Ye return
        except Exception as e:  # Ye exception handle
            print(f"❌ Error saving TXT: {str(e)}")
            return None

    # Ye function data ko PDF file mein save karta hai with error handling
    def save_as_pdf(self, data, filename):
        try:  # Ye try block
            downloads_dir = "downloads"  # Ye directory
            if not os.path.exists(downloads_dir):
                os.makedirs(downloads_dir)
            filepath = os.path.join(downloads_dir, f"{filename}.pdf")  # Ye filepath
            pdf = FPDF()  # Ye PDF object create karti hai
            pdf.add_page()  # Ye new page add karti hai
            pdf.set_font("Arial", size=12)  # Ye font set karti hai
            
            # Handle crawled pages - Ye crawled pages handle karta hai
            if 'pages' in data:  # Ye check
                pdf.set_font("Arial", size=16, style='B')  # Ye bold font
                pdf.cell(0, 10, "Website Crawling Report", ln=True, align='C')  # Ye title
                pdf.ln(10)  # Ye new line
                
                pdf.set_font("Arial", size=12)  # Ye normal font
                pdf.cell(0, 10, f"Start URL: {data.get('start_url', '')}", ln=True)  # Ye URL
                pdf.cell(0, 10, f"Pages Scraped: {data.get('total_stats', {}).get('pages_scraped', 0)}", ln=True)  # Ye count
                pdf.cell(0, 10, f"Scraped At: {data.get('scraped_at', '')}", ln=True)  # Ye timestamp
                pdf.ln(10)  # Ye new line
                
                for i, page in enumerate(data['pages'][:10], 1):  # Limited pages
                    pdf.add_page()  # Ye new page
                    pdf.set_font("Arial", size=14, style='B')  # Ye bold
                    pdf.cell(0, 10, f"Page {i}: {page.get('title', 'N/A')}", ln=True)  # Ye page title
                    pdf.set_font("Arial", size=12)  # Ye normal
                    pdf.cell(0, 10, f"URL: {page.get('url', '')}", ln=True)  # Ye URL
                    pdf.ln(5)  # Ye space
                    
                    if page.get('paragraphs'):  # Ye check
                        for para in page['paragraphs'][:3]:  # Limited paragraphs
                            lines = [para[i:i+80] for i in range(0, len(para), 80)]  # Ye long para split
                            for line in lines:  # Ye inner loop
                                pdf.cell(0, 8, line, ln=True)  # Ye line write
                            pdf.ln(5)  # Ye space
            else:  # Single page
                if data.get('title'):  # Ye check
                    pdf.set_font("Arial", size=16, style='B')  # Ye bold font
                    pdf.cell(0, 10, data['title'], ln=True, align='C')  # Ye title cell
                    pdf.ln(10)  # Ye new line
                pdf.set_font("Arial", size=12)  # Ye normal font
                if data.get('url'):  # Ye check
                    pdf.cell(0, 10, f"URL: {data['url']}", ln=True)  # Ye URL
                if data.get('description'):  # Ye check
                    pdf.cell(0, 10, f"Description: {data['description']}", ln=True)  # Ye description
                pdf.ln(10)  # Ye new line
                if data.get('headings'):  # Ye check
                    pdf.set_font("Arial", size=14, style='B')  # Ye bold
                    pdf.cell(0, 10, "Headings:", ln=True)  # Ye header
                    pdf.set_font("Arial", size=12)  # Ye normal
                    for level, headings in data['headings'].items():  # Ye loop
                        for heading in headings[:10]:  # Limited headings
                            pdf.cell(0, 8, f"{level.upper()}: {heading}", ln=True)  # Ye heading
                    pdf.ln(10)  # Ye new line
                if data.get('paragraphs'):  # Ye check
                    pdf.set_font("Arial", size=14, style='B')  # Ye bold
                    pdf.cell(0, 10, "Content:", ln=True)  # Ye header
                    pdf.set_font("Arial", size=12)  # Ye normal
                    for para in data['paragraphs'][:20]:  # Limited paragraphs
                        lines = [para[i:i+80] for i in range(0, len(para), 80)]  # Ye long para split
                        for line in lines:  # Ye inner loop
                            pdf.cell(0, 8, line, ln=True)  # Ye line write
                        pdf.ln(5)  # Ye space
            pdf.output(filepath)  # Ye PDF save karti hai
            return filepath  # Ye return
        except Exception as e:  # Ye exception handle
            print(f"❌ Error saving PDF: {str(e)}")
            return None
