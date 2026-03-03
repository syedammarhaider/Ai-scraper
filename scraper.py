"""
ULTRA FAST SCRAPER - 100% WORKING
No errors | Blazing fast | Production ready
Author: AMMAR HAIDER
"""

import requests
import re
import time
import uuid
import csv
import os
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
from fpdf import FPDF
import pandas as pd
from collections import deque
import hashlib
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UltraScraper:
    """ULTRA FAST Website Scraper & Crawler"""
    
    def __init__(self):
        """Initialize with fast settings"""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        })
        self.session.verify = False  # Fast mode - skip SSL verification
        
        # Create downloads directory
        self.downloads_dir = "downloads"
        os.makedirs(self.downloads_dir, exist_ok=True)
        
        # Stats
        self.crawl_stats = {"pages": 0, "products": 0, "start": None, "end": None}
        
        logger.info("✅ UltraScraper initialized")

    # ========== FAST CRAWLER ==========
    def crawl_website(self, start_url, max_pages=50, delay=0.2):
        """FAST website crawler - Limited pages for speed"""
        self.crawl_stats = {
            "pages_crawled": 0,
            "products_found": 0,
            "start_time": datetime.now().isoformat(),
            "status": "running"
        }
        
        visited = set()
        queue = deque([start_url])
        all_products = []
        product_urls = set()
        
        base_domain = urlparse(start_url).netloc
        
        logger.info(f"🚀 Starting FAST crawl: {start_url}")
        
        while queue and len(visited) < max_pages:
            url = queue.popleft()
            
            if url in visited:
                continue
                
            visited.add(url)
            self.crawl_stats["pages_crawled"] = len(visited)
            
            try:
                # FAST fetch - timeout 5 seconds
                response = self.session.get(url, timeout=5)
                if response.status_code != 200:
                    continue
                    
                soup = BeautifulSoup(response.text, "html.parser")
                
                # FAST product detection
                page_products = self.extract_products_fast(soup, url)
                
                for product in page_products:
                    # Simple duplicate check
                    if product.get('url') not in product_urls:
                        product_urls.add(product.get('url', ''))
                        all_products.append(product)
                        self.crawl_stats["products_found"] = len(all_products)
                
                # Find more links (limit for speed)
                if len(visited) < max_pages:
                    for a in soup.find_all('a', href=True)[:20]:  # Limit links per page
                        href = a['href']
                        if href.startswith('/') or href.startswith(start_url):
                            full_url = urljoin(url, href)
                            if base_domain in full_url and full_url not in visited:
                                queue.append(full_url)
                
                time.sleep(delay)  # Small delay
                
            except Exception as e:
                logger.debug(f"Skipping {url}: {str(e)}")
                continue
        
        self.crawl_stats["end_time"] = datetime.now().isoformat()
        self.crawl_stats["status"] = "completed"
        
        logger.info(f"✅ Crawl complete: {len(all_products)} products from {len(visited)} pages")
        
        return {
            "crawl_stats": self.crawl_stats,
            "products": all_products,
            "product_count": len(all_products),
            "pages": list(visited)[:100],  # Limited for speed
            "start_url": start_url
        }
    
    # ========== FAST PRODUCT EXTRACTION ==========
    def extract_products_fast(self, soup, url):
        """Extract products FAST - minimal processing"""
        products = []
        
        # Method 1: Look for common product containers (FAST)
        containers = soup.find_all(['div', 'li', 'article'], class_=re.compile(r'product|item|card', re.I))
        
        for container in containers[:20]:  # Limit per page for speed
            product = {}
            
            # Get name - FAST
            name_elem = container.find(['h2', 'h3', 'h4', 'strong'])
            if name_elem:
                product['name'] = self.clean_text(name_elem.get_text())[:100]
            
            # Get price - FAST
            price_elem = container.find(class_=re.compile(r'price|cost|sale', re.I))
            if price_elem:
                product['price'] = self.clean_text(price_elem.get_text())[:50]
            
            # Get link - FAST
            link = container.find('a', href=True)
            if link:
                product['url'] = urljoin(url, link['href'])
            
            # Get image - FAST
            img = container.find('img')
            if img and img.get('src'):
                product['image'] = urljoin(url, img['src'])
            
            if product.get('name') or product.get('price'):
                products.append(product)
        
        # If no containers found, check if page itself is product
        if not products:
            product = {}
            
            # Title as name
            title = soup.find('h1')
            if title:
                product['name'] = self.clean_text(title.get_text())[:100]
            
            # Find price
            price = soup.find(class_=re.compile(r'price|cost', re.I))
            if price:
                product['price'] = self.clean_text(price.get_text())[:50]
            
            if product.get('name') or product.get('price'):
                product['url'] = url
                products.append(product)
        
        return products[:10]  # Max 10 products per page for speed
    
    # ========== FAST SINGLE PAGE SCRAPE ==========
    def scrape_website_fast(self, url):
        """Scrape single page - ULTRA FAST"""
        start = time.time()
        
        try:
            response = self.session.get(url, timeout=5)
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remove scripts for speed
            for tag in soup(["script", "style"]):
                tag.decompose()
            
            # Get basic data FAST
            data = {
                "url": url,
                "title": self.clean_text(soup.title.string) if soup.title else "",
                "text": self.clean_text(soup.get_text())[:5000],  # Limit text
                "products": self.extract_products_fast(soup, url),
                "time": round(time.time() - start, 2)
            }
            
            return data
            
        except Exception as e:
            return {"error": str(e)}
    
    # ========== HELPER FUNCTIONS ==========
    def clean_text(self, text):
        """Clean text FAST"""
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text).strip()
    
    # ========== EXPORT FUNCTIONS ==========
    def save_as_json(self, data, filename):
        """Save as JSON"""
        path = os.path.join(self.downloads_dir, f"{filename}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return path
    
    def save_as_csv(self, data, filename):
        """Save as CSV"""
        path = os.path.join(self.downloads_dir, f"{filename}.csv")
        
        rows = []
        if isinstance(data, dict) and data.get('products'):
            for p in data['products']:
                rows.append([p.get('name', ''), p.get('price', ''), p.get('url', '')])
        
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Name', 'Price', 'URL'])
            writer.writerows(rows)
        
        return path
    
    def save_as_excel(self, data, filename):
        """Save as Excel"""
        path = os.path.join(self.downloads_dir, f"{filename}.xlsx")
        
        rows = []
        if isinstance(data, dict) and data.get('products'):
            for p in data['products']:
                rows.append({'Name': p.get('name', ''), 'Price': p.get('price', ''), 'URL': p.get('url', '')})
        
        df = pd.DataFrame(rows)
        df.to_excel(path, index=False)
        
        return path
    
    def save_as_text(self, data, filename):
        """Save as Text"""
        path = os.path.join(self.downloads_dir, f"{filename}.txt")
        
        with open(path, 'w', encoding='utf-8') as f:
            if isinstance(data, dict) and data.get('products'):
                f.write(f"Products Found: {len(data['products'])}\n\n")
                for i, p in enumerate(data['products'], 1):
                    f.write(f"{i}. {p.get('name', 'N/A')} - {p.get('price', 'N/A')}\n")
        
        return path
    
    def save_as_pdf(self, data, filename):
        """Save as PDF - SIMPLE VERSION"""
        path = os.path.join(self.downloads_dir, f"{filename}.pdf")
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        if isinstance(data, dict) and data.get('products'):
            pdf.cell(0, 10, f"Products: {len(data['products'])}", ln=True)
            pdf.ln(5)
            
            for i, p in enumerate(data['products'][:20], 1):  # Limit for PDF
                pdf.cell(0, 8, f"{i}. {p.get('name', 'N/A')[:50]}", ln=True)
                if p.get('price'):
                    pdf.cell(0, 8, f"   Price: {p['price']}", ln=True)
        
        pdf.output(path)
        return path
    
    def save_as_markdown(self, data, filename):
        """Save as Markdown"""
        path = os.path.join(self.downloads_dir, f"{filename}.md")
        
        with open(path, 'w', encoding='utf-8') as f:
            if isinstance(data, dict) and data.get('products'):
                f.write(f"# Crawl Results\n\n")
                f.write(f"**Products Found:** {len(data['products'])}\n\n")
                
                for i, p in enumerate(data['products'], 1):
                    f.write(f"## Product {i}\n")
                    f.write(f"- **Name:** {p.get('name', 'N/A')}\n")
                    f.write(f"- **Price:** {p.get('price', 'N/A')}\n")
                    if p.get('url'):
                        f.write(f"- **URL:** {p['url']}\n")
                    f.write("\n")
        
        return path
    
    # Legacy method for compatibility
    def scrape_website(self, url, mode="fast"):
        """Compatibility method"""
        return self.scrape_website_fast(url)