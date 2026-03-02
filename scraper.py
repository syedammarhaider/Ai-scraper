# /app/scraper.py

import requests
import re
import time
import uuid
import os
import json
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
from collections import deque

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class UltraScraper:

    def __init__(self, max_pages=200, max_depth=3):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })
        self.session.verify = False

        self.max_pages = max_pages
        self.max_depth = max_depth

        self.visited = set()
        self.products = []

    # ------------------------------------------------
    # UTILS
    # ------------------------------------------------
    def clean(self, text):
        return re.sub(r"\s+", " ", text).strip() if text else ""

    def abs_url(self, url, base):
        return urljoin(base, url)

    def is_internal(self, base_domain, link):
        return urlparse(link).netloc == base_domain

    def is_product_page(self, soup):
        """
        Simple product detection logic:
        - Has price
        - Has add to cart
        - Has product schema
        """
        text = soup.get_text().lower()

        product_keywords = [
            "add to cart",
            "buy now",
            "price",
            "$",
            "€",
            "£",
        ]

        for keyword in product_keywords:
            if keyword in text:
                return True

        # JSON-LD product schema check
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            if "Product" in script.text:
                return True

        return False

    # ------------------------------------------------
    # PRODUCT SCRAPER
    # ------------------------------------------------
    def extract_product(self, soup, url):

        title = self.clean(soup.title.string) if soup.title else ""

        price = ""
        price_tag = soup.find(string=re.compile(r"\$|\€|\£"))
        if price_tag:
            price = self.clean(price_tag)

        images = [
            self.abs_url(img.get("src"), url)
            for img in soup.find_all("img")
            if img.get("src")
        ]

        description = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            description = self.clean(meta_desc.get("content"))

        return {
            "product_id": str(uuid.uuid4()),
            "url": url,
            "title": title,
            "price": price,
            "description": description,
            "images": images[:5]
        }

    # ------------------------------------------------
    # FULL SITE CRAWLER
    # ------------------------------------------------
    def scrape_entire_site(self, start_url):

        if not start_url.startswith("http"):
            start_url = "https://" + start_url

        base_domain = urlparse(start_url).netloc

        queue = deque()
        queue.append((start_url, 0))

        start_time = time.time()

        while queue and len(self.visited) < self.max_pages:

            current_url, depth = queue.popleft()

            if current_url in self.visited:
                continue

            if depth > self.max_depth:
                continue

            try:
                print(f"Scraping: {current_url}")

                response = self.session.get(current_url, timeout=20)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                self.visited.add(current_url)

                # Check if product page
                if self.is_product_page(soup):
                    product_data = self.extract_product(soup, current_url)
                    self.products.append(product_data)

                # Discover internal links
                for a in soup.find_all("a", href=True):
                    link = self.abs_url(a["href"], current_url)

                    if self.is_internal(base_domain, link):
                        if link not in self.visited:
                            queue.append((link, depth + 1))

            except Exception:
                continue

        return {
            "scrape_id": str(uuid.uuid4()),
            "base_url": start_url,
            "total_pages_crawled": len(self.visited),
            "total_products_found": len(self.products),
            "products": self.products,
            "scraped_at": datetime.now().isoformat(),
            "scrape_time": round(time.time() - start_time, 2)
        }

    # ------------------------------------------------
    # SAVE JSON
    # ------------------------------------------------
    def save_as_json(self, data, filename):

        downloads_dir = os.path.join(os.getcwd(), "downloads")

        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)

        filepath = os.path.join(downloads_dir, f"{filename}.json")

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return filepath