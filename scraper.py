"""
ULTRA PROFESSIONAL WEBSITE CRAWLER & SCRAPER
Complete solution for crawling entire websites and extracting all products.
Uses BFS algorithm, automatic product detection, and multi-format export.

Author: AMMAR HAIDER
Version: 5.0 - Enterprise Edition with Full Site Crawling
"""

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
import hashlib
import logging

# Disable SSL warnings for simplicity (in production, use proper certificates)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UltraScraper:
    """
    Enterprise-grade web scraper with full website crawling capabilities.
    
    Features:
    - BFS algorithm for complete website crawling
    - Automatic product page detection
    - Multi-product extraction from all pages
    - Smart URL prioritization (product pages first)
    - Duplicate detection and removal
    - Pagination handling
    - Rich product data extraction
    - Progress tracking
    - Multiple export formats
    - Robust error handling with retries
    """
    
    def __init__(self):
        """Initialize the scraper with session and configuration"""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        })
        self.session.verify = False  # Skip SSL verification (use with caution)
        
        # Store for crawled URLs to avoid duplicates
        self.visited_urls: Set[str] = set()
        self.url_queue: deque = deque()
        
        # Product storage
        self.all_products: List[Dict] = []
        self.product_urls: Set[str] = set()
        
        # Progress tracking
        self.crawl_stats = {
            "pages_crawled": 0,
            "products_found": 0,
            "start_time": None,
            "end_time": None,
            "status": "idle"
        }
        
        # Create downloads directory if it doesn't exist
        self.downloads_dir = "downloads"
        if not os.path.exists(self.downloads_dir):
            os.makedirs(self.downloads_dir)
    
    # ---------- UTILITY METHODS ----------
    
    def clean_text(self, text: str) -> str:
        """
        Clean and normalize text by removing extra whitespace.
        
        Args:
            text: Raw text string
            
        Returns:
            Cleaned text with normalized whitespace
        """
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()
    
    def absolute_url(self, url: str, base: str) -> str:
        """
        Convert relative URL to absolute URL.
        
        Args:
            url: Relative or absolute URL
            base: Base URL for resolution
            
        Returns:
            Absolute URL
        """
        return urljoin(base, url)
    
    def remove_fragment(self, url: str) -> str:
        """
        Remove fragment identifier from URL to avoid duplicates.
        
        Args:
            url: URL with possible fragment
            
        Returns:
            URL without fragment
        """
        url, _ = urldefrag(url)
        return url
    
    def is_same_domain(self, url: str, base_domain: str) -> bool:
        """
        Check if URL belongs to the same domain.
        
        Args:
            url: URL to check
            base_domain: Base domain to compare against
            
        Returns:
            True if same domain, False otherwise
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc == base_domain or parsed.netloc.endswith('.' + base_domain)
        except:
            return False
    
    def get_domain(self, url: str) -> str:
        """
        Extract domain from URL.
        
        Args:
            url: Full URL
            
        Returns:
            Domain name
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return ""
    
    def is_product_url(self, url: str, soup: Optional[BeautifulSoup] = None) -> bool:
        """
        Detect if a URL is likely a product page using multiple signals.
        
        Args:
            url: URL to check
            soup: Optional BeautifulSoup object for content analysis
            
        Returns:
            True if likely a product page, False otherwise
        """
        url_lower = url.lower()
        
        # Common product URL patterns
        product_patterns = [
            r'/product/', r'/products/', r'/item/', r'/items/',
            r'/p/', r'/pd/', r'/dp/', r'/gp/product/',
            r'/shop/', r'/store/', r'/catalog/',
            r'product_id=', r'productid=', r'item_id=',
            r'/buy/', r'/details/', r'/view/',
            r'\.html\?product', r'\.php\?product'
        ]
        
        # Check URL patterns first (fast)
        for pattern in product_patterns:
            if re.search(pattern, url_lower):
                return True
        
        # If we have soup, do deeper content analysis
        if soup:
            # Check for common product indicators in HTML
            product_selectors = [
                'meta[property="og:type"][content*="product"]',
                'meta[name="twitter:card"][content*="product"]',
                '[itemtype*="schema.org/Product"]',
                '.product', '#product', '.product-detail', '.product-info',
                '.price', '.product-price', '.sale-price',
                '.add-to-cart', '.buy-now', '.product-title',
                '.product-description', '.product-sku'
            ]
            
            for selector in product_selectors:
                if soup.select(selector):
                    return True
            
            # Check for price patterns in text
            price_patterns = [
                r'\$\d+\.?\d*', r'€\d+\.?\d*', r'£\d+\.?\d*',
                r'price:\s*\$?\d+', r'sale:\s*\$?\d+',
                r'add to cart', r'buy now', r'sold out', r'in stock'
            ]
            
            page_text = soup.get_text().lower()
            for pattern in price_patterns:
                if re.search(pattern, page_text, re.IGNORECASE):
                    return True
        
        return False
    
    def extract_products_from_page(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """
        Extract all products from a single page.
        
        Args:
            soup: BeautifulSoup object of the page
            url: URL of the page
            
        Returns:
            List of extracted products
        """
        products = []
        
        # Method 1: Look for product schema markup
        schema_products = self._extract_schema_products(soup, url)
        products.extend(schema_products)
        
        # Method 2: Look for product containers
        container_products = self._extract_container_products(soup, url)
        products.extend(container_products)
        
        # Method 3: If no multiple products found, check if page itself is a product
        if len(products) == 0 and self.is_product_url(url, soup):
            single_product = self._extract_single_product(soup, url)
            if single_product:
                products.append(single_product)
        
        return products
    
    def _extract_schema_products(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Extract products using schema.org markup"""
        products = []
        
        # Look for Product schema
        product_elements = soup.find_all(attrs={"itemtype": re.compile(r'schema\.org/Product', re.I)})
        
        if not product_elements:
            # Try JSON-LD
            json_ld = soup.find_all('script', type='application/ld+json')
            for script in json_ld:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get('@type') == 'Product':
                        products.append(self._parse_jsonld_product(data, url))
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get('@type') == 'Product':
                                products.append(self._parse_jsonld_product(item, url))
                except:
                    continue
        
        for product_elem in product_elements:
            product = {
                "url": url,
                "name": self.clean_text(product_elem.find(attrs={"itemprop": "name"}).get_text()) if product_elem.find(attrs={"itemprop": "name"}) else None,
                "price": self.clean_text(product_elem.find(attrs={"itemprop": "price"}).get_text()) if product_elem.find(attrs={"itemprop": "price"}) else None,
                "description": self.clean_text(product_elem.find(attrs={"itemprop": "description"}).get_text()) if product_elem.find(attrs={"itemprop": "description"}) else None,
                "image": product_elem.find(attrs={"itemprop": "image"}).get('src') if product_elem.find(attrs={"itemprop": "image"}) else None,
                "sku": product_elem.find(attrs={"itemprop": "sku"}).get_text() if product_elem.find(attrs={"itemprop": "sku"}) else None,
                "availability": product_elem.find(attrs={"itemprop": "availability"}).get_text() if product_elem.find(attrs={"itemprop": "availability"}) else None,
                "source": "schema"
            }
            if product.get('name') or product.get('price'):
                products.append(self._clean_product(product))
        
        return products
    
    def _parse_jsonld_product(self, data: Dict, url: str) -> Dict:
        """Parse JSON-LD product data"""
        return self._clean_product({
            "url": url,
            "name": data.get('name'),
            "price": data.get('offers', {}).get('price') if isinstance(data.get('offers'), dict) else None,
            "description": data.get('description'),
            "image": data.get('image') if isinstance(data.get('image'), str) else (data.get('image', [{}])[0].get('url') if isinstance(data.get('image'), list) else None),
            "sku": data.get('sku'),
            "availability": data.get('offers', {}).get('availability') if isinstance(data.get('offers'), dict) else None,
            "source": "jsonld"
        })
    
    def _extract_container_products(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Extract products from common container patterns"""
        products = []
        
        # Common product container selectors
        container_selectors = [
            '.product', '.product-item', '.product-card', '.product-box',
            '.item', '.product-layout', '.product-thumb', '.product-container',
            '[class*="product"]', '[class*="Product"]', '[id*="product"]',
            '.grid-item', '.col-product', '.product-tile'
        ]
        
        for selector in container_selectors:
            containers = soup.select(selector)
            for container in containers:
                # Skip if container is too small (probably not a product)
                if len(container.get_text(strip=True)) < 20:
                    continue
                
                product = self._extract_product_from_container(container, url)
                if product.get('name') or product.get('price'):
                    # Generate a unique ID for this product to check duplicates
                    product_hash = self._generate_product_hash(product)
                    product['product_hash'] = product_hash
                    products.append(product)
        
        return products
    
    def _extract_product_from_container(self, container: BeautifulSoup, page_url: str) -> Dict:
        """Extract product details from a container element"""
        
        # Find product name (usually in heading or strong element)
        name = None
        name_elem = (
            container.find(['h1', 'h2', 'h3', 'h4', 'strong']),
            container.find(class_=re.compile(r'name|title', re.I)),
            container.find(attrs={'itemprop': 'name'})
        )
        for elem in name_elem:
            if elem:
                name = self.clean_text(elem.get_text())
                break
        
        # Find price
        price = None
        price_selectors = [
            '.price', '.product-price', '.sale-price', '.regular-price',
            '.offer-price', '[class*="price"]', '[itemprop="price"]',
            '.amount', '.current-price'
        ]
        for selector in price_selectors:
            price_elem = container.select_one(selector)
            if price_elem:
                price = self.clean_text(price_elem.get_text())
                break
        
        # If still no price, look for price patterns in text
        if not price:
            text = container.get_text()
            price_match = re.search(r'\$\s*(\d+\.?\d*)', text)
            if price_match:
                price = price_match.group(0)
        
        # Find image
        image = None
        img_elem = container.find('img')
        if img_elem:
            # Try different image attributes
            for attr in ['src', 'data-src', 'data-original', 'data-lazy-src']:
                if img_elem.get(attr):
                    image = self.absolute_url(img_elem.get(attr), page_url)
                    break
        
        # Find product URL
        product_url = None
        link_elem = container.find('a', href=True)
        if link_elem:
            product_url = self.absolute_url(link_elem['href'], page_url)
        
        # Find description
        description = None
        desc_selectors = ['.description', '.product-description', '.short-description', '[itemprop="description"]']
        for selector in desc_selectors:
            desc_elem = container.select_one(selector)
            if desc_elem:
                description = self.clean_text(desc_elem.get_text())
                break
        
        return self._clean_product({
            "url": product_url or page_url,
            "name": name,
            "price": price,
            "description": description,
            "image": image,
            "source": "container"
        })
    
    def _extract_single_product(self, soup: BeautifulSoup, url: str) -> Dict:
        """Extract a single product from a product page"""
        product = {
            "url": url,
            "name": None,
            "price": None,
            "description": None,
            "image": None,
            "sku": None,
            "availability": None,
            "rating": None,
            "reviews": None,
            "source": "single_page"
        }
        
        # Extract title (usually in h1)
        h1 = soup.find('h1')
        if h1:
            product['name'] = self.clean_text(h1.get_text())
        
        # If no h1, try title tag
        if not product['name'] and soup.title:
            product['name'] = self.clean_text(soup.title.string)
        
        # Extract price
        price_selectors = [
            '.price', '.product-price', '.current-price', '.sale-price',
            '[itemprop="price"]', '.offer-price', '.price-box .price',
            '.product-info-price .price', '.woocommerce-Price-amount'
        ]
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                product['price'] = self.clean_text(price_elem.get_text())
                break
        
        # Extract description
        desc_selectors = [
            '.description', '.product-description', '#description',
            '[itemprop="description"]', '.product-details .description',
            '.woocommerce-product-details__short-description'
        ]
        for selector in desc_selectors:
            desc_elem = soup.select_one(selector)
            if desc_elem:
                product['description'] = self.clean_text(desc_elem.get_text())
                break
        
        # Extract main image
        img_selectors = [
            '.product-image img', '.main-image img', '.gallery-image img',
            '[itemprop="image"]', '.product-img img', '.woocommerce-main-image img'
        ]
        for selector in img_selectors:
            img_elem = soup.select_one(selector)
            if img_elem and img_elem.get('src'):
                product['image'] = self.absolute_url(img_elem['src'], url)
                break
        
        # If no image with selectors, find any significant image
        if not product['image']:
            for img in soup.find_all('img', src=True):
                src = img['src']
                if 'product' in src.lower() or 'large' in src.lower():
                    product['image'] = self.absolute_url(src, url)
                    break
        
        # Extract SKU
        sku_selectors = ['.sku', '[itemprop="sku"]', '.product-sku', '.part-number']
        for selector in sku_selectors:
            sku_elem = soup.select_one(selector)
            if sku_elem:
                product['sku'] = self.clean_text(sku_elem.get_text())
                break
        
        # Extract availability
        avail_selectors = ['.stock', '.availability', '[itemprop="availability"]', '.in-stock', '.out-of-stock']
        for selector in avail_selectors:
            avail_elem = soup.select_one(selector)
            if avail_elem:
                product['availability'] = self.clean_text(avail_elem.get_text())
                break
        
        # Extract rating
        rating_selectors = ['.rating', '.average-rating', '[itemprop="ratingValue"]', '.star-rating']
        for selector in rating_selectors:
            rating_elem = soup.select_one(selector)
            if rating_elem:
                product['rating'] = self.clean_text(rating_elem.get_text())
                break
        
        return self._clean_product(product)
    
    def _generate_product_hash(self, product: Dict) -> str:
        """
        Generate a unique hash for a product to detect duplicates.
        
        Args:
            product: Product dictionary
            
        Returns:
            MD5 hash string
        """
        # Create a string from key fields
        key_fields = [
            str(product.get('name', '')),
            str(product.get('price', '')),
            str(product.get('sku', '')),
            str(product.get('url', ''))
        ]
        key_string = '|'.join(key_fields)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _clean_product(self, product: Dict) -> Dict:
        """Remove None values and empty strings from product dict"""
        return {k: v for k, v in product.items() if v not in (None, "", [], {})}
    
    # ---------- CRAWLER METHODS ----------
    
    def crawl_website(self, start_url: str, max_pages: int = 100, delay: float = 0.5) -> Dict:
        """
        Crawl entire website using BFS algorithm and extract all products.
        
        Args:
            start_url: Starting URL for crawling
            max_pages: Maximum number of pages to crawl
            delay: Delay between requests (seconds)
            
        Returns:
            Dictionary containing crawled data and statistics
        """
        # Reset state for new crawl
        self.visited_urls = set()
        self.url_queue = deque()
        self.all_products = []
        self.product_urls = set()
        
        # Initialize stats
        self.crawl_stats = {
            "pages_crawled": 0,
            "products_found": 0,
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "status": "running",
            "current_url": start_url,
            "product_urls_found": []
        }
        
        logger.info(f"Starting crawl of {start_url} (max pages: {max_pages})")
        
        # Clean and add start URL
        start_url = self.remove_fragment(start_url)
        base_domain = self.get_domain(start_url)
        
        # Initialize queue with start URL
        self.url_queue.append((start_url, 0))  # (url, depth)
        
        # BFS Crawling Loop
        while self.url_queue and self.crawl_stats["pages_crawled"] < max_pages:
            current_url, depth = self.url_queue.popleft()
            
            # Skip if already visited
            if current_url in self.visited_urls:
                continue
            
            self.visited_urls.add(current_url)
            self.crawl_stats["current_url"] = current_url
            self.crawl_stats["pages_crawled"] += 1
            
            logger.info(f"Crawling [{self.crawl_stats['pages_crawled']}/{max_pages}]: {current_url}")
            
            try:
                # Fetch page with retry logic
                page_data = self._fetch_page_with_retry(current_url)
                if not page_data:
                    continue
                
                soup, html = page_data
                
                # Extract products from this page
                page_products = self.extract_products_from_page(soup, current_url)
                
                # Add new products (avoid duplicates)
                for product in page_products:
                    product_hash = self._generate_product_hash(product)
                    
                    # Check if product already exists
                    is_duplicate = False
                    for existing in self.all_products:
                        if existing.get('product_hash') == product_hash:
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        product['product_hash'] = product_hash
                        product['found_on_page'] = current_url
                        product['crawled_at'] = datetime.now().isoformat()
                        self.all_products.append(product)
                        self.crawl_stats["products_found"] += 1
                        
                        # Track product URLs
                        if product.get('url'):
                            self.product_urls.add(product['url'])
                
                # Find all links for further crawling
                if depth < 5:  # Limit crawl depth to 5 levels
                    new_links = self._extract_links(soup, current_url, base_domain)
                    
                    # Prioritize product URLs
                    product_links = []
                    normal_links = []
                    
                    for link in new_links:
                        if link not in self.visited_urls:
                            if self.is_product_url(link):
                                product_links.append(link)
                            else:
                                normal_links.append(link)
                    
                    # Add product URLs first (higher priority)
                    for link in product_links:
                        if link not in self.visited_urls:
                            self.url_queue.append((link, depth + 1))
                            self.crawl_stats.setdefault("product_urls_found", []).append(link)
                    
                    # Add normal URLs
                    for link in normal_links:
                        if link not in self.visited_urls and len(self.url_queue) < max_pages * 2:
                            self.url_queue.append((link, depth + 1))
                
                # Respect delay between requests
                time.sleep(delay)
                
            except Exception as e:
                logger.error(f"Error crawling {current_url}: {str(e)}")
                continue
        
        # Complete crawl
        self.crawl_stats["end_time"] = datetime.now().isoformat()
        self.crawl_stats["status"] = "completed"
        
        # Prepare final result
        result = {
            "crawl_id": str(uuid.uuid4()),
            "start_url": start_url,
            "crawl_stats": self.crawl_stats,
            "products": self.all_products,
            "product_count": len(self.all_products),
            "unique_product_urls": list(self.product_urls),
            "crawled_pages": list(self.visited_urls),
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Crawl completed: {len(self.all_products)} products found from {self.crawl_stats['pages_crawled']} pages")
        
        return result
    
    def _fetch_page_with_retry(self, url: str, max_retries: int = 3) -> Optional[tuple]:
        """
        Fetch a page with retry logic.
        
        Args:
            url: URL to fetch
            max_retries: Maximum number of retry attempts
            
        Returns:
            Tuple of (BeautifulSoup object, HTML string) or None if failed
        """
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                # Check if HTML content
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                    logger.debug(f"Skipping non-HTML: {url}")
                    return None
                
                soup = BeautifulSoup(response.text, "html.parser")
                return (soup, response.text)
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {url}: {str(e)}")
                if attempt == max_retries - 1:
                    return None
                time.sleep(2 ** attempt)  # Exponential backoff
            
            except Exception as e:
                logger.error(f"Unexpected error fetching {url}: {str(e)}")
                return None
        
        return None
    
    def _extract_links(self, soup: BeautifulSoup, base_url: str, base_domain: str) -> Set[str]:
        """
        Extract all same-domain links from a page.
        
        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving relative links
            base_domain: Domain to stay within
            
        Returns:
            Set of absolute URLs within the same domain
        """
        links = set()
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()
            
            # Skip empty, javascript, mailto, tel
            if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            
            # Make absolute URL
            absolute_url = self.absolute_url(href, base_url)
            absolute_url = self.remove_fragment(absolute_url)
            
            # Check if same domain
            if self.is_same_domain(absolute_url, base_domain):
                links.add(absolute_url)
        
        return links
    
    def get_crawl_status(self, session_id: str) -> Optional[Dict]:
        """Get status of a crawl session (placeholder for future implementation)"""
        # This would need session storage in a real implementation
        return self.crawl_stats
    
    # ---------- SINGLE PAGE SCRAPER ----------
    
    def scrape_website(self, url: str, mode: str = "comprehensive") -> Dict:
        """
        Scrape a single website (legacy method, kept for compatibility).
        
        Args:
            url: URL to scrape
            mode: Scraping mode (basic, smart, comprehensive)
            
        Returns:
            Dictionary with scraped data
        """
        start_time = time.time()
        
        try:
            # Fetch page
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remove scripts/styles
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            
            # Extract metadata
            title = self.clean_text(soup.title.string) if soup.title else ""
            
            meta_desc = soup.find("meta", attrs={"name": "description"})
            description = self.clean_text(meta_desc.get("content")) if meta_desc else ""
            
            # Extract headings
            headings = {}
            for i in range(1, 7):
                heading_texts = [self.clean_text(h.get_text()) for h in soup.find_all(f"h{i}")]
                if heading_texts:
                    headings[f"h{i}"] = heading_texts
            
            # Extract paragraphs
            paragraphs = [self.clean_text(p.get_text()) for p in soup.find_all("p") 
                         if len(self.clean_text(p.get_text())) > 30]
            
            # Extract structured data
            structured_data = self.extract_structured_data(soup, url)
            
            # Extract images
            images = []
            for img in soup.find_all("img"):
                if img.get("src"):
                    images.append({
                        "url": self.absolute_url(img.get("src"), url),
                        "alt": self.clean_text(img.get("alt")),
                        "title": self.clean_text(img.get("title"))
                    })
            
            # Extract links
            domain = self.get_domain(url)
            internal_links = []
            external_links = []
            
            for a in soup.find_all("a", href=True):
                link_url = self.absolute_url(a["href"], url)
                link_text = self.clean_text(a.get_text())
                link_data = {"url": link_url, "text": link_text}
                
                if self.is_same_domain(link_url, domain):
                    internal_links.append(link_data)
                else:
                    external_links.append(link_data)
            
            # Extract products (if any)
            products = self.extract_products_from_page(soup, url)
            
            # Generate full text
            full_text = self.generate_professional_text(soup, structured_data, url)
            
            # Prepare data based on mode
            if mode == "basic":
                data = {
                    "scrape_id": str(uuid.uuid4()),
                    "url": url,
                    "title": title,
                    "description": description,
                    "paragraphs": paragraphs[:10],
                    "products": products[:5],
                    "stats": {
                        "paragraph_count": len(paragraphs[:10]),
                        "product_count": len(products[:5]),
                        "scrape_time": round(time.time() - start_time, 2)
                    }
                }
            elif mode == "smart":
                data = {
                    "scrape_id": str(uuid.uuid4()),
                    "url": url,
                    "title": title,
                    "description": description,
                    "headings": {k: v[:5] for k, v in headings.items()},
                    "paragraphs": paragraphs[:20],
                    "images": images[:10],
                    "products": products[:10],
                    "stats": {
                        "paragraph_count": len(paragraphs[:20]),
                        "product_count": len(products[:10]),
                        "image_count": len(images[:10]),
                        "scrape_time": round(time.time() - start_time, 2)
                    }
                }
            else:  # comprehensive
                data = {
                    "scrape_id": str(uuid.uuid4()),
                    "url": url,
                    "title": title,
                    "description": description,
                    "headings": headings,
                    "paragraphs": paragraphs,
                    "structured_data": structured_data,
                    "images": images,
                    "internal_links": internal_links[:50],
                    "external_links": external_links[:50],
                    "products": products,
                    "full_text": full_text[:10000],
                    "stats": {
                        "paragraph_count": len(paragraphs),
                        "product_count": len(products),
                        "image_count": len(images),
                        "internal_links_count": len(internal_links),
                        "external_links_count": len(external_links),
                        "scrape_time": round(time.time() - start_time, 2)
                    },
                    "scraped_at": datetime.now().isoformat()
                }
            
            return self._clean_product(data)  # Reuse product cleaning method
            
        except Exception as e:
            logger.error(f"Scrape error for {url}: {str(e)}")
            return {"error": str(e)}
    
    # ---------- STRUCTURED DATA EXTRACTION ----------
    
    def extract_structured_data(self, soup: BeautifulSoup, url: str) -> Dict:
        """
        Extract structured data like tables, lists, etc.
        
        Args:
            soup: BeautifulSoup object
            url: Base URL
            
        Returns:
            Dictionary with structured data
        """
        structured_data = {
            "tables": [],
            "lists": [],
            "metadata": []
        }
        
        # Extract tables
        for table in soup.find_all("table"):
            table_data = self.extract_table_data(table)
            if table_data:
                structured_data["tables"].append(table_data)
        
        # Extract lists
        for list_tag in soup.find_all(["ul", "ol"]):
            list_data = self.extract_list_data(list_tag)
            if list_data:
                structured_data["lists"].append(list_data)
        
        # Extract meta tags
        for meta in soup.find_all("meta"):
            if meta.get("name") and meta.get("content"):
                structured_data["metadata"].append({
                    "name": meta.get("name"),
                    "content": meta.get("content")
                })
        
        return structured_data
    
    def extract_table_data(self, table: BeautifulSoup) -> Optional[Dict]:
        """Extract data from HTML table"""
        headers = []
        rows = []
        
        # Extract headers
        header_row = table.find("tr")
        if header_row:
            headers = [self.clean_text(th.get_text()) for th in header_row.find_all(["th", "td"])]
        
        # Extract rows
        for tr in table.find_all("tr")[1:]:
            row = [self.clean_text(td.get_text()) for td in tr.find_all("td")]
            if any(row):
                rows.append(row)
        
        if headers or rows:
            return {
                "headers": headers,
                "rows": rows,
                "row_count": len(rows),
                "column_count": len(headers) if headers else (len(rows[0]) if rows else 0)
            }
        
        return None
    
    def extract_list_data(self, list_tag: BeautifulSoup) -> Optional[Dict]:
        """Extract data from HTML list"""
        items = [self.clean_text(li.get_text()) for li in list_tag.find_all("li") 
                if self.clean_text(li.get_text())]
        
        if items:
            return {
                "type": list_tag.name,
                "items": items,
                "item_count": len(items)
            }
        
        return None
    
    # ---------- TEXT GENERATION ----------
    
    def generate_professional_text(self, soup: BeautifulSoup, structured_data: Dict, base_url: str = "") -> str:
        """
        Generate well-formatted text from page content.
        
        Args:
            soup: BeautifulSoup object
            structured_data: Structured data from the page
            base_url: Base URL for resolving links
            
        Returns:
            Formatted text string
        """
        parts = []
        
        # Title
        if soup.title:
            parts.append(f"# {self.clean_text(soup.title.string)}\n")
        
        # Headings
        for i in range(1, 7):
            for heading in soup.find_all(f"h{i}"):
                text = self.clean_text(heading.get_text())
                if text:
                    parts.append(f"{'#' * i} {text}")
        
        # Tables
        if structured_data.get("tables"):
            parts.append("\n## TABLES")
            for idx, table in enumerate(structured_data["tables"], 1):
                parts.append(f"\n### Table {idx}")
                if table.get("headers"):
                    parts.append(" | ".join(table["headers"]))
                    parts.append("-" * 50)
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
            text = self.clean_text(p.get_text())
            if len(text) > 50:  # Only meaningful paragraphs
                parts.append(f"\n{text}")
        
        return "\n".join(parts)
    
    # ---------- EXPORT METHODS ----------
    
    def save_as_json(self, data: Any, filename: str) -> str:
        """Save data as JSON file"""
        filepath = os.path.join(self.downloads_dir, f"{filename}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return filepath
    
    def save_as_csv(self, data: Any, filename: str) -> str:
        """Save data as CSV file"""
        filepath = os.path.join(self.downloads_dir, f"{filename}.csv")
        
        # Handle different data structures
        if isinstance(data, dict) and data.get('products'):
            # Crawl result with products
            products = data['products']
            if products:
                df = pd.DataFrame(products)
                df.to_csv(filepath, index=False, encoding='utf-8')
            else:
                # Create empty CSV with headers
                pd.DataFrame().to_csv(filepath, index=False)
        
        elif isinstance(data, list):
            # Direct list of items
            df = pd.DataFrame(data)
            df.to_csv(filepath, index=False, encoding='utf-8')
        
        else:
            # Single item
            df = pd.DataFrame([data])
            df.to_csv(filepath, index=False, encoding='utf-8')
        
        return filepath
    
    def save_as_excel(self, data: Any, filename: str) -> str:
        """Save data as Excel file with multiple sheets"""
        filepath = os.path.join(self.downloads_dir, f"{filename}.xlsx")
        
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            if isinstance(data, dict) and data.get('products'):
                # Products sheet
                if data['products']:
                    pd.DataFrame(data['products']).to_excel(writer, sheet_name='Products', index=False)
                
                # Statistics sheet
                if data.get('crawl_stats'):
                    stats_data = []
                    for key, value in data['crawl_stats'].items():
                        stats_data.append({'Statistic': key, 'Value': value})
                    pd.DataFrame(stats_data).to_excel(writer, sheet_name='Statistics', index=False)
                
                # Pages sheet
                if data.get('crawled_pages'):
                    pages_df = pd.DataFrame({'Crawled Pages': data['crawled_pages']})
                    pages_df.to_excel(writer, sheet_name='Pages', index=False)
            
            elif isinstance(data, list):
                # List data
                pd.DataFrame(data).to_excel(writer, sheet_name='Data', index=False)
            
            else:
                # Single item
                pd.DataFrame([data]).to_excel(writer, sheet_name='Data', index=False)
        
        return filepath
    
    def save_as_text(self, data: Any, filename: str) -> str:
        """Save data as text file"""
        filepath = os.path.join(self.downloads_dir, f"{filename}.txt")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            if isinstance(data, dict):
                # Pretty print dictionary
                if data.get('products'):
                    f.write(f"PRODUCTS FOUND: {data.get('product_count', 0)}\n")
                    f.write("=" * 50 + "\n\n")
                    
                    for idx, product in enumerate(data.get('products', []), 1):
                        f.write(f"PRODUCT #{idx}\n")
                        f.write("-" * 30 + "\n")
                        for key, value in product.items():
                            if value and key not in ['product_hash']:
                                f.write(f"{key.upper()}: {value}\n")
                        f.write("\n")
                else:
                    # Regular dictionary
                    for key, value in data.items():
                        if isinstance(value, (dict, list)):
                            f.write(f"{key.upper()}:\n{json.dumps(value, indent=2)}\n\n")
                        else:
                            f.write(f"{key.upper()}: {value}\n")
            
            elif isinstance(data, list):
                # List of items
                for idx, item in enumerate(data, 1):
                    f.write(f"ITEM #{idx}\n")
                    f.write("-" * 30 + "\n")
                    f.write(f"{json.dumps(item, indent=2)}\n\n")
            
            else:
                # Primitive type
                f.write(str(data))
        
        return filepath
    
    def save_as_pdf(self, data: Any, filename: str) -> str:
        """Save data as PDF file"""
        filepath = os.path.join(self.downloads_dir, f"{filename}.pdf")
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Title
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "AI SCRAPER - Export Report", ln=True, align='C')
        pdf.ln(10)
        
        # Timestamp
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 10, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True)
        pdf.ln(10)
        
        # Content
        pdf.set_font("Arial", size=12)
        
        if isinstance(data, dict):
            # Summary
            if data.get('crawl_stats'):
                pdf.set_font("Arial", 'B', 14)
                pdf.cell(0, 10, "Crawl Statistics", ln=True)
                pdf.set_font("Arial", size=12)
                
                for key, value in data['crawl_stats'].items():
                    if key != 'product_urls_found':
                        pdf.cell(0, 8, f"{key.replace('_', ' ').title()}: {value}", ln=True)
                pdf.ln(5)
            
            # Products
            if data.get('products'):
                pdf.add_page()
                pdf.set_font("Arial", 'B', 14)
                pdf.cell(0, 10, f"Products ({len(data['products'])})", ln=True)
                pdf.ln(5)
                
                for idx, product in enumerate(data['products'][:50], 1):  # Limit to 50 products for PDF
                    pdf.set_font("Arial", 'B', 12)
                    pdf.cell(0, 8, f"Product #{idx}", ln=True)
                    pdf.set_font("Arial", size=10)
                    
                    for key, value in product.items():
                        if value and key not in ['product_hash', 'found_on_page']:
                            # Handle long text
                            text = f"{key.replace('_', ' ').title()}: {str(value)}"
                            if len(text) > 80:
                                # Split long lines
                                lines = [text[i:i+80] for i in range(0, len(text), 80)]
                                for line in lines:
                                    pdf.cell(0, 5, line, ln=True)
                            else:
                                pdf.cell(0, 5, text, ln=True)
                    pdf.ln(3)
        
        pdf.output(filepath)
        return filepath
    
    def save_as_markdown(self, data: Any, filename: str) -> str:
        """Save data as Markdown file"""
        filepath = os.path.join(self.downloads_dir, f"{filename}.md")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            if isinstance(data, dict) and data.get('products'):
                # Header
                f.write(f"# Website Crawl Report\n\n")
                f.write(f"**Start URL:** {data.get('start_url', 'N/A')}\n")
                f.write(f"**Crawl Date:** {data.get('timestamp', 'N/A')}\n")
                f.write(f"**Products Found:** {data.get('product_count', 0)}\n")
                f.write(f"**Pages Crawled:** {data.get('crawl_stats', {}).get('pages_crawled', 0)}\n\n")
                
                # Statistics
                f.write("## Crawl Statistics\n\n")
                stats = data.get('crawl_stats', {})
                for key, value in stats.items():
                    if key != 'product_urls_found':
                        f.write(f"- **{key.replace('_', ' ').title()}:** {value}\n")
                f.write("\n")
                
                # Products
                f.write("## Products\n\n")
                for idx, product in enumerate(data.get('products', []), 1):
                    f.write(f"### Product #{idx}\n\n")
                    for key, value in product.items():
                        if value and key not in ['product_hash']:
                            f.write(f"- **{key.replace('_', ' ').title()}:** {value}\n")
                    f.write("\n---\n\n")
            
            elif isinstance(data, list):
                # List of items
                f.write("# Exported Data\n\n")
                for idx, item in enumerate(data, 1):
                    f.write(f"## Item {idx}\n\n")
                    f.write(f"```json\n{json.dumps(item, indent=2)}\n```\n\n")
            
            else:
                # Single item
                f.write("# Exported Data\n\n")
                f.write(f"```json\n{json.dumps(data, indent=2)}\n```\n")
        
        return filepath