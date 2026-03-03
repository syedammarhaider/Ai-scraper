# scraper.py - Complete website scraper with multi-product support
# Yeh file website scraping ke liye hai - full site scrap karti hai

import requests  # Web requests karne ke liye
import re        # Regular expressions for text cleaning
import time      # Timing functions ke liye
import uuid      # Unique IDs generate karne ke liye
import csv       # CSV files banane ke liye
import os        # File system operations ke liye
import json      # JSON data handle karne ke liye
import urllib3   # SSL warnings disable karne ke liye
from bs4 import BeautifulSoup  # HTML parsing ke liye
from urllib.parse import urljoin, urlparse, urlencode  # URL manipulation ke liye
from datetime import datetime  # Date/time handling ke liye
from fpdf import FPDF  # PDF generation ke liye
import pandas as pd  # Excel export ke liye
from collections import deque  # BFS traversal ke liye (queue)

# SSL warnings band karo (clean output ke liye)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class UltraScraper:
    """
    Ultra Professional Scraper - Full website scraping with product extraction
    Yeh class complete website scraping karti hai, saari products nikal leti hai
    """
    
    def __init__(self):
        """Initialize scraper with session and settings"""
        # Session create karo with headers
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        })
        self.session.verify = False  # SSL verification off (faster)
        
        # Visited URLs track karne ke liye
        self.visited_urls = set()
        
        # Scraped data store karne ke liye
        self.all_products = []
        self.all_pages = []
        
        # Common product URL patterns (product pages identify karne ke liye)
        self.product_patterns = [
            r'/product/', r'/products/', r'/item/', r'/items/', 
            r'/p/', r'/dp/', r'/gp/product/', r'/shop/', r'/store/',
            r'/collection/', r'/collections/', r'/catalog/', r'/catalogue/',
            r'/detail/', r'/details/', r'/view/', r'/show/', r'/watch/',
            r'/buy/', r'/order/', r'/pdp/', r'/product-page/', r'/prod/',
            r'/\d+\.html$', r'/pd-', r'/pr-', r'/sku/', r'/asin/', r'/upc/'
        ]
        
        # Common category/list page patterns
        self.category_patterns = [
            r'/category/', r'/categories/', r'/collection/', r'/collections/',
            r'/shop/', r'/store/', r'/products/', r'/all-products/',
            r'/catalog/', r'/catalogue/', r'/browse/', r'/list/',
            r'/page/', r'/search/', r'/filter/', r'/sort/',
            r'/brand/', r'/brands/', r'/tags/', r'/tag/'
        ]
        
        # Maximum pages to scrape (set high for full site)
        self.max_pages = 1000
        self.max_products = 10000
        
    # ---------- UTILITY FUNCTIONS ----------
    def clean_text(self, text):
        """Text clean karo - extra spaces, newlines remove karo"""
        if not text:
            return ""
        # Multiple spaces ko single space mein convert karo
        text = re.sub(r'\s+', ' ', str(text))
        # Trim karo
        return text.strip()
    
    def extract_numbers(self, text):
        """Text se numbers extract karo (prices ke liye)"""
        if not text:
            return []
        # Find all numbers (including decimals)
        numbers = re.findall(r'[\d,]+\.?\d*', str(text))
        # Clean commas and convert
        clean_numbers = []
        for num in numbers:
            num = num.replace(',', '')
            try:
                if '.' in num:
                    clean_numbers.append(float(num))
                else:
                    clean_numbers.append(int(num))
            except:
                pass
        return clean_numbers
    
    def extract_price(self, text):
        """Text se price extract karo"""
        if not text:
            return None
        # Price patterns: $19.99, 19.99$, USD 19.99, etc.
        price_patterns = [
            r'\$\s*([\d,]+\.?\d*)',
            r'([\d,]+\.?\d*)\s*\$',
            r'€\s*([\d,]+\.?\d*)',
            r'([\d,]+\.?\d*)\s*€',
            r'£\s*([\d,]+\.?\d*)',
            r'([\d,]+\.?\d*)\s*£',
            r'₹\s*([\d,]+\.?\d*)',
            r'([\d,]+\.?\d*)\s*₹',
            r'PKR\s*([\d,]+\.?\d*)',
            r'([\d,]+\.?\d*)\s*PKR',
            r'Rs\.?\s*([\d,]+\.?\d*)',
            r'([\d,]+\.?\d*)\s*Rs\.?',
            r'price[:\s]+([\d,]+\.?\d*)',
            r'[\d,]+\.?\d*'
        ]
        
        text = str(text)
        for pattern in price_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Get the number part (usually group 1)
                num_str = match.group(1) if match.groups() else match.group(0)
                # Clean and convert
                num_str = num_str.replace(',', '')
                try:
                    return float(num_str)
                except:
                    pass
        return None
    
    def is_product_url(self, url):
        """Check karo ke URL product page ka hai ya nahi"""
        url_lower = url.lower()
        for pattern in self.product_patterns:
            if re.search(pattern, url_lower):
                return True
        return False
    
    def is_category_url(self, url):
        """Check karo ke URL category/list page ka hai ya nahi"""
        url_lower = url.lower()
        for pattern in self.category_patterns:
            if re.search(pattern, url_lower):
                return True
        return False
    
    def get_absolute_url(self, relative_url, base_url):
        """Relative URL ko absolute mein convert karo"""
        if not relative_url:
            return None
        return urljoin(base_url, relative_url)
    
    def is_same_domain(self, url, base_url):
        """Check karo ke URL same domain ka hai ya nahi"""
        try:
            url_domain = urlparse(url).netloc
            base_domain = urlparse(base_url).netloc
            return url_domain == base_domain or not url_domain
        except:
            return False
    
    # ---------- PRODUCT EXTRACTION ----------
    def extract_products_from_page(self, soup, page_url):
        """
        Single page se saare products extract karo
        Yeh function AI-powered hai - different patterns identify karta hai
        """
        products = []
        
        # Method 1: Product containers dhoondo (common patterns)
        product_containers = []
        
        # Common container classes/IDs
        container_selectors = [
            'product', 'item', 'prod', 'product-item', 'product-card',
            'product-box', 'product-thumb', 'product-wrapper',
            'grid-item', 'collection-item', 'catalog-item',
            'card', 'product-card', 'item-card', 'shop-item',
            'product-tile', 'product-listing', 'product-row',
            'article', 'post', 'listing-item', 'product-list-item',
            '.product', '.item', '[class*="product"]', '[class*="Product"]',
            '[class*="prod"]', '[class*="item"]', '[class*="card"]',
            'div[data-product]', 'li[data-product]', 'tr[data-product]'
        ]
        
        # Try each selector
        for selector in container_selectors:
            # Handle different selector types
            if selector.startswith('.'):
                found = soup.find_all(class_=selector[1:])
            elif selector.startswith('['):
                found = soup.find_all(selector)
            else:
                found = soup.find_all(class_=selector)
            
            if found and len(found) > len(product_containers):
                product_containers = found
        
        # Also try finding by tag + class patterns
        if not product_containers:
            for tag in ['div', 'li', 'article', 'section', 'tr', 'a']:
                found = soup.find_all(tag, class_=re.compile(r'product|item|card', re.I))
                if found and len(found) > len(product_containers):
                    product_containers = found
        
        # Method 2: Product links dhoondo
        product_links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if self.is_product_url(href):
                product_links.append({
                    'url': self.get_absolute_url(href, page_url),
                    'text': self.clean_text(a.get_text()),
                    'element': a
                })
        
        # Method 3: Extract from structured data (JSON-LD)
        structured_products = self.extract_structured_products(soup, page_url)
        if structured_products:
            products.extend(structured_products)
        
        # Method 4: Process product containers
        for container in product_containers[:50]:  # Max 50 per page
            product = self.extract_product_from_container(container, page_url)
            if product and product.get('name'):
                # Check if it's actually a product (has price or product indicators)
                if product.get('price') or product.get('url') and self.is_product_url(product['url']):
                    products.append(product)
        
        # Method 5: Process product links (if containers didn't work)
        if len(products) < 5 and product_links:
            for link_info in product_links[:30]:
                # Try to extract product info from the link's context
                a_element = link_info['element']
                # Look for parent container that might have more info
                parent = a_element.find_parent(['div', 'li', 'article', 'section'])
                if parent:
                    product = self.extract_product_from_container(parent, page_url)
                    if product and product.get('name'):
                        products.append(product)
                else:
                    # Just the link itself
                    products.append({
                        'name': link_info['text'] or 'Product',
                        'url': link_info['url'],
                        'page_url': page_url
                    })
        
        # Remove duplicates (same URL)
        unique_products = []
        seen_urls = set()
        for p in products:
            url = p.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_products.append(p)
            elif not url:
                unique_products.append(p)
        
        return unique_products
    
    def extract_product_from_container(self, container, page_url):
        """
        Ek container element se product details extract karo
        """
        product = {}
        
        # 1. Product name/title
        name_selectors = [
            'h1', 'h2', 'h3', 'h4', '.title', '.name', '.product-title',
            '.product-name', '.item-title', '.card-title', '.heading',
            '[class*="title"]', '[class*="name"]', 'strong', 'b',
            'a[class*="title"]', 'a[class*="name"]'
        ]
        
        for selector in name_selectors:
            if selector.startswith('.'):
                elem = container.find(class_=selector[1:])
            elif selector.startswith('['):
                elem = container.find(selector)
            else:
                elem = container.find(selector)
            
            if elem:
                name = self.clean_text(elem.get_text())
                if name and len(name) > 3:
                    product['name'] = name
                    break
        
        # If no name found, try any heading or link
        if 'name' not in product:
            for tag in ['h1', 'h2', 'h3', 'h4', 'a']:
                elem = container.find(tag)
                if elem:
                    name = self.clean_text(elem.get_text())
                    if name and len(name) > 3:
                        product['name'] = name
                        break
        
        # 2. Product URL
        link = container.find('a', href=True)
        if link:
            product['url'] = self.get_absolute_url(link['href'], page_url)
        elif container.name == 'a' and container.get('href'):
            product['url'] = self.get_absolute_url(container['href'], page_url)
        
        # 3. Price
        price_selectors = [
            '.price', '.product-price', '.sale-price', '.regular-price',
            '.current-price', '.amount', '.offer-price', '.selling-price',
            '[class*="price"]', '.cost', '.prix', '.precio', '.preis',
            'span[class*="price"]', 'div[class*="price"]', 'strong[class*="price"]',
            '.currency', '.value', '.money'
        ]
        
        for selector in price_selectors:
            if selector.startswith('.'):
                elem = container.find(class_=selector[1:])
            elif selector.startswith('['):
                elem = container.find(selector)
            else:
                elem = container.find(selector)
            
            if elem:
                price_text = self.clean_text(elem.get_text())
                price = self.extract_price(price_text)
                if price:
                    product['price'] = price
                    product['price_text'] = price_text
                    break
        
        # If no price found, check any element with numbers
        if 'price' not in product:
            for elem in container.find_all(['span', 'div', 'p', 'strong']):
                text = elem.get_text()
                if re.search(r'[\d,]+\.?\d*', text):
                    price = self.extract_price(text)
                    if price:
                        product['price'] = price
                        product['price_text'] = self.clean_text(text)
                        break
        
        # 4. Image
        img = container.find('img')
        if img:
            # Try different image attributes
            for attr in ['src', 'data-src', 'data-original', 'data-lazy-src', 'data-echo']:
                if img.get(attr):
                    product['image'] = self.get_absolute_url(img[attr], page_url)
                    break
            if 'image' not in product and img.get('src'):
                product['image'] = self.get_absolute_url(img['src'], page_url)
            
            # Alt text
            if img.get('alt'):
                product['image_alt'] = self.clean_text(img['alt'])
        
        # 5. Description/Snippet
        desc_selectors = [
            '.description', '.desc', '.product-description', '.snippet',
            '.short-description', '.excerpt', '.summary', '.details',
            'p', '.text', '.content'
        ]
        
        for selector in desc_selectors:
            if selector.startswith('.'):
                elem = container.find(class_=selector[1:])
            elif selector == 'p':
                elem = container.find('p')
            else:
                elem = container.find(selector)
            
            if elem:
                desc = self.clean_text(elem.get_text())
                if desc and len(desc) > 10:
                    product['description'] = desc
                    break
        
        # 6. SKU/ID
        sku_selectors = [
            '.sku', '.product-sku', '.id', '.product-id', '.code',
            '[class*="sku"]', '[class*="id"]', '[data-sku]', '[data-id]'
        ]
        
        for selector in sku_selectors:
            if selector.startswith('.'):
                elem = container.find(class_=selector[1:])
            elif selector.startswith('['):
                elem = container.find(selector)
            else:
                elem = container.find(selector)
            
            if elem:
                sku = self.clean_text(elem.get_text())
                if sku:
                    product['sku'] = sku
                    break
        
        # 7. Rating/Reviews
        rating_selectors = [
            '.rating', '.reviews', '.stars', '.review-count',
            '[class*="rating"]', '[class*="stars"]'
        ]
        
        for selector in rating_selectors:
            if selector.startswith('.'):
                elem = container.find(class_=selector[1:])
            elif selector.startswith('['):
                elem = container.find(selector)
            else:
                elem = container.find(selector)
            
            if elem:
                rating_text = self.clean_text(elem.get_text())
                rating_numbers = self.extract_numbers(rating_text)
                if rating_numbers:
                    product['rating'] = rating_numbers[0]
                    if len(rating_numbers) > 1:
                        product['review_count'] = rating_numbers[1]
                    elif 'out of' in rating_text.lower() or '/' in rating_text:
                        # Try to parse rating like "4.5 out of 5"
                        parts = re.findall(r'([\d.]+)', rating_text)
                        if len(parts) >= 2:
                            product['rating'] = float(parts[0])
                            product['max_rating'] = float(parts[1])
                    break
        
        # 8. Stock status
        stock_selectors = [
            '.stock', '.availability', '.in-stock', '.out-of-stock',
            '[class*="stock"]', '[class*="availability"]'
        ]
        
        for selector in stock_selectors:
            if selector.startswith('.'):
                elem = container.find(class_=selector[1:])
            elif selector.startswith('['):
                elem = container.find(selector)
            else:
                elem = container.find(selector)
            
            if elem:
                stock_text = self.clean_text(elem.get_text()).lower()
                product['stock_status'] = stock_text
                product['in_stock'] = 'out of stock' not in stock_text and 'sold out' not in stock_text
                break
        
        # 9. Category
        category_selectors = [
            '.category', '.breadcrumb', '.crumbs', '[class*="category"]',
            '.collection', '.tag'
        ]
        
        for selector in category_selectors:
            if selector.startswith('.'):
                elem = container.find(class_=selector[1:])
            elif selector.startswith('['):
                elem = container.find(selector)
            else:
                elem = container.find(selector)
            
            if elem:
                category = self.clean_text(elem.get_text())
                if category and len(category) < 50:
                    product['category'] = category
                    break
        
        # Only return if we have at least a name
        if product.get('name'):
            return product
        return None
    
    def extract_structured_products(self, soup, page_url):
        """
        JSON-LD structured data se products extract karo
        """
        products = []
        
        # Find all script tags with JSON-LD
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                
                # Handle different structures
                if isinstance(data, dict):
                    # Single product
                    if data.get('@type') in ['Product', 'Item']:
                        product = self.parse_structured_product(data, page_url)
                        if product:
                            products.append(product)
                    
                    # Multiple products in a list
                    elif data.get('@graph'):
                        for item in data['@graph']:
                            if item.get('@type') in ['Product', 'Item']:
                                product = self.parse_structured_product(item, page_url)
                                if product:
                                    products.append(product)
                
                elif isinstance(data, list):
                    # List of items
                    for item in data:
                        if isinstance(item, dict):
                            if item.get('@type') in ['Product', 'Item']:
                                product = self.parse_structured_product(item, page_url)
                                if product:
                                    products.append(product)
            
            except:
                continue
        
        return products
    
    def parse_structured_product(self, data, page_url):
        """
        JSON-LD object se product parse karo
        """
        product = {}
        
        # Name
        if data.get('name'):
            product['name'] = self.clean_text(data['name'])
        elif data.get('title'):
            product['name'] = self.clean_text(data['title'])
        
        # URL
        if data.get('url'):
            product['url'] = self.get_absolute_url(data['url'], page_url)
        
        # Price
        if data.get('offers'):
            offers = data['offers']
            if isinstance(offers, dict):
                if offers.get('price'):
                    try:
                        product['price'] = float(offers['price'])
                    except:
                        pass
                if offers.get('priceCurrency'):
                    product['currency'] = offers['priceCurrency']
                if offers.get('availability'):
                    product['availability'] = offers['availability']
            elif isinstance(offers, list) and offers:
                if offers[0].get('price'):
                    try:
                        product['price'] = float(offers[0]['price'])
                    except:
                        pass
        
        # Image
        if data.get('image'):
            if isinstance(data['image'], str):
                product['image'] = self.get_absolute_url(data['image'], page_url)
            elif isinstance(data['image'], dict) and data['image'].get('url'):
                product['image'] = self.get_absolute_url(data['image']['url'], page_url)
            elif isinstance(data['image'], list) and data['image']:
                product['image'] = self.get_absolute_url(data['image'][0], page_url)
        
        # Description
        if data.get('description'):
            product['description'] = self.clean_text(data['description'])
        
        # SKU
        if data.get('sku'):
            product['sku'] = data['sku']
        
        # Brand
        if data.get('brand'):
            if isinstance(data['brand'], dict):
                product['brand'] = data['brand'].get('name')
            else:
                product['brand'] = data['brand']
        
        # Rating
        if data.get('aggregateRating'):
            rating = data['aggregateRating']
            if rating.get('ratingValue'):
                try:
                    product['rating'] = float(rating['ratingValue'])
                except:
                    pass
            if rating.get('reviewCount'):
                try:
                    product['review_count'] = int(rating['reviewCount'])
                except:
                    pass
        
        return product if product.get('name') else None
    
    # ---------- PAGE EXTRACTION ----------
    def extract_page_data(self, url, soup):
        """
        Page se general information extract karo
        """
        page_data = {
            'url': url,
            'title': '',
            'description': '',
            'headings': {},
            'paragraphs': [],
            'links': [],
            'images': [],
            'product_count': 0
        }
        
        # Title
        if soup.title:
            page_data['title'] = self.clean_text(soup.title.string)
        
        # Meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            page_data['description'] = self.clean_text(meta_desc.get('content', ''))
        
        # Headings
        for i in range(1, 7):
            headings = soup.find_all(f'h{i}')
            if headings:
                page_data['headings'][f'h{i}'] = [self.clean_text(h.get_text()) for h in headings]
        
        # Paragraphs
        paragraphs = []
        for p in soup.find_all('p'):
            text = self.clean_text(p.get_text())
            if text and len(text) > 20:
                paragraphs.append(text)
        page_data['paragraphs'] = paragraphs[:20]  # Max 20 paragraphs
        
        return page_data
    
    # ---------- CRAWLER ----------
    def crawl_website(self, start_url, max_pages=500, max_products=5000):
        """
        Complete website crawl karo - BFS algorithm use karte hain
        start_url: Starting URL
        max_pages: Maximum pages to crawl
        max_products: Maximum products to collect
        """
        print(f"\n{'='*60}")
        print(f"🚀 STARTING FULL WEBSITE CRAWL")
        print(f"📌 Start URL: {start_url}")
        print(f"📊 Max Pages: {max_pages}")
        print(f"📦 Max Products: {max_products}")
        print(f"{'='*60}\n")
        
        # Reset data
        self.visited_urls = set()
        self.all_products = []
        self.all_pages = []
        
        # Queue for BFS
        urls_to_visit = deque([start_url])
        
        # Stats
        pages_scraped = 0
        products_found = 0
        categories_found = 0
        
        # Start crawling
        while urls_to_visit and pages_scraped < max_pages and products_found < max_products:
            # Get next URL
            current_url = urls_to_visit.popleft()
            
            # Skip if already visited
            if current_url in self.visited_urls:
                continue
            
            # Mark as visited
            self.visited_urls.add(current_url)
            
            print(f"\n🔍 Scraping [{pages_scraped+1}/{max_pages}]: {current_url[:100]}...")
            
            try:
                # Fetch page
                response = self.session.get(current_url, timeout=30)
                response.raise_for_status()
                
                # Parse HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Remove scripts/styles
                for tag in soup(['script', 'style', 'noscript', 'iframe']):
                    tag.decompose()
                
                # Check if it's a product page
                is_product = self.is_product_url(current_url)
                
                # Extract products from this page
                page_products = self.extract_products_from_page(soup, current_url)
                
                if page_products:
                    # Add page URL to each product
                    for p in page_products:
                        p['page_url'] = current_url
                        p['discovered_at'] = datetime.now().isoformat()
                    
                    # Add to collection
                    self.all_products.extend(page_products)
                    products_found += len(page_products)
                    
                    print(f"   ✅ Found {len(page_products)} products (Total: {products_found})")
                    
                    # Show sample
                    for p in page_products[:3]:
                        price_str = f" - ${p.get('price')}" if p.get('price') else ""
                        print(f"      • {p.get('name', 'Unknown')[:50]}{price_str}")
                
                # Extract page data
                page_data = self.extract_page_data(current_url, soup)
                page_data['product_count'] = len(page_products)
                page_data['is_product_page'] = is_product
                page_data['scraped_at'] = datetime.now().isoformat()
                self.all_pages.append(page_data)
                
                # Find all links to follow
                domain = urlparse(start_url).netloc
                new_links = 0
                
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    
                    # Skip empty or javascript links
                    if not href or href.startswith('#') or href.startswith('javascript:'):
                        continue
                    
                    # Convert to absolute URL
                    absolute_url = self.get_absolute_url(href, current_url)
                    
                    # Only follow same domain links
                    if not absolute_url or not self.is_same_domain(absolute_url, start_url):
                        continue
                    
                    # Check if it's a product or category page (prioritize)
                    is_product_link = self.is_product_url(absolute_url)
                    is_category_link = self.is_category_url(absolute_url)
                    
                    # Add to queue if not visited
                    if absolute_url not in self.visited_urls and absolute_url not in urls_to_visit:
                        # Prioritize product and category pages
                        if is_product_link:
                            urls_to_visit.appendleft(absolute_url)  # High priority
                            new_links += 1
                        elif is_category_link:
                            urls_to_visit.append(absolute_url)  # Medium priority
                            new_links += 1
                        elif len(urls_to_visit) < max_pages * 2:
                            urls_to_visit.append(absolute_url)  # Low priority
                            new_links += 1
                
                print(f"   🔗 Found {new_links} new URLs to crawl")
                print(f"   📊 Queue: {len(urls_to_visit)} URLs remaining")
                
                pages_scraped += 1
                
                # Small delay to be polite
                time.sleep(0.5)
                
            except Exception as e:
                print(f"   ❌ Error: {str(e)[:100]}")
                continue
        
        # Final stats
        print(f"\n{'='*60}")
        print(f"✅ CRAWLING COMPLETE!")
        print(f"📊 Pages Scraped: {pages_scraped}")
        print(f"📦 Products Found: {products_found}")
        print(f"🎯 Categories Found: {categories_found}")
        print(f"{'='*60}\n")
        
        # Remove duplicates by URL
        unique_products = []
        seen_urls = set()
        for p in self.all_products:
            url = p.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_products.append(p)
            elif not url:
                unique_products.append(p)
        
        self.all_products = unique_products
        
        return {
            'success': True,
            'pages_scraped': pages_scraped,
            'total_products': len(self.all_products),
            'start_url': start_url,
            'products': self.all_products,
            'pages': self.all_pages,
            'scraped_at': datetime.now().isoformat()
        }
    
    # ---------- MAIN SCRAPE FUNCTION ----------
    def scrape_website(self, url, mode="comprehensive", max_pages=500, max_products=5000):
        """
        Main scraping function - full website scrape karta hai
        mode: 'basic', 'smart', 'comprehensive'
        max_pages: Maximum pages to crawl
        max_products: Maximum products to collect
        """
        start_time = time.time()
        
        try:
            # Normalize URL
            if not url.startswith('http'):
                url = 'https://' + url
            
            print(f"\n{'='*60}")
            print(f"🕷️  ULTRA SCRAPER v4.0 - PROFESSIONAL EDITION")
            print(f"📌 URL: {url}")
            print(f"⚙️  Mode: {mode}")
            print(f"📊 Max Pages: {max_pages}")
            print(f"📦 Max Products: {max_products}")
            print(f"{'='*60}")
            
            # Crawl website
            crawl_result = self.crawl_website(url, max_pages, max_products)
            
            if not crawl_result['success']:
                return {'error': 'Crawling failed'}
            
            # Prepare result based on mode
            if mode == "basic":
                # Basic mode - only essential info
                result = {
                    'scrape_id': str(uuid.uuid4()),
                    'url': url,
                    'total_products': crawl_result['total_products'],
                    'products': crawl_result['products'][:100],  # Max 100 products
                    'pages_scraped': crawl_result['pages_scraped'],
                    'stats': {
                        'total_products': crawl_result['total_products'],
                        'pages_scraped': crawl_result['pages_scraped'],
                        'scrape_time': round(time.time() - start_time, 2)
                    },
                    'scraped_at': datetime.now().isoformat()
                }
            
            elif mode == "smart":
                # Smart mode - moderate details
                result = {
                    'scrape_id': str(uuid.uuid4()),
                    'url': url,
                    'total_products': crawl_result['total_products'],
                    'products': crawl_result['products'][:500],  # Max 500 products
                    'pages': crawl_result['pages'][:50],  # Max 50 pages
                    'stats': {
                        'total_products': crawl_result['total_products'],
                        'pages_scraped': crawl_result['pages_scraped'],
                        'average_products_per_page': round(crawl_result['total_products'] / max(1, crawl_result['pages_scraped']), 2),
                        'scrape_time': round(time.time() - start_time, 2)
                    },
                    'scraped_at': datetime.now().isoformat()
                }
            
            else:
                # Comprehensive mode - everything
                result = {
                    'scrape_id': str(uuid.uuid4()),
                    'url': url,
                    'total_products': crawl_result['total_products'],
                    'products': crawl_result['products'],
                    'pages': crawl_result['pages'],
                    'stats': {
                        'total_products': crawl_result['total_products'],
                        'pages_scraped': crawl_result['pages_scraped'],
                        'average_products_per_page': round(crawl_result['total_products'] / max(1, crawl_result['pages_scraped']), 2),
                        'product_urls_found': len([p for p in crawl_result['products'] if p.get('url')]),
                        'products_with_prices': len([p for p in crawl_result['products'] if p.get('price')]),
                        'products_with_images': len([p for p in crawl_result['products'] if p.get('image')]),
                        'scrape_time': round(time.time() - start_time, 2)
                    },
                    'scraped_at': datetime.now().isoformat()
                }
            
            print(f"\n{'='*60}")
            print(f"✅ SCRAPING COMPLETED SUCCESSFULLY!")
            print(f"📦 Total Products: {result['total_products']}")
            print(f"📊 Pages Scraped: {result['stats']['pages_scraped']}")
            print(f"⏱️  Time Taken: {result['stats']['scrape_time']} seconds")
            print(f"{'='*60}\n")
            
            return result
            
        except Exception as e:
            error_msg = f"Scraping failed: {str(e)}"
            print(f"\n❌ ERROR: {error_msg}\n")
            return {'error': error_msg}
    
    # ---------- EXPORT FUNCTIONS ----------
    def save_as_json(self, data, filename):
        """Save data as JSON file"""
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ JSON saved: {filepath}")
        return filepath
    
    def save_as_csv(self, data, filename):
        """Save products as CSV file"""
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.csv")
        
        # Extract products
        products = data.get('products', [])
        
        if not products:
            # Create empty CSV with headers
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Name', 'Price', 'URL', 'Image', 'Description', 'SKU', 'Category', 'Rating'])
            return filepath
        
        # Determine all possible fields
        all_fields = set()
        for p in products:
            all_fields.update(p.keys())
        
        # Preferred field order
        field_order = ['name', 'price', 'url', 'image', 'description', 'sku', 'category', 'rating', 'review_count', 'stock_status', 'brand', 'page_url']
        fields = [f for f in field_order if f in all_fields]
        fields.extend([f for f in all_fields if f not in field_order])
        
        # Write CSV
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for product in products:
                # Filter to only our fields
                row = {k: product.get(k, '') for k in fields}
                writer.writerow(row)
        
        print(f"✅ CSV saved: {filepath} ({len(products)} products)")
        return filepath
    
    def save_as_excel(self, data, filename):
        """Save data as Excel file with multiple sheets"""
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.xlsx")
        
        # Create Excel file
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Products sheet
            products = data.get('products', [])
            if products:
                df_products = pd.DataFrame(products)
                df_products.to_excel(writer, sheet_name='Products', index=False)
            
            # Summary sheet
            summary_data = {
                'Property': ['URL', 'Total Products', 'Pages Scraped', 'Scraped At'],
                'Value': [
                    data.get('url', ''),
                    data.get('total_products', 0),
                    data.get('stats', {}).get('pages_scraped', 0),
                    data.get('scraped_at', '')
                ]
            }
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name='Summary', index=False)
            
            # Stats sheet
            if data.get('stats'):
                stats_data = []
                for key, value in data['stats'].items():
                    stats_data.append({'Statistic': key, 'Value': value})
                df_stats = pd.DataFrame(stats_data)
                df_stats.to_excel(writer, sheet_name='Statistics', index=False)
            
            # Pages sheet
            pages = data.get('pages', [])
            if pages:
                df_pages = pd.DataFrame(pages)
                df_pages.to_excel(writer, sheet_name='Pages', index=False)
        
        print(f"✅ Excel saved: {filepath}")
        return filepath
    
    def save_as_text(self, data, filename):
        """Save data as formatted text file"""
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.txt")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("AI SCRAPER - PROFESSIONAL EDITION\n")
            f.write("="*80 + "\n\n")
            
            f.write(f"URL: {data.get('url', 'N/A')}\n")
            f.write(f"Total Products: {data.get('total_products', 0)}\n")
            f.write(f"Pages Scraped: {data.get('stats', {}).get('pages_scraped', 0)}\n")
            f.write(f"Scraped At: {data.get('scraped_at', 'N/A')}\n\n")
            
            f.write("="*80 + "\n")
            f.write("PRODUCTS\n")
            f.write("="*80 + "\n\n")
            
            products = data.get('products', [])
            for i, product in enumerate(products, 1):
                f.write(f"Product #{i}\n")
                f.write("-"*40 + "\n")
                
                if product.get('name'):
                    f.write(f"Name: {product['name']}\n")
                if product.get('price'):
                    f.write(f"Price: ${product['price']}\n")
                if product.get('url'):
                    f.write(f"URL: {product['url']}\n")
                if product.get('image'):
                    f.write(f"Image: {product['image']}\n")
                if product.get('description'):
                    f.write(f"Description: {product['description'][:200]}...\n")
                if product.get('sku'):
                    f.write(f"SKU: {product['sku']}\n")
                if product.get('category'):
                    f.write(f"Category: {product['category']}\n")
                if product.get('rating'):
                    f.write(f"Rating: {product['rating']}/5\n")
                
                f.write("\n")
        
        print(f"✅ Text file saved: {filepath}")
        return filepath
    
    def save_as_pdf(self, data, filename):
        """Save data as PDF file"""
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.pdf")
        
        pdf = FPDF()
        pdf.add_page()
        
        # Title
        pdf.set_font("Arial", size=20, style='B')
        pdf.cell(0, 15, "AI SCRAPER - PROFESSIONAL EDITION", ln=True, align='C')
        pdf.set_font("Arial", size=16, style='B')
        pdf.cell(0, 10, "Complete Website Scrape Results", ln=True, align='C')
        pdf.ln(10)
        
        # Summary
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 8, f"URL: {data.get('url', 'N/A')}", ln=True)
        pdf.cell(0, 8, f"Total Products: {data.get('total_products', 0)}", ln=True)
        pdf.cell(0, 8, f"Pages Scraped: {data.get('stats', {}).get('pages_scraped', 0)}", ln=True)
        pdf.cell(0, 8, f"Scraped At: {data.get('scraped_at', 'N/A')}", ln=True)
        pdf.ln(10)
        
        # Products
        pdf.set_font("Arial", size=14, style='B')
        pdf.cell(0, 10, "Products Found:", ln=True)
        pdf.ln(5)
        
        products = data.get('products', [])
        for i, product in enumerate(products[:50], 1):  # Max 50 products in PDF
            pdf.set_font("Arial", size=12, style='B')
            
            # Check if we need a new page
            if pdf.get_y() > 250:
                pdf.add_page()
            
            pdf.cell(0, 8, f"Product #{i}: {product.get('name', 'Unknown')[:50]}", ln=True)
            pdf.set_font("Arial", size=10)
            
            if product.get('price'):
                pdf.cell(0, 6, f"Price: ${product['price']}", ln=True)
            if product.get('url'):
                # URL ko shorten karo
                url_short = product['url'][:70] + "..." if len(product['url']) > 70 else product['url']
                pdf.cell(0, 6, f"URL: {url_short}", ln=True)
            if product.get('description'):
                desc_short = product['description'][:100] + "..." if len(product['description']) > 100 else product['description']
                pdf.multi_cell(0, 6, f"Description: {desc_short}")
            
            pdf.ln(5)
        
        pdf.output(filepath)
        print(f"✅ PDF saved: {filepath}")
        return filepath