# Updated scraper.py with Full Website Crawling using BFS Algorithm
# Har line ke upar Roman Urdu mein comment added hai ke ye line kya karti hai
# Is code mein robust error handling with retries add kiya gaya hai using requests Session with HTTPAdapter
# Full site crawling: Starting URL se shuru kar ke internal links ko BFS se crawl karega, max_pages limit ke sath to infinite na ho
# Products: Assuming e-commerce site, all pages scrape kar ke aggregate data collect karega (paragraphs, headings, etc. from all pages)
# Agar specific product pattern chahiye to further customize kar sakte hain, but general whole site scraping implemented

import requests, re, time, uuid, csv, os, json, urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
from fpdf import FPDF
import pandas as pd
from collections import deque  # Ye import BFS ke liye queue use karne ke liye hai
from requests.adapters import HTTPAdapter  # Ye import retry mechanism ke liye hai
from requests.packages.urllib3.util.retry import Retry  # Ye import retry strategy ke liye hai

# Disable SSL warnings - Ye line SSL warnings ko disable karti hai taake insecure requests mein warnings na aayein
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class UltraScraper:
    # Ye init function class ko initialize karta hai, session banata hai with retries
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
    # Ye function single page ko scrape karta hai (existing logic, ab crawl mein use hoga)
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

            # Headings - Ye block all headings (h1 to h6) collect karta hai
            headings = {f"h{i}": [self.clean(h.get_text()) for h in soup.find_all(f"h{i}")]
                        for i in range(1, 7)}  # Ye comprehension headings dictionary banati hai

            # Paragraphs - Ye block paragraphs collect karta hai (min 30 chars)
            paragraphs = [self.clean(p.get_text()) for p in soup.find_all("p") if len(p.get_text()) > 30]  # Ye list comprehension paragraphs filter karti hai

            # Structured data: tables + lists + Google Sheets - Ye line structured data extract karti hai
            structured_data = self.extract_structured_data(soup, url)  # Ye function call karti hai structured data ke liye

            # Images - Ye block images collect karta hai
            images = [{"url": self.abs_url(img.get("src"), url), "alt": self.clean(img.get("alt"))}
                      for img in soup.find_all("img") if img.get("src")]  # Ye comprehension images list banati hai

            # Links - Ye block internal aur external links separate karta hai
            domain = urlparse(url).netloc  # Ye line domain extract karti hai
            internal_links, external_links = [], []  # Ye line lists initialize karti hai
            for a in soup.find_all("a", href=True):  # Ye loop all anchors par iterate karta hai
                link = self.abs_url(a["href"], url)  # Ye line absolute link banati hai
                text = self.clean(a.get_text())  # Ye line link text clean karti hai
                if urlparse(link).netloc == domain:  # Ye check karti hai internal link hai ya nahi
                    internal_links.append({"url": link, "text": text})  # Ye internal link add karti hai
                else:
                    external_links.append({"url": link, "text": text})  # Ye external link add karti hai

            # Full readable text - Ye line professional text generate karti hai
            full_text = self.generate_professional_text(soup, structured_data, url)  # Ye function call karti hai text ke liye

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

            return self.remove_empty(data)  # Ye line empty values remove karti hai aur return karti hai

        except Exception as e:  # Ye block error handle karta hai
            return {"error": str(e)}  # Ye error message return karti hai

    # ---------- FULL WEBSITE CRAWLER USING BFS ----------
    # Ye new function pori site ko crawl karta hai using BFS (queue-based), all products/pages scrape karega
    def crawl_website(self, start_url, mode="comprehensive", max_pages=50, max_depth=3):
        aggregate_data = {"pages": [], "total_stats": {"pages_scraped": 0, "total_paragraphs": 0}}  # Ye aggregated data initialize karti hai
        visited = set()  # Ye set visited URLs track karta hai to duplicates avoid kare
        queue = deque([(start_url, 0)])  # Ye queue BFS ke liye initialize karti hai with (url, depth)
        domain = urlparse(start_url).netloc  # Ye domain extract karti hai to internal links check kare

        while queue and len(aggregate_data["pages"]) < max_pages:  # Ye loop queue empty na ho aur max pages na exceed ho
            current_url, depth = queue.popleft()  # Ye line queue se next URL nikalti hai
            if current_url in visited or depth > max_depth:  # Ye check karti hai visited hai ya depth exceed
                continue  # Ye skip karti hai agar condition true

            visited.add(current_url)  # Ye URL ko visited set mein add karti hai
            page_data = self.scrape_single_page(current_url, mode)  # Ye single page scrape karti hai
            if "error" not in page_data:  # Ye check karti hai error nahi hai
                aggregate_data["pages"].append(page_data)  # Ye page data aggregate mein add karti hai
                aggregate_data["total_stats"]["pages_scraped"] += 1  # Ye pages count increase karti hai
                aggregate_data["total_stats"]["total_paragraphs"] += page_data["stats"].get("paragraph_count", 0)  # Ye total paragraphs add karti hai

                # Find internal links to enqueue - Ye block new internal links find karta hai
                for link in page_data.get("internal_links", []):  # Ye loop internal links par iterate karta hai
                    next_url = link["url"]  # Ye next URL extract karti hai
                    if next_url not in visited and urlparse(next_url).netloc == domain:  # Ye check karti hai not visited and same domain
                        queue.append((next_url, depth + 1))  # Ye queue mein add karti hai with increased depth

        aggregate_data["scrape_id"] = str(uuid.uuid4())  # Ye unique ID add karti hai
        aggregate_data["start_url"] = start_url  # Ye start URL add karti hai
        aggregate_data["scraped_at"] = datetime.now().isoformat()  # Ye timestamp add karti hai
        return aggregate_data  # Ye final aggregated data return karti hai

    # ---------- STRUCTURED DATA ----------
    # Ye function structured data (tables, lists) extract karta hai
    def extract_structured_data(self, soup, url):
        structured_data = {"tables": [], "lists": []}  # Ye dictionary initialize karti hai

        # Tables - Ye block all tables extract karta hai
        for table in soup.find_all("table"):  # Ye loop tables par iterate karta hai
            t = self.extract_table_data(table)  # Ye table data extract karti hai
            if t:  # Ye check karti hai data mila hai
                structured_data["tables"].append(t)  # Ye append karti hai

        # Lists - Ye block all lists extract karta hai
        for list_tag in soup.find_all(["ul", "ol"]):  # Ye loop ul/ol par iterate karta hai
            l = self.extract_list_data(list_tag)  # Ye list data extract karti hai
            if l:  # Ye check karti hai data mila hai
                structured_data["lists"].append(l)  # Ye append karti hai

        # Google Sheets (optional) - Ye block agar Google Sheets hai to extract karta hai
        if "docs.google.com/spreadsheets" in url:  # Ye check karti hai URL mein sheets hai
            sheets = self.extract_google_sheets_data(soup)  # Ye sheets data extract karti hai
            if sheets:  # Ye check karti hai data mila hai
                structured_data["tables"].extend(sheets)  # Ye extend karti hai

        return structured_data  # Ye structured data return karti hai

    # Ye function single table se data extract karta hai
    def extract_table_data(self, table):
        headers, rows = [], []  # Ye lists initialize karti hai
        header_row = table.find("tr")  # Ye first row find karti hai
        if header_row:  # Ye check karti hai row mila hai
            headers = [self.clean(th.get_text()) for th in header_row.find_all(["th", "td"])]  # Ye headers collect karti hai
        for tr in table.find_all("tr")[1:]:  # Ye loop remaining rows par iterate karta hai
            row = [self.clean(td.get_text()) for td in tr.find_all("td")]  # Ye row data collect karti hai
            if any(row):  # Ye check karti hai row empty nahi hai
                rows.append(row)  # Ye append karti hai
        if headers or rows:  # Ye check karti hai data mila hai
            return {"headers": headers, "rows": rows,  # Ye dictionary return karti hai
                    "row_count": len(rows), "column_count": len(headers) if headers else (len(rows[0]) if rows else 0)}
        return None  # Ye None return karti hai agar data nahi

    # Ye function single list se data extract karta hai
    def extract_list_data(self, list_tag):
        items = [self.clean(li.get_text()) for li in list_tag.find_all("li") if self.clean(li.get_text())]  # Ye items collect karti hai
        if items:  # Ye check karti hai items mile hain
            return {"type": list_tag.name, "items": items, "item_count": len(items)}  # Ye dictionary return karti hai
        return None  # Ye None return karti hai

    # Ye function Google Sheets se data extract karta hai
    def extract_google_sheets_data(self, soup):
        tables = []  # Ye list initialize karti hai
        for table in soup.find_all("table"):  # Ye loop tables par iterate karta hai
            t = self.extract_table_data(table)  # Ye table data extract karti hai
            if t:  # Ye check karti hai data mila hai
                t["source"] = "google_sheets"  # Ye source add karti hai
                tables.append(t)  # Ye append karti hai
        return tables  # Ye tables return karti hai

    # ---------- PROFESSIONAL TEXT ----------
    # Ye function readable text generate karta hai from soup
    def generate_professional_text(self, soup, structured_data, base_url=""):
        parts = []  # Ye list initialize karti hai for text parts

        # Title - Ye block title add karta hai
        if soup.title:  # Ye check karti hai title mila hai
            parts.append(f"# TITLE: {self.clean(soup.title.string)}\n")  # Ye title append karti hai

        # Headings - Ye block all headings add karta hai
        for i in range(1, 7):  # Ye loop h1 to h6 par iterate karta hai
            for h in soup.find_all(f"h{i}"):  # Ye inner loop headings find karti hai
                parts.append(f"{'#' * i} {self.clean(h.get_text())}")  # Ye heading append karti hai

        # Tables - Ye block tables add karta hai
        if structured_data.get("tables"):  # Ye check karti hai tables hain
            parts.append("\n## TABLES")  # Ye header append karti hai
            for idx, table in enumerate(structured_data["tables"], 1):  # Ye loop tables par iterate karta hai
                parts.append(f"\n### Table {idx}")  # Ye table number append karti hai
                if table.get("headers"):  # Ye check karti hai headers hain
                    parts.append(" | ".join(table["headers"]))  # Ye headers append karti hai
                    parts.append("-" * (len(" | ".join(table["headers"]))))  # Ye separator append karti hai
                for row in table.get("rows", []):  # Ye loop rows par iterate karta hai
                    parts.append(" | ".join(str(cell) for cell in row))  # Ye row append karti hai

        # Lists - Ye block lists add karta hai
        if structured_data.get("lists"):  # Ye check karti hai lists hain
            parts.append("\n## LISTS")  # Ye header append karti hai
            for lst in structured_data["lists"]:  # Ye loop lists par iterate karta hai
                parts.append(f"\n### {lst['type'].upper()} LIST")  # Ye list type append karti hai
                for item in lst["items"]:  # Ye inner loop items par iterate karta hai
                    parts.append(f"- {item}")  # Ye item append karti hai

        # Paragraphs - Ye block paragraphs add karta hai
        for p in soup.find_all("p"):  # Ye loop paragraphs par iterate karta hai
            text = self.clean(p.get_text())  # Ye text clean karti hai
            if len(text) > 30:  # Ye check karti hai length >30
                parts.append(f"\n{text}")  # Ye paragraph append karti hai

        # Images URLs - Ye block images add karta hai
        if soup.find_all("img"):  # Ye check karti hai images hain
            parts.append("\n## IMAGES")  # Ye header append karti hai
            for img in soup.find_all("img"):  # Ye loop images par iterate karta hai
                src = img.get("src")  # Ye src extract karti hai
                if src:  # Ye check karti hai src mila hai
                    parts.append(f"- {self.abs_url(src, base_url)}")  # Ye image URL append karti hai

        # Links URLs - Ye block links add karta hai
        parts.append("\n## LINKS")  # Ye header append karti hai
        domain = urlparse(base_url).netloc  # Ye domain extract karti hai
        for a in soup.find_all("a", href=True):  # Ye loop anchors par iterate karta hai
            link = self.abs_url(a["href"], base_url)  # Ye absolute link banati hai
            parts.append(f"- {link}")  # Ye link append karti hai

        return "\n".join(parts).strip()  # Ye all parts join karti hai aur return karti hai

    # ---------- EXPORT METHODS ----------
    # Ye function data ko JSON file mein save karta hai
    def save_as_json(self, data, filename):
        downloads_dir = "downloads"  # Ye directory name set karti hai
        if not os.path.exists(downloads_dir):  # Ye check karti hai directory exists nahi
            os.makedirs(downloads_dir)  # Ye directory create karti hai
        filepath = os.path.join(downloads_dir, f"{filename}.json")  # Ye filepath banati hai
        with open(filepath, 'w', encoding='utf-8') as f:  # Ye file open karti hai write mode mein
            json.dump(data, f, indent=2, ensure_ascii=False)  # Ye data JSON mein dump karti hai
        return filepath  # Ye filepath return karti hai

    # Ye function data ko CSV file mein save karta hai
    def save_as_csv(self, data, filename):
        downloads_dir = "downloads"  # Ye directory name set karti hai
        if not os.path.exists(downloads_dir):  # Ye check karti hai
            os.makedirs(downloads_dir)  # Ye create karti hai
        filepath = os.path.join(downloads_dir, f"{filename}.csv")  # Ye filepath banati hai
        csv_data = []  # Ye list initialize karti hai
        if data.get('title'):  # Ye check karti hai title hai
            csv_data.append(['Type', 'Content'])  # Ye header add karti hai
            csv_data.append(['Title', data['title']])  # Ye title add karti hai
        if data.get('headings'):  # Ye check karti hai headings hain
            for level, headings in data['headings'].items():  # Ye loop headings par
                for heading in headings:  # Ye inner loop
                    csv_data.append([level.upper(), heading])  # Ye add karti hai
        if data.get('paragraphs'):  # Ye check karti hai paragraphs hain
            for para in data['paragraphs']:  # Ye loop
                csv_data.append(['Paragraph', para])  # Ye add karti hai
        with open(filepath, 'w', newline='', encoding='utf-8') as f:  # Ye file open karti hai
            writer = csv.writer(f)  # Ye CSV writer create karti hai
            writer.writerows(csv_data)  # Ye rows write karti hai
        return filepath  # Ye return karti hai

    # Ye function data ko Excel file mein save karta hai
    def save_as_excel(self, data, filename):
        downloads_dir = "downloads"  # Ye directory set karti hai
        if not os.path.exists(downloads_dir):  # Ye check
            os.makedirs(downloads_dir)  # Ye create
        filepath = os.path.join(downloads_dir, f"{filename}.xlsx")  # Ye filepath
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:  # Ye Excel writer open karti hai
            summary_data = {  # Ye summary data banati hai
                'Property': ['URL', 'Title', 'Description', 'Scraped At'],
                'Value': [
                    data.get('url', ''),
                    data.get('title', ''),
                    data.get('description', ''),
                    data.get('scraped_at', '')
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)  # Ye summary sheet write karti hai
            if data.get('headings'):  # Ye check
                for level, headings in data['headings'].items():  # Ye loop
                    if headings:  # Ye check
                        df = pd.DataFrame({level.upper(): headings})  # Ye DataFrame banati hai
                        df.to_excel(writer, sheet_name=level.upper(), index=False)  # Ye write karti hai
            if data.get('paragraphs'):  # Ye check
                df = pd.DataFrame({'Paragraphs': data['paragraphs']})  # Ye DataFrame
                df.to_excel(writer, sheet_name='Paragraphs', index=False)  # Ye write
        return filepath  # Ye return

    # Ye function data ko TXT file mein save karta hai
    def save_as_text(self, data, filename):
        downloads_dir = "downloads"  # Ye directory
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        filepath = os.path.join(downloads_dir, f"{filename}.txt")
        with open(filepath, 'w', encoding='utf-8') as f:  # Ye open
            f.write(f"TITLE: {data.get('title', 'N/A')}\n")  # Ye write title
            f.write(f"URL: {data.get('url', 'N/A')}\n")  # Ye URL
            f.write(f"DESCRIPTION: {data.get('description', 'N/A')}\n")  # Ye description
            f.write(f"SCRAPED AT: {data.get('scraped_at', 'N/A')}\n")  # Ye timestamp
            f.write("=" * 50 + "\n\n")  # Ye separator
            if data.get('headings'):  # Ye check
                for level, headings in data['headings'].items():  # Ye loop
                    for heading in headings:  # Ye inner
                        f.write(f"{level.upper()}: {heading}\n\n")  # Ye write
            if data.get('paragraphs'):  # Ye check
                f.write("PARAGRAPHS:\n")  # Ye header
                f.write("-" * 20 + "\n")  # Ye separator
                for para in data['paragraphs']:  # Ye loop
                    f.write(f"{para}\n\n")  # Ye write
            if data.get('full_text'):  # Ye check
                f.write("FULL TEXT:\n")  # Ye header
                f.write("-" * 20 + "\n")  # Ye separator
                f.write(data['full_text'])  # Ye full text
        return filepath  # Ye return

    # Ye function data ko PDF file mein save karta hai
    def save_as_pdf(self, data, filename):
        downloads_dir = "downloads"  # Ye directory
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        filepath = os.path.join(downloads_dir, f"{filename}.pdf")  # Ye filepath
        pdf = FPDF()  # Ye PDF object create karti hai
        pdf.add_page()  # Ye new page add karti hai
        pdf.set_font("Arial", size=12)  # Ye font set karti hai
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
                for heading in headings:  # Ye inner
                    pdf.cell(0, 8, f"{level.upper()}: {heading}", ln=True)  # Ye heading
            pdf.ln(10)  # Ye new line
        if data.get('paragraphs'):  # Ye check
            pdf.set_font("Arial", size=14, style='B')  # Ye bold
            pdf.cell(0, 10, "Content:", ln=True)  # Ye header
            pdf.set_font("Arial", size=12)  # Ye normal
            for para in data['paragraphs']:  # Ye loop
                lines = [para[i:i+80] for i in range(0, len(para), 80)]  # Ye long para split karti hai
                for line in lines:  # Ye inner loop
                    pdf.cell(0, 8, line, ln=True)  # Ye line write
                pdf.ln(5)  # Ye space
        pdf.output(filepath)  # Ye PDF save karti hai
        return filepath  # Ye return