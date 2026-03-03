import requests
import re
import time
import uuid
import csv
import os
import json
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag
from datetime import datetime
from fpdf import FPDF
import pandas as pd
from collections import deque
from typing import Dict, List, Set, Optional, Any
import threading
from queue import Queue
import hashlib

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class UltraScraper:
    """
    Ultra Professional Web Scraper - Full Website Crawling with BFS Algorithm
    Scrapes ALL products from entire website automatically
    """
    
    def __init__(self):
        """Initialize the scraper with session and settings"""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
        self.session.verify = False
        self.visited_urls: Set[str] = set()  # Store all visited URLs to avoid duplicates
        self.product_urls: Set[str] = set()   # Store all detected product URLs
        self.products_data: List[Dict] = []   # Store all extracted product data
        self.crawl_queue = deque()             # BFS queue for crawling
        self.domain = ""                        # Store domain for internal links
        self.start_time = None                   # Track start time for progress
        self.product_patterns = [                # Regex patterns to identify product URLs
            r'/product/',
            r'/products/',
            r'/item/',
            r'/items/',
            r'/p/',
            r'/pd/',
            r'/prod/',
            r'/shop/',
            r'/buy/',
            r'/details/',
            r'/view/',
            r'product\.php',
            r'item\.php',
            r'product-',
            r'item-',
            r'\?product=',
            r'\?item=',
            r'\-p-\d+',                         # Common pattern: -p-123
            r'\-prod-\d+',                       # -prod-123
            r'\/\d+\/\d+\/\d+\/',                 # Date patterns
            r'collections\/.*\/products\/',       # Shopify pattern
            r'\/products\/[a-z0-9-]+',            # Shopify products
        ]
        self.max_pages = 1000                     # Maximum pages to crawl (safety limit)
        self.crawled_count = 0                     # Count of crawled pages
        self.progress_callback = None               # Progress tracking callback

    # ---------- UTILITY FUNCTIONS ----------
    def clean_text(self, text: str) -> str:
        """Clean text by removing extra spaces and newlines"""
        if not text:
            return ""
        # Remove extra whitespace and normalize
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'\t+', ' ', text)
        return text.strip()

    def abs_url(self, url: str, base: str) -> str:
        """Convert relative URL to absolute URL"""
        if not url:
            return ""
        # Remove fragments (anchors) from URL
        url, _ = urldefrag(url)
        return urljoin(base, url)

    def is_same_domain(self, url: str, base: str) -> bool:
        """Check if URL belongs to same domain"""
        url_domain = urlparse(url).netloc
        base_domain = urlparse(base).netloc
        # Remove www. prefix for comparison
        url_domain = re.sub(r'^www\.', '', url_domain)
        base_domain = re.sub(r'^www\.', '', base_domain)
        return url_domain == base_domain or not url_domain

    def is_product_url(self, url: str) -> bool:
        """Detect if URL is a product page using multiple patterns"""
        url_lower = url.lower()
        
        # Check against all product patterns
        for pattern in self.product_patterns:
            if re.search(pattern, url_lower):
                return True
        
        # Additional checks for common e-commerce platforms
        if any(x in url_lower for x in ['product', 'item', 'p-', 'prod-', '/p/', '/products/']):
            return True
            
        # Check URL structure (often product URLs have numbers)
        if re.search(r'\/\d+\.html$', url_lower):  # Ends with /123.html
            return True
            
        return False

    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and should be crawled"""
        if not url or len(url) > 500:  # Skip very long URLs
            return False
            
        # Skip unwanted file types
        skip_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', 
                          '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip',
                          '.mp3', '.mp4', '.avi', '.css', '.js', '.json',
                          '.xml', '.rss', '.atom', '.webm', '.webp']
        
        url_lower = url.lower()
        for ext in skip_extensions:
            if ext in url_lower:
                return False
        
        # Skip common non-HTML pages
        skip_patterns = ['mailto:', 'tel:', 'javascript:', '#', '?', '&', 
                        'login', 'signup', 'register', 'cart', 'checkout',
                        'wishlist', 'account', 'profile', 'logout']
        
        for pattern in skip_patterns:
            if pattern in url_lower:
                return False
                
        return True

    def normalize_url(self, url: str) -> str:
        """Normalize URL to avoid duplicates"""
        # Remove fragments
        url, _ = urldefrag(url)
        
        # Remove trailing slash except for root
        if url.endswith('/') and not url.endswith('://'):
            url = url[:-1]
            
        # Remove common tracking parameters
        parsed = urlparse(url)
        query_params = parsed.query.split('&') if parsed.query else []
        
        # Keep only important parameters (like page, sort, filter)
        important_params = ['page', 'sort', 'order', 'dir', 'category', 'brand']
        filtered_params = []
        
        for param in query_params:
            param_name = param.split('=')[0].lower() if '=' in param else param
            if param_name in important_params:
                filtered_params.append(param)
        
        # Rebuild URL with important parameters
        new_query = '&'.join(filtered_params) if filtered_params else ''
        normalized = parsed._replace(query=new_query).geturl()
        
        return normalized

    # ---------- CRAWLING ENGINE (BFS ALGORITHM) ----------
    def crawl_website_bfs(self, start_url: str, max_pages: int = 500, progress_callback=None) -> Set[str]:
        """
        Crawl entire website using BFS (Breadth-First Search) algorithm
        Returns set of all discovered product URLs
        """
        print(f"🚀 Starting BFS crawl from: {start_url}")
        
        # Initialize crawling
        self.start_url = start_url
        self.domain = urlparse(start_url).netloc
        self.max_pages = max_pages
        self.progress_callback = progress_callback
        self.visited_urls = set()
        self.product_urls = set()
        self.crawl_queue = deque()
        self.crawled_count = 0
        
        # Normalize and add start URL to queue
        start_url_normalized = self.normalize_url(start_url)
        self.crawl_queue.append(start_url_normalized)
        
        # BFS main loop
        while self.crawl_queue and self.crawled_count < self.max_pages:
            # Get next URL from queue (FIFO - Breadth First)
            current_url = self.crawl_queue.popleft()
            
            # Skip if already visited
            if current_url in self.visited_urls:
                continue
                
            # Mark as visited
            self.visited_urls.add(current_url)
            self.crawled_count += 1
            
            # Progress update
            if self.progress_callback:
                self.progress_callback(self.crawled_count, len(self.product_urls))
            
            print(f"📄 Crawling ({self.crawled_count}/{self.max_pages}): {current_url[:100]}...")
            
            try:
                # Fetch and parse page
                response = self.fetch_page(current_url)
                if not response:
                    continue
                    
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Check if current page is a product page
                if self.is_product_url(current_url):
                    print(f"  🔍 Found PRODUCT page!")
                    self.product_urls.add(current_url)
                
                # Extract all links from page
                new_urls = self.extract_links_from_page(soup, current_url)
                
                # Add new URLs to queue (BFS - add to end)
                for url in new_urls:
                    if url not in self.visited_urls and url not in self.crawl_queue:
                        self.crawl_queue.append(url)
                
                # Small delay to be polite to server
                time.sleep(0.5)
                
            except Exception as e:
                print(f"  ❌ Error crawling {current_url}: {str(e)}")
                continue
        
        print(f"✅ BFS Crawl Complete!")
        print(f"   Total Pages Crawled: {len(self.visited_urls)}")
        print(f"   Total Products Found: {len(self.product_urls)}")
        
        return self.product_urls

    def fetch_page(self, url: str, retries: int = 3) -> Optional[requests.Response]:
        """Fetch page with retry logic"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=15, allow_redirects=True)
                response.raise_for_status()
                
                # Check if HTML content
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' not in content_type.lower():
                    print(f"  ⚠️ Not HTML: {content_type}")
                    return None
                    
                return response
                
            except requests.RequestException as e:
                if attempt == retries - 1:
                    print(f"  ❌ Failed after {retries} attempts: {e}")
                    return None
                print(f"  ⚠️ Retry {attempt + 1}/{retries}...")
                time.sleep(2 ** attempt)  # Exponential backoff
        
        return None

    def extract_links_from_page(self, soup: BeautifulSoup, base_url: str) -> Set[str]:
        """Extract all internal links from page"""
        links = set()
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue
            
            # Convert to absolute URL
            absolute_url = self.abs_url(href, base_url)
            
            # Check if same domain and valid
            if self.is_same_domain(absolute_url, base_url) and self.is_valid_url(absolute_url):
                normalized = self.normalize_url(absolute_url)
                links.add(normalized)
        
        return links

    # ---------- PRODUCT EXTRACTION ----------
    def extract_all_products(self) -> List[Dict]:
        """
        Extract product data from all discovered product URLs
        Returns list of all products with rich data
        """
        print(f"\n📦 Extracting products from {len(self.product_urls)} URLs...")
        
        self.products_data = []
        total_products = len(self.product_urls)
        
        for idx, product_url in enumerate(self.product_urls, 1):
            print(f"  📝 Extracting product {idx}/{total_products}: {product_url[:80]}...")
            
            try:
                # Fetch product page
                response = self.fetch_page(product_url)
                if not response:
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract rich product data
                product_data = self.extract_product_details(soup, product_url)
                
                if product_data:
                    self.products_data.append(product_data)
                    print(f"    ✅ Extracted: {product_data.get('name', 'Unknown')[:50]}")
                
                # Small delay to avoid rate limiting
                time.sleep(1)
                
            except Exception as e:
                print(f"    ❌ Error extracting product: {str(e)}")
                continue
        
        print(f"✅ Successfully extracted {len(self.products_data)} products!")
        return self.products_data

    def extract_product_details(self, soup: BeautifulSoup, url: str) -> Dict:
        """
        Extract rich product details from product page
        Uses multiple strategies to find product information
        """
        product = {
            'product_id': str(uuid.uuid4()),
            'url': url,
            'name': '',
            'price': '',
            'sale_price': '',
            'currency': 'USD',
            'description': '',
            'short_description': '',
            'images': [],
            'sku': '',
            'brand': '',
            'categories': [],
            'tags': [],
            'attributes': {},
            'reviews': {
                'rating': '',
                'count': '',
                'reviews_list': []
            },
            'availability': '',
            'stock_status': '',
            'extracted_at': datetime.now().isoformat()
        }
        
        # ----- EXTRACT PRODUCT NAME (Multiple strategies) -----
        # Strategy 1: Meta og:title
        meta_title = soup.find('meta', property='og:title')
        if meta_title and meta_title.get('content'):
            product['name'] = self.clean_text(meta_title['content'])
        
        # Strategy 2: Product title heading
        if not product['name']:
            title_tags = soup.find_all(['h1', 'h2'], class_=re.compile(r'product.*title|title.*product', re.I))
            for tag in title_tags:
                text = self.clean_text(tag.get_text())
                if text and len(text) > 5:
                    product['name'] = text
                    break
        
        # Strategy 3: Page title
        if not product['name'] and soup.title:
            title = self.clean_text(soup.title.string)
            # Clean up title (remove site name)
            title = re.sub(r'\s*[|\-–—]\s.*$', '', title)
            product['name'] = title
        
        # ----- EXTRACT PRICE (Multiple strategies) -----
        # Strategy 1: Meta product:price
        meta_price = soup.find('meta', property='product:price:amount')
        if meta_price and meta_price.get('content'):
            product['price'] = self.clean_text(meta_price['content'])
        
        # Strategy 2: Meta og:price
        if not product['price']:
            og_price = soup.find('meta', property='og:price:amount')
            if og_price and og_price.get('content'):
                product['price'] = self.clean_text(og_price['content'])
        
        # Strategy 3: Price selectors
        if not product['price']:
            price_selectors = [
                '.price', '.product-price', '.sale-price', '.regular-price',
                '[class*="price"]', '[itemprop="price"]', '.amount',
                'span.price', 'div.price', 'p.price', '.current-price'
            ]
            
            for selector in price_selectors:
                price_elem = soup.select_one(selector)
                if price_elem:
                    price_text = self.clean_text(price_elem.get_text())
                    # Extract numbers and dots/comma
                    price_match = re.search(r'[\d,]+(?:\.\d{2})?', price_text)
                    if price_match:
                        product['price'] = price_match.group()
                        break
        
        # Extract currency
        currency_elem = soup.find('meta', property='product:price:currency')
        if currency_elem and currency_elem.get('content'):
            product['currency'] = currency_elem['content']
        
        # ----- EXTRACT DESCRIPTION -----
        # Strategy 1: Meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            product['description'] = self.clean_text(meta_desc['content'])
        
        # Strategy 2: Product description div
        if not product['description']:
            desc_selectors = [
                '.description', '.product-description', '#description',
                '[class*="description"]', '[itemprop="description"]',
                'div.description', 'p.description', '.short-description'
            ]
            
            for selector in desc_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    product['description'] = self.clean_text(desc_elem.get_text())
                    if len(product['description']) > 50:
                        break
        
        # ----- EXTRACT IMAGES -----
        # Strategy 1: Meta og:image
        meta_image = soup.find('meta', property='og:image')
        if meta_image and meta_image.get('content'):
            product['images'].append(meta_image['content'])
        
        # Strategy 2: Product gallery images
        img_selectors = [
            '.product-image img', '.gallery img', '.product-gallery img',
            '[class*="product-img"]', '[class*="gallery-img"]',
            'img.product-image', 'img.main-image', 'img.primary-image'
        ]
        
        for selector in img_selectors:
            for img in soup.select(selector):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy')
                if src and src not in product['images']:
                    absolute_src = self.abs_url(src, url)
                    if absolute_src not in product['images']:
                        product['images'].append(absolute_src)
        
        # Limit images to 5
        product['images'] = product['images'][:5]
        
        # ----- EXTRACT SKU -----
        sku_selectors = [
            '.sku', '.product-sku', '[itemprop="sku"]',
            '.product-id', '.product-code', '.product-number'
        ]
        
        for selector in sku_selectors:
            sku_elem = soup.select_one(selector)
            if sku_elem:
                product['sku'] = self.clean_text(sku_elem.get_text())
                break
        
        # ----- EXTRACT BRAND -----
        brand_selectors = [
            '.brand', '.product-brand', '[itemprop="brand"]',
            '.manufacturer', '.product-manufacturer'
        ]
        
        for selector in brand_selectors:
            brand_elem = soup.select_one(selector)
            if brand_elem:
                product['brand'] = self.clean_text(brand_elem.get_text())
                break
        
        # ----- EXTRACT CATEGORIES -----
        category_selectors = [
            '.breadcrumb', '.breadcrumbs', '.product-categories',
            '.categories', '.product-category'
        ]
        
        for selector in category_selectors:
            cat_elem = soup.select_one(selector)
            if cat_elem:
                # Extract category links
                for link in cat_elem.find_all('a'):
                    cat_text = self.clean_text(link.get_text())
                    if cat_text and cat_text not in product['categories']:
                        product['categories'].append(cat_text)
                break
        
        # ----- EXTRACT RATING -----
        rating_selectors = [
            '.rating', '.product-rating', '.reviews-rating',
            '[itemprop="ratingValue"]', '.average-rating', '.star-rating'
        ]
        
        for selector in rating_selectors:
            rating_elem = soup.select_one(selector)
            if rating_elem:
                rating_text = self.clean_text(rating_elem.get_text())
                # Extract rating number
                rating_match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
                if rating_match:
                    product['reviews']['rating'] = rating_match.group()
                    break
        
        # ----- EXTRACT REVIEW COUNT -----
        count_selectors = [
            '.review-count', '.reviews-count', '[itemprop="reviewCount"]',
            '.rating-count', '.total-reviews'
        ]
        
        for selector in count_selectors:
            count_elem = soup.select_one(selector)
            if count_elem:
                count_text = self.clean_text(count_elem.get_text())
                count_match = re.search(r'(\d+)', count_text)
                if count_match:
                    product['reviews']['count'] = count_match.group()
                    break
        
        # ----- EXTRACT AVAILABILITY -----
        avail_selectors = [
            '.availability', '.stock', '.product-availability',
            '[itemprop="availability"]', '.in-stock', '.out-of-stock'
        ]
        
        for selector in avail_selectors:
            avail_elem = soup.select_one(selector)
            if avail_elem:
                product['availability'] = self.clean_text(avail_elem.get_text())
                # Determine stock status
                if 'in stock' in product['availability'].lower():
                    product['stock_status'] = 'in_stock'
                elif 'out of stock' in product['availability'].lower():
                    product['stock_status'] = 'out_of_stock'
                elif 'pre order' in product['availability'].lower():
                    product['stock_status'] = 'pre_order'
                break
        
        # Remove empty fields
        product = {k: v for k, v in product.items() if v not in ('', [], {}, None)}
        
        return product

    # ---------- MAIN SCRAPING FUNCTION ----------
    def scrape_full_website(self, start_url: str, max_pages: int = 500, progress_callback=None) -> Dict:
        """
        Main function to scrape entire website
        - Crawls website using BFS
        - Detects all product pages
        - Extracts all product data
        - Returns comprehensive results
        """
        self.start_time = time.time()
        
        print("=" * 60)
        print("🚀 ULTRA PROFESSIONAL WEBSITE SCRAPER")
        print("=" * 60)
        print(f"📌 Start URL: {start_url}")
        print(f"📌 Max Pages: {max_pages}")
        print("-" * 60)
        
        # Step 1: Crawl website using BFS to find all product URLs
        print("\n🔍 STEP 1: Crawling website (BFS Algorithm)...")
        product_urls = self.crawl_website_bfs(start_url, max_pages, progress_callback)
        
        # Step 2: Extract data from all product pages
        print("\n📦 STEP 2: Extracting product data...")
        products = self.extract_all_products()
        
        # Calculate statistics
        elapsed_time = round(time.time() - self.start_time, 2)
        
        # Step 3: Prepare final results
        result = {
            "scrape_id": str(uuid.uuid4()),
            "start_url": start_url,
            "domain": self.domain,
            "crawled_at": datetime.now().isoformat(),
            "crawl_time_seconds": elapsed_time,
            "statistics": {
                "total_pages_crawled": len(self.visited_urls),
                "total_product_urls_found": len(product_urls),
                "total_products_extracted": len(products),
                "extraction_success_rate": f"{round(len(products) / len(product_urls) * 100 if product_urls else 0, 1)}%",
                "pages_per_second": round(len(self.visited_urls) / elapsed_time, 2) if elapsed_time > 0 else 0
            },
            "products": products
        }
        
        print("\n" + "=" * 60)
        print("✅ SCRAPING COMPLETE!")
        print("=" * 60)
        print(f"📊 Statistics:")
        print(f"   • Total Pages Crawled: {result['statistics']['total_pages_crawled']}")
        print(f"   • Total Products Found: {result['statistics']['total_product_urls_found']}")
        print(f"   • Total Products Extracted: {result['statistics']['total_products_extracted']}")
        print(f"   • Success Rate: {result['statistics']['extraction_success_rate']}")
        print(f"   • Time Taken: {elapsed_time} seconds")
        print("=" * 60)
        
        return result

    # ---------- EXPORT FUNCTIONS (All formats) ----------
    def save_as_json(self, data: Dict, filename: str) -> str:
        """Save data as JSON file"""
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return filepath

    def save_as_csv(self, data: Dict, filename: str) -> str:
        """Save products as CSV file"""
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.csv")
        
        # Prepare CSV headers
        headers = ['Product ID', 'Name', 'Price', 'Currency', 'SKU', 'Brand', 
                  'Categories', 'Rating', 'Review Count', 'Stock Status', 
                  'Availability', 'URL', 'Description']
        
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            
            # Write each product
            for product in data.get('products', []):
                writer.writerow([
                    product.get('product_id', ''),
                    product.get('name', ''),
                    product.get('price', ''),
                    product.get('currency', ''),
                    product.get('sku', ''),
                    product.get('brand', ''),
                    ', '.join(product.get('categories', [])),
                    product.get('reviews', {}).get('rating', ''),
                    product.get('reviews', {}).get('count', ''),
                    product.get('stock_status', ''),
                    product.get('availability', ''),
                    product.get('url', ''),
                    product.get('description', '')[:500] + '...' if len(product.get('description', '')) > 500 else product.get('description', '')
                ])
        
        return filepath

    def save_as_excel(self, data: Dict, filename: str) -> str:
        """Save data as Excel file with multiple sheets"""
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.xlsx")
        
        # Create Excel file with multiple sheets
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Sheet 1: Summary
            summary_data = {
                'Property': ['Start URL', 'Domain', 'Crawl Date', 'Total Pages', 
                            'Total Products', 'Crawl Time (s)', 'Success Rate'],
                'Value': [
                    data.get('start_url', ''),
                    data.get('domain', ''),
                    data.get('crawled_at', ''),
                    data.get('statistics', {}).get('total_pages_crawled', 0),
                    data.get('statistics', {}).get('total_products_extracted', 0),
                    data.get('crawl_time_seconds', 0),
                    data.get('statistics', {}).get('extraction_success_rate', '0%')
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
            
            # Sheet 2: All Products
            if data.get('products'):
                products_flat = []
                for p in data['products']:
                    products_flat.append({
                        'Product ID': p.get('product_id', ''),
                        'Name': p.get('name', ''),
                        'Price': p.get('price', ''),
                        'Currency': p.get('currency', ''),
                        'SKU': p.get('sku', ''),
                        'Brand': p.get('brand', ''),
                        'Categories': ', '.join(p.get('categories', [])),
                        'Rating': p.get('reviews', {}).get('rating', ''),
                        'Review Count': p.get('reviews', {}).get('count', ''),
                        'Stock Status': p.get('stock_status', ''),
                        'Availability': p.get('availability', ''),
                        'URL': p.get('url', '')
                    })
                pd.DataFrame(products_flat).to_excel(writer, sheet_name='Products', index=False)
        
        return filepath

    def save_as_text(self, data: Dict, filename: str) -> str:
        """Save data as formatted text file"""
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.txt")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("ULTRA PROFESSIONAL WEB SCRAPER - FULL WEBSITE PRODUCTS\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("📊 SCRAPING SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"Start URL: {data.get('start_url', 'N/A')}\n")
            f.write(f"Domain: {data.get('domain', 'N/A')}\n")
            f.write(f"Crawl Date: {data.get('crawled_at', 'N/A')}\n")
            f.write(f"Total Pages Crawled: {data.get('statistics', {}).get('total_pages_crawled', 0)}\n")
            f.write(f"Total Products Found: {data.get('statistics', {}).get('total_product_urls_found', 0)}\n")
            f.write(f"Total Products Extracted: {data.get('statistics', {}).get('total_products_extracted', 0)}\n")
            f.write(f"Success Rate: {data.get('statistics', {}).get('extraction_success_rate', '0%')}\n")
            f.write(f"Time Taken: {data.get('crawl_time_seconds', 0)} seconds\n\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("📦 ALL EXTRACTED PRODUCTS\n")
            f.write("=" * 80 + "\n\n")
            
            for idx, product in enumerate(data.get('products', []), 1):
                f.write(f"PRODUCT #{idx}\n")
                f.write("-" * 40 + "\n")
                f.write(f"Name: {product.get('name', 'N/A')}\n")
                f.write(f"Price: {product.get('price', 'N/A')} {product.get('currency', '')}\n")
                f.write(f"SKU: {product.get('sku', 'N/A')}\n")
                f.write(f"Brand: {product.get('brand', 'N/A')}\n")
                f.write(f"Categories: {', '.join(product.get('categories', []))}\n")
                f.write(f"Rating: {product.get('reviews', {}).get('rating', 'N/A')} ({product.get('reviews', {}).get('count', '0')} reviews)\n")
                f.write(f"Availability: {product.get('availability', 'N/A')}\n")
                f.write(f"URL: {product.get('url', 'N/A')}\n")
                f.write(f"Description: {product.get('description', 'N/A')[:200]}...\n")
                f.write("-" * 40 + "\n\n")
        
        return filepath

    def save_as_pdf(self, data: Dict, filename: str) -> str:
        """Save data as PDF file"""
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.pdf")
        
        pdf = FPDF()
        pdf.add_page()
        
        # Title
        pdf.set_font("Arial", 'B', 20)
        pdf.cell(0, 15, "ULTRA PROFESSIONAL SCRAPER", ln=True, align='C')
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "Full Website Products Report", ln=True, align='C')
        pdf.ln(10)
        
        # Summary
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, "📊 SCRAPING SUMMARY", ln=True)
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 8, f"Start URL: {data.get('start_url', 'N/A')}", ln=True)
        pdf.cell(0, 8, f"Domain: {data.get('domain', 'N/A')}", ln=True)
        pdf.cell(0, 8, f"Crawl Date: {data.get('crawled_at', 'N/A')}", ln=True)
        pdf.cell(0, 8, f"Total Pages: {data.get('statistics', {}).get('total_pages_crawled', 0)}", ln=True)
        pdf.cell(0, 8, f"Total Products: {data.get('statistics', {}).get('total_products_extracted', 0)}", ln=True)
        pdf.cell(0, 8, f"Success Rate: {data.get('statistics', {}).get('extraction_success_rate', '0%')}", ln=True)
        pdf.cell(0, 8, f"Time: {data.get('crawl_time_seconds', 0)} seconds", ln=True)
        pdf.ln(10)
        
        # Products
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, "📦 EXTRACTED PRODUCTS", ln=True)
        pdf.ln(5)
        
        for idx, product in enumerate(data.get('products', [])[:20], 1):  # Limit to 20 products for PDF
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, f"Product #{idx}: {product.get('name', 'N/A')}", ln=True)
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 6, f"Price: {product.get('price', 'N/A')} {product.get('currency', '')}", ln=True)
            pdf.cell(0, 6, f"Brand: {product.get('brand', 'N/A')}", ln=True)
            pdf.cell(0, 6, f"SKU: {product.get('sku', 'N/A')}", ln=True)
            pdf.cell(0, 6, f"Categories: {', '.join(product.get('categories', []))[:50]}", ln=True)
            pdf.cell(0, 6, f"Rating: {product.get('reviews', {}).get('rating', 'N/A')}/5", ln=True)
            pdf.cell(0, 6, f"URL: {product.get('url', 'N/A')[:80]}...", ln=True)
            pdf.ln(5)
            
            # Check if we need a new page
            if pdf.get_y() > 250:
                pdf.add_page()
        
        pdf.output(filepath)
        return filepath


# ---------- PROGRESS TRACKING CALLBACK ----------
class ProgressTracker:
    """Helper class to track scraping progress"""
    
    def __init__(self):
        self.start_time = time.time()
        self.last_update = 0
        
    def update(self, crawled: int, products_found: int):
        """Update progress - called during crawling"""
        current_time = time.time()
        # Update every 2 seconds to avoid console spam
        if current_time - self.last_update > 2:
            elapsed = current_time - self.start_time
            rate = crawled / elapsed if elapsed > 0 else 0
            print(f"⏳ Progress: {crawled} pages crawled | {products_found} products found | {rate:.1f} pages/sec")
            self.last_update = current_time


# ---------- TEST FUNCTION ----------
def test_scraper():
    """Test the full website scraper"""
    scraper = UltraScraper()
    tracker = ProgressTracker()
    
    # Test with a sample e-commerce site
    result = scraper.scrape_full_website(
        start_url="https://books.toscrape.com",  # Test site
        max_pages=50,
        progress_callback=tracker.update
    )
    
    # Save results
    scraper.save_as_json(result, f"full_website_{int(time.time())}")
    scraper.save_as_csv(result, f"full_website_{int(time.time())}")
    
    return result


if __name__ == "__main__":
    test_scraper()