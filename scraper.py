# scraper.py - Ultra Professional Web Scraper
# Yeh complete website scraper hai jo poori site ki saari pages/products scrape karta hai

import requests  # HTTP requests for fetching web pages
import re  # Regular expressions for text cleaning
import time  # Time functions for delays and timestamps
import uuid  # Generate unique IDs
import csv  # CSV file handling
import os  # Operating system functions
import json  # JSON handling
import urllib3  # HTTP connection pooling
from bs4 import BeautifulSoup  # HTML parsing
from urllib.parse import urljoin, urlparse  # URL manipulation
from datetime import datetime  # Date and time
from fpdf import FPDF  # PDF generation
from collections import deque  # Double-ended queue for BFS
from concurrent.futures import ThreadPoolExecutor  # Multi-threading
import pandas as pd  # Data analysis and Excel

# Disable SSL warnings (for sites with invalid certificates)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class UltraScraper:
    """Ultra Professional Web Scraper - Full Site Scraping Capability"""
    
    def __init__(self):
        """Initialize the scraper with session and headers"""
        # Create a persistent session for cookies and connection reuse
        self.session = requests.Session()
        # Browser-like headers to avoid blocking
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        })
        # Disable SSL verification for problematic sites
        self.session.verify = False
        
        # Create downloads directory if it doesn't exist
        self.downloads_dir = "downloads"
        if not os.path.exists(self.downloads_dir):
            os.makedirs(self.downloads_dir)
        
        # Track visited URLs to avoid duplicates
        self.visited_urls = set()
        # Store all scraped data
        self.all_scraped_data = []
        # Store products data
        self.all_products = []
        
    # ========== UTILITY FUNCTIONS ==========
    
    def clean(self, text):
        """Clean text by removing extra whitespace"""
        # Remove extra spaces, newlines, tabs
        return re.sub(r"\s+", " ", text).strip() if text else ""

    def abs_url(self, url, base):
        """Convert relative URL to absolute URL"""
        # Join base URL with relative path
        return urljoin(base, url)

    def remove_empty(self, data):
        """Remove empty values from dictionary"""
        # Filter out empty strings, None, empty lists/dicts
        return {k: v for k, v in data.items() if v not in ("", None, [], {})}
    
    def is_valid_url(self, url, base_domain):
        """Check if URL belongs to same domain"""
        try:
            # Parse URL and get domain
            parsed = urlparse(url)
            domain = parsed.netloc
            # Check if domain matches base domain
            return domain == base_domain or domain.endswith('.' + base_domain)
        except:
            return False
    
    def extract_domain(self, url):
        """Extract domain from URL"""
        parsed = urlparse(url)
        return parsed.netloc

    # ========== PRODUCT DETECTION ==========
    
    def is_product_page(self, url, soup=None):
        """Detect if URL/page is a product page"""
        # Check URL patterns for products
        url_lower = url.lower()
        product_patterns = [
            '/product/', '/products/', '/item/', '/items/', '/p/', 
            '/prod/', '/shop/', '/buy/', '/product-detail/', '/product-details/',
            '?product=', '&product=', '/dp/', '/gp/product/', '/itm/',
            '/catalog/', '/collection/', '/collections/'
        ]
        
        # Check URL for product patterns
        for pattern in product_patterns:
            if pattern in url_lower:
                return True
        
        # If soup provided, check HTML for product indicators
        if soup:
            # Check for common product page elements
            product_indicators = [
                soup.find('form', attrs={'action': re.compile(r'cart|add-to-cart|buy', re.I)}),
                soup.find('button', text=re.compile(r'add to cart|buy now|purchase', re.I)),
                soup.find('input', attrs={'name': re.compile(r'add-to-cart|product_id|variation', re.I)}),
                soup.find('div', class_=re.compile(r'product|item', re.I)),
                soup.find('meta', attrs={'property': 'og:type', 'content': 'product'}),
                soup.find('meta', attrs={'name': 'twitter:card', 'content': 'product'})
            ]
            
            if any(product_indicators):
                return True
        
        return False
    
    def extract_products(self, soup, url):
        """Extract product information from page"""
        products = []
        
        # Method 1: Look for structured product data (JSON-LD)
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    # Single product
                    if data.get('@type') in ['Product', 'Item']:
                        product = self.extract_product_from_jsonld(data, url)
                        if product:
                            products.append(product)
                    # Multiple products in graph
                    elif data.get('@graph'):
                        for item in data['@graph']:
                            if item.get('@type') in ['Product', 'Item']:
                                product = self.extract_product_from_jsonld(item, url)
                                if product:
                                    products.append(product)
                elif isinstance(data, list):
                    for item in data:
                        if item.get('@type') in ['Product', 'Item']:
                            product = self.extract_product_from_jsonld(item, url)
                            if product:
                                products.append(product)
            except:
                pass
        
        # Method 2: Look for product listings in HTML
        product_elements = soup.find_all(['div', 'li', 'article'], 
                                         class_=re.compile(r'product|item|card', re.I))
        
        for elem in product_elements[:20]:  # Limit to first 20 per page
            product = self.extract_product_from_html(elem, url)
            if product:
                products.append(product)
        
        return products
    
    def extract_product_from_jsonld(self, data, base_url):
        """Extract product from JSON-LD structured data"""
        try:
            product = {
                'name': data.get('name', ''),
                'description': data.get('description', ''),
                'price': data.get('offers', {}).get('price', '') if isinstance(data.get('offers'), dict) else '',
                'currency': data.get('offers', {}).get('priceCurrency', '') if isinstance(data.get('offers'), dict) else '',
                'url': self.abs_url(data.get('url', ''), base_url) if data.get('url') else base_url,
                'image': self.abs_url(data.get('image', ''), base_url) if data.get('image') else '',
                'sku': data.get('sku', ''),
                'brand': data.get('brand', {}).get('name', '') if isinstance(data.get('brand'), dict) else '',
                'availability': data.get('offers', {}).get('availability', '') if isinstance(data.get('offers'), dict) else '',
                'rating': data.get('aggregateRating', {}).get('ratingValue', '') if data.get('aggregateRating') else '',
                'review_count': data.get('aggregateRating', {}).get('reviewCount', '') if data.get('aggregateRating') else ''
            }
            # Remove empty fields
            return self.remove_empty(product)
        except:
            return None
    
    def extract_product_from_html(self, element, base_url):
        """Extract product from HTML element"""
        try:
            product = {}
            
            # Get product name
            name_elem = element.find(['h2', 'h3', 'h4', 'div'], 
                                     class_=re.compile(r'title|name|heading|product-title', re.I))
            if name_elem:
                product['name'] = self.clean(name_elem.get_text())
            
            # Get product link
            link_elem = element.find('a', href=True)
            if link_elem:
                product['url'] = self.abs_url(link_elem['href'], base_url)
            
            # Get price
            price_elem = element.find(class_=re.compile(r'price|amount|cost|sale', re.I))
            if price_elem:
                price_text = self.clean(price_elem.get_text())
                # Extract numbers from price text
                price_match = re.search(r'[\d,]+(?:\.\d{2})?', price_text)
                if price_match:
                    product['price'] = price_match.group().replace(',', '')
            
            # Get image
            img_elem = element.find('img')
            if img_elem and img_elem.get('src'):
                product['image'] = self.abs_url(img_elem['src'], base_url)
            
            # Get description/summary
            desc_elem = element.find(['p', 'div'], 
                                     class_=re.compile(r'desc|summary|excerpt', re.I))
            if desc_elem:
                product['description'] = self.clean(desc_elem.get_text())[:200]  # Limit length
            
            # Return only if we have at least name or url
            if product.get('name') or product.get('url'):
                return self.remove_empty(product)
            
            return None
        except:
            return None

    # ========== FULL WEBSITE SCRAPER ==========
    
    def scrape_full_website(self, start_url, max_pages=100, mode="comprehensive"):
        """Scrape entire website using BFS approach"""
        start_time = time.time()
        
        # Reset tracking
        self.visited_urls = set()
        self.all_scraped_data = []
        self.all_products = []
        
        # Queue for BFS
        url_queue = deque([start_url])
        
        # Get base domain
        base_domain = self.extract_domain(start_url)
        
        print(f"🚀 Starting full site scrape of: {base_domain}")
        print(f"📊 Max pages: {max_pages}")
        
        # Counter for pages scraped
        pages_scraped = 0
        
        # BFS loop
        while url_queue and pages_scraped < max_pages:
            # Get next URL from queue
            current_url = url_queue.popleft()
            
            # Skip if already visited
            if current_url in self.visited_urls:
                continue
            
            print(f"📄 Scraping page {pages_scraped + 1}: {current_url}")
            
            try:
                # Fetch page
                response = self.session.get(current_url, timeout=30)
                response.raise_for_status()
                
                # Parse HTML
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Remove scripts and styles
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()
                
                # Mark as visited
                self.visited_urls.add(current_url)
                pages_scraped += 1
                
                # Scrape current page data
                page_data = self.scrape_page_data(soup, current_url, mode)
                self.all_scraped_data.append(page_data)
                
                # Check if this is a product page
                if self.is_product_page(current_url, soup):
                    # Extract products from this page
                    products = self.extract_products(soup, current_url)
                    for product in products:
                        product['source_url'] = current_url
                        product['scraped_at'] = datetime.now().isoformat()
                        self.all_products.append(product)
                    
                    if products:
                        print(f"   ✅ Found {len(products)} products on this page")
                
                # Find all links on page for further scraping
                for link in soup.find_all('a', href=True):
                    # Get absolute URL
                    next_url = self.abs_url(link['href'], current_url)
                    
                    # Check if valid and same domain
                    if self.is_valid_url(next_url, base_domain):
                        # Avoid duplicates and fragments
                        parsed = urlparse(next_url)
                        clean_url = parsed._replace(fragment='').geturl()
                        
                        # Skip common non-page URLs
                        skip_patterns = ['.jpg', '.jpeg', '.png', '.gif', '.pdf', '.zip', 
                                        '.css', '.js', 'mailto:', 'tel:', '#', 'javascript:']
                        
                        if not any(pattern in clean_url.lower() for pattern in skip_patterns):
                            if clean_url not in self.visited_urls:
                                url_queue.append(clean_url)
                
                # Small delay to be polite
                time.sleep(0.1)
                
            except Exception as e:
                print(f"   ❌ Error scraping {current_url}: {str(e)}")
                self.visited_urls.add(current_url)  # Mark as visited anyway
                continue
        
        # Prepare final result
        result = {
            "scrape_id": str(uuid.uuid4()),
            "start_url": start_url,
            "domain": base_domain,
            "scraped_at": datetime.now().isoformat(),
            "scrape_time_seconds": round(time.time() - start_time, 2),
            "stats": {
                "pages_scraped": pages_scraped,
                "total_pages_found": len(self.visited_urls),
                "total_products": len(self.all_products),
                "queue_remaining": len(url_queue)
            },
            "pages": self.all_scraped_data,
            "products": self.all_products
        }
        
        return self.remove_empty(result)
    
    def scrape_page_data(self, soup, url, mode="comprehensive"):
        """Scrape data from a single page"""
        
        # Get title
        title = self.clean(soup.title.string) if soup.title else ""
        
        # Get meta description
        description = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            description = self.clean(meta_desc.get("content", ""))
        
        # Get headings
        headings = {}
        for i in range(1, 7):
            h_tags = soup.find_all(f"h{i}")
            if h_tags:
                headings[f"h{i}"] = [self.clean(h.get_text()) for h in h_tags if self.clean(h.get_text())]
        
        # Get paragraphs
        paragraphs = []
        for p in soup.find_all("p"):
            text = self.clean(p.get_text())
            if len(text) > 20:  # Only meaningful paragraphs
                paragraphs.append(text)
        
        # Get images
        images = []
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                images.append({
                    "url": self.abs_url(src, url),
                    "alt": self.clean(img.get("alt", "")),
                    "title": self.clean(img.get("title", ""))
                })
        
        # Prepare page data based on mode
        if mode == "basic":
            data = {
                "url": url,
                "title": title,
                "paragraphs": paragraphs[:5],
                "stats": {
                    "paragraph_count": len(paragraphs[:5]),
                    "image_count": len(images[:5])
                }
            }
        elif mode == "smart":
            data = {
                "url": url,
                "title": title,
                "description": description,
                "headings": {k: v[:3] for k, v in headings.items()},
                "paragraphs": paragraphs[:10],
                "images": images[:5],
                "stats": {
                    "paragraph_count": len(paragraphs[:10]),
                    "image_count": len(images[:5])
                }
            }
        else:  # comprehensive
            data = {
                "url": url,
                "title": title,
                "description": description,
                "headings": headings,
                "paragraphs": paragraphs,
                "images": images,
                "stats": {
                    "paragraph_count": len(paragraphs),
                    "image_count": len(images)
                }
            }
        
        return self.remove_empty(data)

    # ========== SINGLE PAGE SCRAPER ==========
    
    def scrape_website(self, url, mode="comprehensive"):
        """Scrape single website (backward compatibility)"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remove scripts/styles
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            
            # Use page scraper
            data = self.scrape_page_data(soup, url, mode)
            
            # Add metadata
            data["scrape_id"] = str(uuid.uuid4())
            data["scraped_at"] = datetime.now().isoformat()
            
            # Check for products
            if self.is_product_page(url, soup):
                products = self.extract_products(soup, url)
                if products:
                    data["products"] = products
                    data["product_count"] = len(products)
            
            return self.remove_empty(data)
            
        except Exception as e:
            return {"error": str(e)}

    # ========== EXPORT FUNCTIONS ==========
    
    def save_as_json(self, data, filename):
        """Save data as JSON file"""
        filepath = os.path.join(self.downloads_dir, f"{filename}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return filepath
    
    def save_as_csv(self, data, filename):
        """Save data as CSV file"""
        filepath = os.path.join(self.downloads_dir, f"{filename}.csv")
        
        # Prepare CSV data
        csv_rows = []
        
        # Handle full site data
        if isinstance(data, dict) and "products" in data:
            # Product data
            for product in data.get("products", []):
                row = {
                    "Product Name": product.get("name", ""),
                    "Price": product.get("price", ""),
                    "URL": product.get("url", ""),
                    "Image": product.get("image", ""),
                    "Description": product.get("description", ""),
                    "Source Page": product.get("source_url", "")
                }
                csv_rows.append(row)
            
            # Page data summary
            for page in data.get("pages", []):
                row = {
                    "Page URL": page.get("url", ""),
                    "Title": page.get("title", ""),
                    "Paragraphs": len(page.get("paragraphs", [])),
                    "Images": len(page.get("images", []))
                }
                csv_rows.append(row)
        
        # Handle single page data
        elif isinstance(data, dict):
            # Try to extract as product
            if data.get("products"):
                for product in data["products"]:
                    row = {
                        "Product Name": product.get("name", ""),
                        "Price": product.get("price", ""),
                        "URL": product.get("url", ""),
                        "Image": product.get("image", ""),
                        "Description": product.get("description", "")
                    }
                    csv_rows.append(row)
            
            # Page metadata
            row = {
                "Page URL": data.get("url", ""),
                "Title": data.get("title", ""),
                "Description": data.get("description", ""),
                "Paragraphs": len(data.get("paragraphs", [])),
                "Images": len(data.get("images", []))
            }
            csv_rows.append(row)
        
        # Write CSV
        if csv_rows:
            df = pd.DataFrame(csv_rows)
            df.to_csv(filepath, index=False, encoding='utf-8')
        else:
            # Fallback - create simple CSV
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Data"])
                writer.writerow([json.dumps(data)[:1000]])
        
        return filepath
    
    def save_as_excel(self, data, filename):
        """Save data as Excel file"""
        filepath = os.path.join(self.downloads_dir, f"{filename}.xlsx")
        
        # Create Excel writer
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            
            # Products sheet
            if isinstance(data, dict) and "products" in data and data["products"]:
                products_df = pd.DataFrame(data["products"])
                products_df.to_excel(writer, sheet_name="Products", index=False)
            
            # Pages sheet
            if isinstance(data, dict) and "pages" in data and data["pages"]:
                pages_data = []
                for page in data["pages"]:
                    pages_data.append({
                        "URL": page.get("url", ""),
                        "Title": page.get("title", ""),
                        "Paragraphs": len(page.get("paragraphs", [])),
                        "Images": len(page.get("images", []))
                    })
                if pages_data:
                    pages_df = pd.DataFrame(pages_data)
                    pages_df.to_excel(writer, sheet_name="Pages", index=False)
            
            # Summary sheet
            summary_data = {
                "Property": ["Start URL", "Domain", "Scraped At", "Pages Scraped", "Total Products"],
                "Value": [
                    data.get("start_url", ""),
                    data.get("domain", ""),
                    data.get("scraped_at", ""),
                    str(data.get("stats", {}).get("pages_scraped", 0)),
                    str(data.get("stats", {}).get("total_products", 0))
                ]
            }
            if isinstance(data, dict):
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name="Summary", index=False)
        
        return filepath
    
    def save_as_text(self, data, filename):
        """Save data as text file"""
        filepath = os.path.join(self.downloads_dir, f"{filename}.txt")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            
            # Write header
            f.write("=" * 80 + "\n")
            f.write("AI SCRAPER - EXTRACTED DATA\n")
            f.write("=" * 80 + "\n\n")
            
            # Handle full site data
            if isinstance(data, dict):
                if "start_url" in data:
                    f.write(f"START URL: {data['start_url']}\n")
                    f.write(f"DOMAIN: {data.get('domain', '')}\n")
                    f.write(f"SCRAPED AT: {data.get('scraped_at', '')}\n")
                    f.write(f"PAGES SCRAPED: {data.get('stats', {}).get('pages_scraped', 0)}\n")
                    f.write(f"TOTAL PRODUCTS: {data.get('stats', {}).get('total_products', 0)}\n")
                    f.write("\n" + "=" * 80 + "\n\n")
                
                # Products section
                if "products" in data and data["products"]:
                    f.write("PRODUCTS FOUND:\n")
                    f.write("-" * 40 + "\n")
                    for i, product in enumerate(data["products"], 1):
                        f.write(f"\nProduct #{i}:\n")
                        for key, value in product.items():
                            if value:
                                f.write(f"  {key.upper()}: {value}\n")
                    f.write("\n" + "=" * 80 + "\n\n")
                
                # Pages section
                if "pages" in data and data["pages"]:
                    f.write("PAGES SCRAPED:\n")
                    f.write("-" * 40 + "\n")
                    for i, page in enumerate(data["pages"], 1):
                        f.write(f"\nPage #{i}: {page.get('url', '')}\n")
                        f.write(f"  Title: {page.get('title', '')}\n")
                        if page.get("paragraphs"):
                            f.write(f"  Paragraphs: {len(page['paragraphs'])}\n")
                        if page.get("images"):
                            f.write(f"  Images: {len(page['images'])}\n")
            
            # Handle single page data
            elif isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, (list, dict)):
                        f.write(f"\n{key.upper()}:\n")
                        f.write("-" * 20 + "\n")
                        if isinstance(value, list):
                            for item in value[:10]:  # Limit to 10 items
                                if isinstance(item, dict):
                                    for k, v in item.items():
                                        f.write(f"  {k}: {v}\n")
                                    f.write("\n")
                                else:
                                    f.write(f"  {item}\n")
                        else:
                            json.dump(value, f, indent=2)
                    else:
                        f.write(f"{key}: {value}\n")
        
        return filepath
    
    def save_as_pdf(self, data, filename):
        """Save data as PDF file"""
        filepath = os.path.join(self.downloads_dir, f"{filename}.pdf")
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Title
        pdf.set_font("Arial", style='B', size=16)
        pdf.cell(0, 10, "AI SCRAPER - EXTRACTED DATA", ln=True, align='C')
        pdf.ln(10)
        
        pdf.set_font("Arial", size=12)
        
        # Handle full site data
        if isinstance(data, dict):
            if "start_url" in data:
                pdf.set_font("Arial", style='B', size=14)
                pdf.cell(0, 10, "SITE SUMMARY", ln=True)
                pdf.set_font("Arial", size=12)
                pdf.cell(0, 8, f"Start URL: {data['start_url']}", ln=True)
                pdf.cell(0, 8, f"Domain: {data.get('domain', '')}", ln=True)
                pdf.cell(0, 8, f"Pages Scraped: {data.get('stats', {}).get('pages_scraped', 0)}", ln=True)
                pdf.cell(0, 8, f"Products Found: {data.get('stats', {}).get('total_products', 0)}", ln=True)
                pdf.ln(10)
            
            # Products
            if "products" in data and data["products"]:
                pdf.set_font("Arial", style='B', size=14)
                pdf.cell(0, 10, f"PRODUCTS ({len(data['products'])})", ln=True)
                pdf.set_font("Arial", size=12)
                
                for i, product in enumerate(data["products"][:20], 1):  # Limit to 20 products
                    pdf.set_font("Arial", style='B', size=12)
                    pdf.cell(0, 8, f"Product #{i}: {product.get('name', 'N/A')}", ln=True)
                    pdf.set_font("Arial", size=11)
                    
                    if product.get('price'):
                        pdf.cell(0, 6, f"  Price: {product['price']}", ln=True)
                    if product.get('url'):
                        pdf.cell(0, 6, f"  URL: {product['url'][:50]}...", ln=True)
                    
                    pdf.ln(5)
        
        pdf.output(filepath)
        return filepath
    
    def save_as_markdown(self, data, filename):
        """Save data as Markdown file"""
        filepath = os.path.join(self.downloads_dir, f"{filename}.md")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            
            f.write("# AI SCRAPER - EXTRACTED DATA\n\n")
            
            if isinstance(data, dict):
                if "start_url" in data:
                    f.write("## Site Summary\n\n")
                    f.write(f"- **Start URL:** {data['start_url']}\n")
                    f.write(f"- **Domain:** {data.get('domain', '')}\n")
                    f.write(f"- **Scraped At:** {data.get('scraped_at', '')}\n")
                    f.write(f"- **Pages Scraped:** {data.get('stats', {}).get('pages_scraped', 0)}\n")
                    f.write(f"- **Products Found:** {data.get('stats', {}).get('total_products', 0)}\n\n")
                
                if "products" in data and data["products"]:
                    f.write(f"## Products ({len(data['products'])})\n\n")
                    for i, product in enumerate(data["products"], 1):
                        f.write(f"### Product #{i}: {product.get('name', 'N/A')}\n\n")
                        for key, value in product.items():
                            if value and key != 'name':
                                f.write(f"- **{key.title()}:** {value}\n")
                        f.write("\n")
        
        return filepath