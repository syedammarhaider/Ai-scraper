import requests
import re
import time
import uuid
import csv
import os
import json
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
from datetime import datetime
from fpdf import FPDF
import pandas as pd
from typing import List, Dict, Any
import concurrent.futures

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class UltraScraper:

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        })
        self.session.verify = False
        self.visited_urls = set()
        self.all_products = []
        self.product_urls = set()
        self.domain = ""

    # ---------- UTILS ----------
    def clean(self, text):
        return re.sub(r"\s+", " ", text).strip() if text else ""

    def abs_url(self, url, base):
        if not url:
            return ""
        if url.startswith(('http://', 'https://')):
            return url
        return urljoin(base, url)

    def remove_empty(self, data):
        return {k: v for k, v in data.items() if v not in ("", None, [], {})}

    def is_product_url(self, url: str) -> bool:
        """Detect if URL is likely a product page"""
        url_lower = url.lower()
        product_patterns = [
            '/product/', '/products/', '/item/', '/items/', '/p/', '/prod/',
            '/shop/', '/buy/', '/detail/', '/view/', '?product=', '&product=',
            '/dp/', '/gp/product/', '/itm/', '/pd/', '-p-', '_p/',
            '/catalog/', '/collection/', '/collections/'
        ]
        
        # Common e-commerce platforms patterns
        if any(pattern in url_lower for pattern in product_patterns):
            return True
        
        # Check URL structure for common product patterns
        parsed = urlparse(url)
        path_parts = parsed.path.split('/')
        
        # If URL has numbers and looks like a product ID
        if len(path_parts) > 2:
            last_part = path_parts[-1]
            if re.search(r'\d{5,}', last_part) or re.search(r'[A-Z0-9]{8,}', last_part):
                return True
        
        return False

    def extract_product_urls_from_page(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract all product URLs from a page"""
        product_urls = []
        
        # Find all links
        for a in soup.find_all('a', href=True):
            href = a['href']
            full_url = self.abs_url(href, base_url)
            
            # Only process URLs from same domain
            if self.domain and self.domain not in full_url:
                continue
            
            if self.is_product_url(full_url) and full_url not in self.product_urls:
                product_urls.append(full_url)
                self.product_urls.add(full_url)
        
        return product_urls

    def find_pagination_urls(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Find all pagination links"""
        pagination_urls = []
        
        # Common pagination selectors
        pagination_selectors = [
            'a[href*="page"]', 'a[href*="Page"]', 'a[href*="pagination"]',
            'a.next', 'a[rel="next"]', '.pagination a', '.pages a',
            '.pager a', 'a[href*="?page="]', 'a[href*="&page="]',
            'a[href*="/page/"]', 'a[href*="/Page/"]', '.load-more a'
        ]
        
        for selector in pagination_selectors:
            for link in soup.select(selector):
                href = link.get('href')
                if href:
                    full_url = self.abs_url(href, base_url)
                    if self.domain in full_url and full_url not in self.visited_urls:
                        pagination_urls.append(full_url)
        
        return pagination_urls

    def scrape_product_page(self, url: str) -> Dict[str, Any]:
        """Scrape a single product page"""
        try:
            print(f"📦 Scraping product: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove scripts/styles
            for tag in soup(["script", "style", "noscript", "iframe"]):
                tag.decompose()
            
            # Extract product data
            product_data = {
                "product_url": url,
                "title": self.extract_product_title(soup),
                "price": self.extract_price(soup),
                "description": self.extract_description(soup),
                "images": self.extract_product_images(soup, url),
                "specifications": self.extract_specifications(soup),
                "availability": self.extract_availability(soup),
                "rating": self.extract_rating(soup),
                "reviews_count": self.extract_reviews_count(soup),
                "sku": self.extract_sku(soup),
                "brand": self.extract_brand(soup),
                "categories": self.extract_categories(soup, url),
                "features": self.extract_features(soup),
                "variants": self.extract_variants(soup),
                "meta_data": self.extract_meta_data(soup),
                "scraped_at": datetime.now().isoformat()
            }
            
            return self.remove_empty(product_data)
            
        except Exception as e:
            print(f"❌ Error scraping {url}: {str(e)}")
            return {
                "product_url": url,
                "error": str(e),
                "scraped_at": datetime.now().isoformat()
            }

    def extract_product_title(self, soup: BeautifulSoup) -> str:
        """Extract product title"""
        # Try common title selectors
        selectors = [
            'h1[class*="product"]', 'h1[class*="title"]', '.product-title',
            '.product-name', '.item-title', '[class*="product-title"]',
            '[class*="product-name"]', 'h1', 'title'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return self.clean(element.get_text())
        
        return ""

    def extract_price(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract product price"""
        price_data = {
            "current_price": None,
            "original_price": None,
            "currency": "USD"
        }
        
        # Common price selectors
        current_selectors = [
            '[class*="price"] [class*="current"]', '[class*="price"] [class*="sale"]',
            '[class*="product-price"]', '[class*="offer-price"]', '[itemprop="price"]',
            '.price', '.sale-price', '.current-price', '[class*="price-now"]'
        ]
        
        original_selectors = [
            '[class*="price"] [class*="original"]', '[class*="price"] [class*="old"]',
            '.old-price', '.original-price', '.regular-price', '[class*="price-was"]',
            '[class*="compare-price"]'
        ]
        
        # Extract current price
        for selector in current_selectors:
            element = soup.select_one(selector)
            if element:
                price_text = self.clean(element.get_text())
                price_match = re.search(r'[\d,]+(?:\.\d{2})?', price_text.replace(',', ''))
                if price_match:
                    price_data["current_price"] = float(price_match.group().replace(',', ''))
                    break
        
        # Extract original price
        for selector in original_selectors:
            element = soup.select_one(selector)
            if element:
                price_text = self.clean(element.get_text())
                price_match = re.search(r'[\d,]+(?:\.\d{2})?', price_text.replace(',', ''))
                if price_match:
                    price_data["original_price"] = float(price_match.group().replace(',', ''))
                    break
        
        # Detect currency
        page_text = soup.get_text()
        currency_symbols = {'$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY', '₹': 'INR', '₽': 'RUB'}
        for symbol, currency in currency_symbols.items():
            if symbol in page_text[:500]:
                price_data["currency"] = currency
                break
        
        return price_data

    def extract_description(self, soup: BeautifulSoup) -> str:
        """Extract product description"""
        selectors = [
            '[class*="description"]', '[class*="details"]', '[class*="overview"]',
            '[itemprop="description"]', '.product-description', '.product-details',
            '#description', '#details', '.description-content', '.tab-content'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return self.clean(element.get_text())
        
        return ""

    def extract_product_images(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Extract product images"""
        images = []
        
        # Common image selectors
        selectors = [
            '.product-gallery img', '.product-images img', '[class*="gallery"] img',
            '[class*="product-image"]', '[class*="main-image"]', '[class*="thumbnail"] img',
            '.woocommerce-product-gallery__image img', '.swiper-slide img'
        ]
        
        for selector in selectors:
            for img in soup.select(selector):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    full_url = self.abs_url(src, base_url)
                    alt = self.clean(img.get('alt', ''))
                    images.append({
                        "url": full_url,
                        "alt": alt,
                        "type": "main" if not images else "thumbnail"
                    })
        
        # If no images found with selectors, try all images
        if not images:
            for img in soup.find_all('img'):
                src = img.get('src')
                if src and 'logo' not in src.lower():
                    full_url = self.abs_url(src, base_url)
                    alt = self.clean(img.get('alt', ''))
                    images.append({
                        "url": full_url,
                        "alt": alt,
                        "type": "unknown"
                    })
        
        return images[:10]  # Limit to 10 images per product

    def extract_specifications(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract product specifications"""
        specs = []
        
        # Common specs selectors
        spec_tables = soup.select('table[class*="spec"]')
        for table in spec_tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    specs.append({
                        "name": self.clean(cells[0].get_text()),
                        "value": self.clean(cells[1].get_text())
                    })
        
        # Try attribute lists
        attr_selectors = [
            '[class*="spec"] li', '[class*="attribute"] li',
            '.product-attributes li', '.technical-details li'
        ]
        
        for selector in attr_selectors:
            for item in soup.select(selector):
                text = self.clean(item.get_text())
                if ':' in text:
                    parts = text.split(':', 1)
                    specs.append({
                        "name": self.clean(parts[0]),
                        "value": self.clean(parts[1])
                    })
        
        return specs

    def extract_availability(self, soup: BeautifulSoup) -> str:
        """Extract product availability"""
        selectors = [
            '[class*="stock"]', '[class*="availability"]', '.in-stock',
            '.out-of-stock', '[itemprop="availability"]'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return self.clean(element.get_text())
        
        return ""

    def extract_rating(self, soup: BeautifulSoup) -> Dict:
        """Extract product rating"""
        rating_data = {
            "average": None,
            "count": None
        }
        
        # Rating selectors
        avg_selectors = [
            '[itemprop="ratingValue"]', '[class*="rating"] [class*="average"]',
            '.rating-value', '.average-rating', '[class*="score"]'
        ]
        
        count_selectors = [
            '[itemprop="ratingCount"]', '[class*="rating"] [class*="count"]',
            '.review-count', '.rating-count', '[class*="votes"]'
        ]
        
        for selector in avg_selectors:
            element = soup.select_one(selector)
            if element:
                try:
                    rating_data["average"] = float(self.clean(element.get_text()))
                    break
                except:
                    pass
        
        for selector in count_selectors:
            element = soup.select_one(selector)
            if element:
                try:
                    text = self.clean(element.get_text())
                    count_match = re.search(r'\d+', text)
                    if count_match:
                        rating_data["count"] = int(count_match.group())
                    break
                except:
                    pass
        
        return rating_data

    def extract_reviews_count(self, soup: BeautifulSoup) -> int:
        """Extract number of reviews"""
        selectors = [
            '[class*="review"] [class*="count"]', '.reviews-count',
            '[class*="rating"] [class*="count"]', '.review-total'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = self.clean(element.get_text())
                count_match = re.search(r'\d+', text)
                if count_match:
                    return int(count_match.group())
        
        return 0

    def extract_sku(self, soup: BeautifulSoup) -> str:
        """Extract product SKU"""
        selectors = [
            '[itemprop="sku"]', '[class*="sku"]', '.product-sku',
            '.sku', '.product-id', '[class*="product-code"]'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return self.clean(element.get_text())
        
        return ""

    def extract_brand(self, soup: BeautifulSoup) -> str:
        """Extract product brand"""
        selectors = [
            '[itemprop="brand"]', '[class*="brand"]', '.product-brand',
            '.brand-name', '.manufacturer'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return self.clean(element.get_text())
        
        return ""

    def extract_categories(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract product categories"""
        categories = []
        
        # Breadcrumb selectors
        breadcrumb_selectors = [
            '.breadcrumb', '.breadcrumbs', '[class*="breadcrumb"]',
            '.woocommerce-breadcrumb', '.path', '.navigation-path'
        ]
        
        for selector in breadcrumb_selectors:
            breadcrumb = soup.select_one(selector)
            if breadcrumb:
                for link in breadcrumb.find_all('a'):
                    cat = self.clean(link.get_text())
                    if cat and cat not in categories:
                        categories.append(cat)
                break
        
        # If no breadcrumb, try category links
        if not categories:
            cat_links = soup.select('a[href*="category"], a[href*="categoria"], a[href*="collection"]')
            for link in cat_links[:3]:  # Limit to first 3
                cat = self.clean(link.get_text())
                if cat and cat not in categories:
                    categories.append(cat)
        
        return categories

    def extract_features(self, soup: BeautifulSoup) -> List[str]:
        """Extract product features/highlights"""
        features = []
        
        # Feature selectors
        feature_selectors = [
            '[class*="feature"] li', '.product-features li',
            '.key-features li', '.highlights li', '.bullet-points li',
            '[class*="benefits"] li'
        ]
        
        for selector in feature_selectors:
            for item in soup.select(selector):
                feature = self.clean(item.get_text())
                if feature and len(feature) > 10:  # Meaningful features only
                    features.append(feature)
        
        return features[:20]  # Limit to 20 features

    def extract_variants(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract product variants (size, color, etc.)"""
        variants = []
        
        # Variant selectors
        variant_selectors = [
            '[class*="variation"]', '[class*="variant"]',
            '.product-variations', '.variations', '.swatches'
        ]
        
        for selector in variant_selectors:
            variant_container = soup.select_one(selector)
            if variant_container:
                # Try to find different variant types
                for label in variant_container.find_all(['label', 'span']):
                    variant_text = self.clean(label.get_text())
                    if variant_text and len(variant_text) < 50:
                        variants.append({
                            "type": "option",
                            "value": variant_text
                        })
        
        return variants

    def extract_meta_data(self, soup: BeautifulSoup) -> Dict:
        """Extract meta data"""
        meta_data = {}
        
        # Meta tags
        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property')
            content = meta.get('content')
            if name and content:
                meta_data[name] = content
        
        return meta_data

    def crawl_website(self, start_url: str, max_pages: int = 100) -> List[Dict]:
        """Crawl entire website and extract all products"""
        print(f"🚀 Starting full site crawl: {start_url}")
        start_time = time.time()
        
        if not start_url.startswith('http'):
            start_url = 'https://' + start_url
        
        self.domain = urlparse(start_url).netloc
        urls_to_visit = [start_url]
        self.visited_urls = set()
        self.product_urls = set()
        self.all_products = []
        
        page_count = 0
        
        while urls_to_visit and page_count < max_pages:
            current_url = urls_to_visit.pop(0)
            
            if current_url in self.visited_urls:
                continue
            
            try:
                print(f"🌐 Crawling ({page_count + 1}/{max_pages}): {current_url}")
                
                response = self.session.get(current_url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                
                self.visited_urls.add(current_url)
                page_count += 1
                
                # Extract product URLs from this page
                new_product_urls = self.extract_product_urls_from_page(soup, current_url)
                for product_url in new_product_urls:
                    if product_url not in self.product_urls:
                        self.product_urls.add(product_url)
                
                # Find pagination links
                pagination_urls = self.find_pagination_urls(soup, current_url)
                for pag_url in pagination_urls:
                    if pag_url not in self.visited_urls and pag_url not in urls_to_visit:
                        urls_to_visit.append(pag_url)
                
                # Also look for category/collection links
                category_links = soup.select('a[href*="category"], a[href*="collection"], a[href*="catalog"]')
                for cat_link in category_links:
                    href = cat_link.get('href')
                    if href:
                        full_url = self.abs_url(href, current_url)
                        if self.domain in full_url and full_url not in self.visited_urls and full_url not in urls_to_visit:
                            urls_to_visit.append(full_url)
                
            except Exception as e:
                print(f"❌ Error crawling {current_url}: {str(e)}")
                self.visited_urls.add(current_url)
        
        print(f"\n📊 Found {len(self.product_urls)} product URLs")
        
        # Scrape all products (with threading for speed)
        print("🔄 Scraping all products...")
        
        # Use ThreadPoolExecutor for concurrent scraping
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {executor.submit(self.scrape_product_page, url): url 
                           for url in list(self.product_urls)}
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    product_data = future.result()
                    if product_data and 'error' not in product_data:
                        self.all_products.append(product_data)
                        print(f"✅ Scraped: {product_data.get('title', url)[:50]}")
                    else:
                        print(f"⚠️ Failed: {url}")
                except Exception as e:
                    print(f"❌ Error processing {url}: {str(e)}")
        
        elapsed_time = round(time.time() - start_time, 2)
        print(f"\n✅ Crawl completed in {elapsed_time} seconds")
        print(f"📦 Total products scraped: {len(self.all_products)}")
        
        return self.all_products

    # ---------- MAIN SCRAPE FUNCTION ----------
    def scrape_website(self, url, mode="comprehensive"):
        start = time.time()
        
        try:
            if not url.startswith("http"):
                url = "https://" + url
            
            # For comprehensive mode, crawl the entire site
            if mode == "comprehensive" or mode == "full-site":
                products = self.crawl_website(url)
                
                # Compile final data
                data = {
                    "scrape_id": str(uuid.uuid4()),
                    "site_url": url,
                    "domain": self.domain,
                    "total_products_found": len(self.product_urls),
                    "total_products_scraped": len(products),
                    "products": products,
                    "stats": {
                        "total_pages_crawled": len(self.visited_urls),
                        "success_rate": round((len(products) / len(self.product_urls) * 100) if self.product_urls else 0, 2),
                        "scrape_time": round(time.time() - start, 2),
                        "products_per_second": round(len(products) / (time.time() - start), 2) if products else 0
                    },
                    "scraped_at": datetime.now().isoformat()
                }
                
                return self.remove_empty(data)
            
            else:
                # Original single page scraping for other modes
                return self.scrape_single_page(url, mode, start)
                
        except Exception as e:
            return {"error": str(e)}

    def scrape_single_page(self, url, mode, start):
        """Original single page scraping method"""
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

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
        headings = {f"h{i}": [self.clean(h.get_text()) for h in soup.find_all(f"h{i}") if h.get_text()]
                    for i in range(1, 7)}

        # Paragraphs
        paragraphs = [self.clean(p.get_text()) for p in soup.find_all("p") if len(p.get_text()) > 30]

        # Structured data
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
            data = {
                "scrape_id": str(uuid.uuid4()),
                "url": url,
                "title": title,
                "description": description,
                "paragraphs": paragraphs[:5],
                "stats": {
                    "paragraph_count": len(paragraphs[:5]),
                    "scrape_time": round(time.time() - start, 2)
                },
                "scraped_at": datetime.now().isoformat()
            }
        elif mode == "smart":
            data = {
                "scrape_id": str(uuid.uuid4()),
                "url": url,
                "title": title,
                "description": description,
                "headings": {k: v[:3] for k, v in headings.items()},
                "paragraphs": paragraphs[:10],
                "images": images[:5],
                "stats": {
                    "paragraph_count": len(paragraphs[:10]),
                    "image_count": len(images[:5]),
                    "scrape_time": round(time.time() - start, 2)
                },
                "scraped_at": datetime.now().isoformat()
            }
        else:
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
        
        # Prepare CSV data - flatten product structure
        csv_rows = []
        
        # Header
        headers = ['Product URL', 'Title', 'Current Price', 'Original Price', 'Currency', 
                   'Description', 'Brand', 'SKU', 'Availability', 'Rating', 'Reviews Count',
                   'Categories', 'Features', 'Scraped At']
        csv_rows.append(headers)
        
        # Add products
        if 'products' in data:
            for product in data['products']:
                price_data = product.get('price', {})
                row = [
                    product.get('product_url', ''),
                    product.get('title', ''),
                    price_data.get('current_price', ''),
                    price_data.get('original_price', ''),
                    price_data.get('currency', 'USD'),
                    product.get('description', '')[:200] + '...' if len(product.get('description', '')) > 200 else product.get('description', ''),
                    product.get('brand', ''),
                    product.get('sku', ''),
                    product.get('availability', ''),
                    product.get('rating', {}).get('average', ''),
                    product.get('rating', {}).get('count', ''),
                    ', '.join(product.get('categories', [])),
                    ', '.join(product.get('features', []))[:200],
                    product.get('scraped_at', '')
                ]
                csv_rows.append(row)
        else:
            # Single page data
            row = [
                data.get('url', ''),
                data.get('title', ''),
                '', '', 'USD',
                data.get('description', '')[:200],
                '', '', '',
                '', '',
                '', '',
                data.get('scraped_at', '')
            ]
            csv_rows.append(row)
        
        # Write to CSV
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(csv_rows)
        
        return filepath

    def save_as_excel(self, data, filename):
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.xlsx")
        
        # Create Excel workbook
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            if 'products' in data:
                # Products sheet
                products_data = []
                for product in data['products']:
                    price = product.get('price', {})
                    products_data.append({
                        'Product URL': product.get('product_url', ''),
                        'Title': product.get('title', ''),
                        'Current Price': price.get('current_price', ''),
                        'Original Price': price.get('original_price', ''),
                        'Currency': price.get('currency', 'USD'),
                        'Brand': product.get('brand', ''),
                        'SKU': product.get('sku', ''),
                        'Availability': product.get('availability', ''),
                        'Rating': product.get('rating', {}).get('average', ''),
                        'Reviews Count': product.get('rating', {}).get('count', 0),
                        'Categories': ', '.join(product.get('categories', [])),
                        'Scraped At': product.get('scraped_at', '')
                    })
                
                pd.DataFrame(products_data).to_excel(writer, sheet_name='Products', index=False)
                
                # Summary sheet
                summary_data = {
                    'Metric': ['Site URL', 'Domain', 'Total Products Found', 'Total Products Scraped', 
                              'Pages Crawled', 'Success Rate', 'Scrape Time (s)'],
                    'Value': [
                        data.get('site_url', ''),
                        data.get('domain', ''),
                        data.get('total_products_found', 0),
                        data.get('total_products_scraped', 0),
                        data.get('stats', {}).get('total_pages_crawled', 0),
                        f"{data.get('stats', {}).get('success_rate', 0)}%",
                        data.get('stats', {}).get('scrape_time', 0)
                    ]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
            else:
                # Single page data
                pd.DataFrame([data]).to_excel(writer, sheet_name='Data', index=False)
        
        return filepath

    def save_as_text(self, data, filename):
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.txt")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            if 'products' in data:
                # Site summary
                f.write("=" * 80 + "\n")
                f.write(f"SITE SCRAPE REPORT\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"Site URL: {data.get('site_url', 'N/A')}\n")
                f.write(f"Domain: {data.get('domain', 'N/A')}\n")
                f.write(f"Total Products Found: {data.get('total_products_found', 0)}\n")
                f.write(f"Total Products Scraped: {data.get('total_products_scraped', 0)}\n")
                f.write(f"Pages Crawled: {data.get('stats', {}).get('total_pages_crawled', 0)}\n")
                f.write(f"Success Rate: {data.get('stats', {}).get('success_rate', 0)}%\n")
                f.write(f"Scrape Time: {data.get('stats', {}).get('scrape_time', 0)} seconds\n")
                f.write(f"Scraped At: {data.get('scraped_at', 'N/A')}\n\n")
                
                # Products
                for i, product in enumerate(data.get('products', []), 1):
                    f.write("-" * 80 + "\n")
                    f.write(f"PRODUCT #{i}\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"Title: {product.get('title', 'N/A')}\n")
                    f.write(f"URL: {product.get('product_url', 'N/A')}\n")
                    
                    price = product.get('price', {})
                    if price.get('current_price'):
                        f.write(f"Price: {price.get('currency', 'USD')} {price.get('current_price')}\n")
                        if price.get('original_price'):
                            f.write(f"Original Price: {price.get('currency')} {price.get('original_price')}\n")
                    
                    f.write(f"Brand: {product.get('brand', 'N/A')}\n")
                    f.write(f"SKU: {product.get('sku', 'N/A')}\n")
                    f.write(f"Availability: {product.get('availability', 'N/A')}\n")
                    
                    rating = product.get('rating', {})
                    if rating.get('average'):
                        f.write(f"Rating: {rating.get('average')} ({rating.get('count', 0)} reviews)\n")
                    
                    if product.get('categories'):
                        f.write(f"Categories: {', '.join(product.get('categories', []))}\n")
                    
                    if product.get('features'):
                        f.write("Features:\n")
                        for feature in product.get('features', [])[:10]:
                            f.write(f"  • {feature}\n")
                    
                    if product.get('description'):
                        f.write(f"Description: {product.get('description')[:300]}...\n")
                    
                    f.write("\n")
            else:
                # Single page
                f.write(f"TITLE: {data.get('title', 'N/A')}\n")
                f.write(f"URL: {data.get('url', 'N/A')}\n")
                f.write(f"DESCRIPTION: {data.get('description', 'N/A')}\n")
                f.write(f"SCRAPED AT: {data.get('scraped_at', 'N/A')}\n")
                f.write("=" * 50 + "\n\n")
                
                if data.get('paragraphs'):
                    for para in data['paragraphs']:
                        f.write(f"{para}\n\n")
        
        return filepath

    def save_as_pdf(self, data, filename):
        downloads_dir = "downloads"
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        
        filepath = os.path.join(downloads_dir, f"{filename}.pdf")
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=10)
        
        if 'products' in data:
            # Title
            pdf.set_font("Arial", size=16, style='B')
            pdf.cell(0, 10, f"SITE SCRAPE REPORT: {data.get('domain', '')}", ln=True, align='C')
            pdf.ln(10)
            
            # Summary
            pdf.set_font("Arial", size=12, style='B')
            pdf.cell(0, 10, "SUMMARY", ln=True)
            pdf.set_font("Arial", size=10)
            pdf.cell(0, 8, f"Site URL: {data.get('site_url', 'N/A')}", ln=True)
            pdf.cell(0, 8, f"Total Products: {data.get('total_products_scraped', 0)}", ln=True)
            pdf.cell(0, 8, f"Scrape Time: {data.get('stats', {}).get('scrape_time', 0)}s", ln=True)
            pdf.ln(10)
            
            # Products
            for i, product in enumerate(data.get('products', [])[:50], 1):  # Limit to 50 products for PDF
                pdf.set_font("Arial", size=12, style='B')
                pdf.cell(0, 10, f"Product #{i}: {product.get('title', '')[:50]}", ln=True)
                pdf.set_font("Arial", size=8)
                
                price = product.get('price', {})
                if price.get('current_price'):
                    pdf.cell(0, 6, f"Price: {price.get('currency', 'USD')} {price.get('current_price')}", ln=True)
                
                if product.get('brand'):
                    pdf.cell(0, 6, f"Brand: {product.get('brand')}", ln=True)
                
                if product.get('sku'):
                    pdf.cell(0, 6, f"SKU: {product.get('sku')}", ln=True)
                
                pdf.ln(5)
                
                # Check if we need a new page
                if pdf.get_y() > 250:
                    pdf.add_page()
        else:
            # Single page PDF
            pdf.set_font("Arial", size=16, style='B')
            pdf.cell(0, 10, data.get('title', 'Scraped Data'), ln=True, align='C')
            pdf.ln(10)
            
            pdf.set_font("Arial", size=12)
            pdf.cell(0, 10, f"URL: {data.get('url', 'N/A')}", ln=True)
            pdf.ln(10)
            
            if data.get('paragraphs'):
                pdf.set_font("Arial", size=12, style='B')
                pdf.cell(0, 10, "Content:", ln=True)
                pdf.set_font("Arial", size=10)
                for para in data['paragraphs'][:10]:
                    pdf.multi_cell(0, 6, para)
                    pdf.ln(5)
        
        pdf.output(filepath)
        return filepath