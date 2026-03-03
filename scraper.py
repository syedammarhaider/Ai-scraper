
import requests, re, time, uuid, csv, os, json, urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
from fpdf import FPDF
import pandas as pd

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class UltraScraper:

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self.session.verify = False

    # ---------- UTILS ----------
    def clean(self, text):
        return re.sub(r"\s+", " ", text).strip() if text else ""

    def abs_url(self, url, base):
        return urljoin(base, url)

    def remove_empty(self, data):
        return {k: v for k, v in data.items() if v not in ("", None, [], {})}

    # ---------- SCRAPER ----------
    def scrape_website(self, url, mode="comprehensive"):
        start = time.time()
        try:
            if not url.startswith("http"):
                url = "https://" + url

            r = self.session.get(url, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            # Remove scripts/styles
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            # Metadata
            title = self.clean(soup.title.string) if soup.title else ""
            description = ""
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                description = self.clean(meta_desc.get("content"))

            # Headings
            headings = {f"h{i}": [self.clean(h.get_text()) for h in soup.find_all(f"h{i}")]
                        for i in range(1, 7)}

            # Paragraphs
            paragraphs = [self.clean(p.get_text()) for p in soup.find_all("p") if len(p.get_text()) > 30]

            # Structured data: tables + lists + Google Sheets
            structured_data = self.extract_structured_data(soup, url)

            # Images
            images = [{"url": self.abs_url(img.get("src"), url), "alt": self.clean(img.get("alt"))}
                      for img in soup.find_all("img") if img.get("src")]

            # Links
            domain = urlparse(url).netloc
            internal_links, external_links = [], []
            for a in soup.find_all("a", href=True):
                link = self.abs_url(a["href"], url)
                text = self.clean(a.get_text())
                if urlparse(link).netloc == domain:
                    internal_links.append({"url": link, "text": text})
                else:
                    external_links.append({"url": link, "text": text})

            # Full readable text
            full_text = self.generate_professional_text(soup, structured_data, url)

            # Compose final JSON based on mode
            if mode == "basic":
                # Basic mode - minimal data
                data = {
                    "scrape_id": str(uuid.uuid4()),
                    "url": url,
                    "title": title,
                    "description": description,
                    "paragraphs": paragraphs[:5],  # Only first 5 paragraphs
                    "stats": {
                        "paragraph_count": len(paragraphs[:5]),
                        "scrape_time": round(time.time() - start, 2)
                    },
                    "scraped_at": datetime.now().isoformat()
                }
            elif mode == "smart":
                # Smart mode - moderate data
                data = {
                    "scrape_id": str(uuid.uuid4()),
                    "url": url,
                    "title": title,
                    "description": description,
                    "headings": {k: v[:3] for k, v in headings.items()},  # Limit headings
                    "paragraphs": paragraphs[:10],  # First 10 paragraphs
                    "images": images[:5],  # First 5 images
                    "stats": {
                        "paragraph_count": len(paragraphs[:10]),
                        "image_count": len(images[:5]),
                        "scrape_time": round(time.time() - start, 2)
                    },
                    "scraped_at": datetime.now().isoformat()
                }
            else:
                # Comprehensive mode - all data
                data = {
                    "scrape_id": str(uuid.uuid4()),
                    "url": url,
                    "title": title,
                    "description": description,
                    "headings": headings,
                    "paragraphs": paragraphs,
                    "structured_data": structured_data,
                    "images": images,
                    "internal_links": internal_links,
                    "external_links": external_links,
                    "full_text": full_text,
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

            return self.remove_empty(data)

        except Exception as e:
            return {"error": str(e)}

    # ---------- STRUCTURED DATA ----------
    def extract_structured_data(self, soup, url):
        structured_data = {"tables": [], "lists": []}

        # Tables
        for table in soup.find_all("table"):
            t = self.extract_table_data(table)
            if t:
                structured_data["tables"].append(t)

        # Lists
        for list_tag in soup.find_all(["ul", "ol"]):
            l = self.extract_list_data(list_tag)
            if l:
                structured_data["lists"].append(l)

        # Google Sheets (optional)
        if "docs.google.com/spreadsheets" in url:
            sheets = self.extract_google_sheets_data(soup)
            if sheets:
                structured_data["tables"].extend(sheets)

        return structured_data

    def extract_table_data(self, table):
        headers, rows = [], []
        header_row = table.find("tr")
        if header_row:
            headers = [self.clean(th.get_text()) for th in header_row.find_all(["th", "td"])]
        for tr in table.find_all("tr")[1:]:
            row = [self.clean(td.get_text()) for td in tr.find_all("td")]
            if any(row):
                rows.append(row)
        if headers or rows:
            return {"headers": headers, "rows": rows,
                    "row_count": len(rows), "column_count": len(headers) if headers else (len(rows[0]) if rows else 0)}
        return None

    def extract_list_data(self, list_tag):
        items = [self.clean(li.get_text()) for li in list_tag.find_all("li") if self.clean(li.get_text())]
        if items:
            return {"type": list_tag.name, "items": items, "item_count": len(items)}
        return None

    def extract_google_sheets_data(self, soup):
        tables = []
        for table in soup.find_all("table"):
            t = self.extract_table_data(table)
            if t:
                t["source"] = "google_sheets"
                tables.append(t)
        return tables

    # ---------- PROFESSIONAL TEXT ----------
    def generate_professional_text(self, soup, structured_data, base_url=""):
        parts = []

        # Title
        if soup.title:
            parts.append(f"# TITLE: {self.clean(soup.title.string)}\n")

        # Headings
        for i in range(1, 7):
            for h in soup.find_all(f"h{i}"):
                parts.append(f"{'#' * i} {self.clean(h.get_text())}")

        # Tables
        if structured_data.get("tables"):
            parts.append("\n## TABLES")
            for idx, table in enumerate(structured_data["tables"], 1):
                parts.append(f"\n### Table {idx}")
                if table.get("headers"):
                    parts.append(" | ".join(table["headers"]))
                    parts.append("-" * (len(" | ".join(table["headers"]))))
                for row in table.get("rows", []):
                    parts.append(" | ".join(str(cell) for cell in row))

        # Lists
        if structured_data.get("lists"):
            parts.append("\n## LISTS")
            for lst in structured_data["lists"]:
                parts.append(f"\n### {lst['type'].upper()} LIST")
                for item in lst["items"]:
                    parts.append(f"- {item}")

        # Paragraphs
        for p in soup.find_all("p"):
            text = self.clean(p.get_text())
            if len(text) > 30:
                parts.append(f"\n{text}")

        # Images URLs
        if soup.find_all("img"):
            parts.append("\n## IMAGES")
            for img in soup.find_all("img"):
                src = img.get("src")
                if src:
                    parts.append(f"- {self.abs_url(src, base_url)}")

        # Links URLs
        parts.append("\n## LINKS")
        domain = urlparse(base_url).netloc
        for a in soup.find_all("a", href=True):
            link = self.abs_url(a["href"], base_url)
            parts.append(f"- {link}")

        return "\n".join(parts).strip()

    # ---------- EXPORT METHODS ----------
    def save_as_json(self, data, filename):
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return filepath

    def save_as_csv(self, data, filename):
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.csv")
        
        # Extract relevant data for CSV
        csv_data = []
        
        # Add basic info
        if data.get('title'):
            csv_data.append(['Type', 'Content'])
            csv_data.append(['Title', data['title']])
        
        # Add headings
        if data.get('headings'):
            for level, headings in data['headings'].items():
                for heading in headings:
                    csv_data.append([level.upper(), heading])
        
        # Add paragraphs
        if data.get('paragraphs'):
            for para in data['paragraphs']:
                csv_data.append(['Paragraph', para])
        
        # Write to CSV
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)
        
        return filepath

    def save_as_excel(self, data, filename):
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.xlsx")
        
        # Create Excel workbook
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Summary sheet
            summary_data = {
                'Property': ['URL', 'Title', 'Description', 'Scraped At'],
                'Value': [
                    data.get('url', ''),
                    data.get('title', ''),
                    data.get('description', ''),
                    data.get('scraped_at', '')
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
            
            # Headings sheet
            if data.get('headings'):
                for level, headings in data['headings'].items():
                    if headings:
                        df = pd.DataFrame({level.upper(): headings})
                        df.to_excel(writer, sheet_name=level.upper(), index=False)
            
            # Paragraphs sheet
            if data.get('paragraphs'):
                df = pd.DataFrame({'Paragraphs': data['paragraphs']})
                df.to_excel(writer, sheet_name='Paragraphs', index=False)
        
        return filepath

    def save_as_text(self, data, filename):
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.txt")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"TITLE: {data.get('title', 'N/A')}\n")
            f.write(f"URL: {data.get('url', 'N/A')}\n")
            f.write(f"DESCRIPTION: {data.get('description', 'N/A')}\n")
            f.write(f"SCRAPED AT: {data.get('scraped_at', 'N/A')}\n")
            f.write("=" * 50 + "\n\n")
            
            # Add headings
            if data.get('headings'):
                for level, headings in data['headings'].items():
                    for heading in headings:
                        f.write(f"{level.upper()}: {heading}\n\n")
            
            # Add paragraphs
            if data.get('paragraphs'):
                f.write("PARAGRAPHS:\n")
                f.write("-" * 20 + "\n")
                for para in data['paragraphs']:
                    f.write(f"{para}\n\n")
            
            # Add full text if available
            if data.get('full_text'):
                f.write("FULL TEXT:\n")
                f.write("-" * 20 + "\n")
                f.write(data['full_text'])
        
        return filepath

    def save_as_pdf(self, data, filename):
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.pdf")
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        # Title
        if data.get('title'):
            pdf.set_font("Arial", size=16, style='B')
            pdf.cell(0, 10, data['title'], ln=True, align='C')
            pdf.ln(10)
        
        # URL and description
        pdf.set_font("Arial", size=12)
        if data.get('url'):
            pdf.cell(0, 10, f"URL: {data['url']}", ln=True)
        if data.get('description'):
            pdf.cell(0, 10, f"Description: {data['description']}", ln=True)
        pdf.ln(10)
        
        # Headings
        if data.get('headings'):
            pdf.set_font("Arial", size=14, style='B')
            pdf.cell(0, 10, "Headings:", ln=True)
            pdf.set_font("Arial", size=12)
            for level, headings in data['headings'].items():
                for heading in headings:
                    pdf.cell(0, 8, f"{level.upper()}: {heading}", ln=True)
            pdf.ln(10)
        
        # Paragraphs
        if data.get('paragraphs'):
            pdf.set_font("Arial", size=14, style='B')
            pdf.cell(0, 10, "Content:", ln=True)
            pdf.set_font("Arial", size=12)
            for para in data['paragraphs']:
                # Handle long paragraphs by splitting them
                lines = [para[i:i+80] for i in range(0, len(para), 80)]
                for line in lines:
                    pdf.cell(0, 8, line, ln=True)
                pdf.ln(5)
        
        pdf.output(filepath)
        return filepath