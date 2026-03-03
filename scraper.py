import requests                     # HTTP requests bhejne ke liye
import re                           # regex matching ke liye
import time                         # time tracking ke liye
import uuid                         # unique scrape id banane ke liye
import os                           # file system operations ke liye
import json                         # JSON export ke liye
import csv                          # CSV export ke liye
import queue                        # BFS queue ke liye
import urllib3                      # SSL warnings disable karne ke liye
from bs4 import BeautifulSoup       # HTML parse karne ke liye
from urllib.parse import urljoin, urlparse
from datetime import datetime
import pandas as pd
from fpdf import FPDF

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class UltraWebsiteCrawler:

    def __init__(self):
        # Session create karte hain taake har request same connection use kare
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self.session.verify = False

        # visited URLs store karne ke liye set
        self.visited = set()

        # products store karne ke liye list
        self.products = []

        # duplicate products avoid karne ke liye
        self.product_urls = set()

    # ---------------- CLEAN TEXT ----------------
    def clean(self, text):
        # extra spaces remove karta hai
        return re.sub(r"\s+", " ", text).strip() if text else ""

    # ---------------- IS PRODUCT PAGE ----------------
    def is_product_page(self, soup, url):
        """
        Yeh function check karta hai ke page product page hai ya nahi
        Common ecommerce patterns check karta hai
        """

        text = soup.get_text().lower()

        product_keywords = [
            "add to cart",
            "buy now",
            "price",
            "sku",
            "product description",
            "rating"
        ]

        # agar keywords kaafi mil jayein to product page samjhenge
        score = sum(1 for k in product_keywords if k in text)

        return score >= 2  # minimum 2 signals required

    # ---------------- EXTRACT PRODUCT ----------------
    def extract_product(self, soup, url):
        """
        Product data extract karta hai
        """

        product = {}

        # Product URL
        product["url"] = url

        # Name detect karne ki koshish
        title = soup.find("h1")
        product["name"] = self.clean(title.get_text()) if title else ""

        # Price detect karne ki koshish
        price_text = soup.find(text=re.compile(r"\$|€|£|Rs|PKR"))
        product["price"] = self.clean(price_text) if price_text else ""

        # Image detect
        img = soup.find("img")
        product["image"] = urljoin(url, img["src"]) if img and img.get("src") else ""

        # Description
        desc = soup.find("p")
        product["description"] = self.clean(desc.get_text()) if desc else ""

        # SKU detect
        sku = soup.find(text=re.compile("sku", re.I))
        product["sku"] = self.clean(sku) if sku else ""

        # Rating detect
        rating = soup.find(text=re.compile("rating", re.I))
        product["rating"] = self.clean(rating) if rating else ""

        return product

    # ---------------- BFS WEBSITE CRAWLER ----------------
    def crawl_website(self, base_url, max_pages=500):
        """
        BFS algorithm se poori website crawl karta hai
        """

        if not base_url.startswith("http"):
            base_url = "https://" + base_url

        domain = urlparse(base_url).netloc

        q = queue.Queue()
        q.put(base_url)

        self.visited.add(base_url)

        print(f"🚀 Crawling started on {base_url}")

        while not q.empty() and len(self.visited) < max_pages:

            current_url = q.get()

            try:
                r = self.session.get(current_url, timeout=15)
                soup = BeautifulSoup(r.text, "html.parser")

                print(f"🔎 Crawling: {current_url}")

                # Product detection
                if self.is_product_page(soup, current_url):
                    if current_url not in self.product_urls:
                        product = self.extract_product(soup, current_url)
                        self.products.append(product)
                        self.product_urls.add(current_url)
                        print(f"🛒 Product Found: {product.get('name')}")

                # Internal links collect karo
                for a in soup.find_all("a", href=True):
                    link = urljoin(current_url, a["href"])
                    parsed = urlparse(link)

                    if parsed.netloc == domain:
                        if link not in self.visited:
                            self.visited.add(link)
                            q.put(link)

            except Exception as e:
                print(f"❌ Error: {e}")

        print(f"✅ Crawling Finished. Total Products: {len(self.products)}")

        return {
            "scrape_id": str(uuid.uuid4()),
            "base_url": base_url,
            "total_products": len(self.products),
            "products": self.products,
            "scraped_at": datetime.now().isoformat()
        }

    # ---------------- EXPORT JSON ----------------
    def save_json(self, data, filename):
        os.makedirs("downloads", exist_ok=True)
        path = f"downloads/{filename}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    # ---------------- EXPORT CSV ----------------
    def save_csv(self, data, filename):
        os.makedirs("downloads", exist_ok=True)
        path = f"downloads/{filename}.csv"

        keys = data["products"][0].keys() if data["products"] else []

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data["products"])

        return path

    # ---------------- EXPORT EXCEL ----------------
    def save_excel(self, data, filename):
        os.makedirs("downloads", exist_ok=True)
        path = f"downloads/{filename}.xlsx"
        df = pd.DataFrame(data["products"])
        df.to_excel(path, index=False)
        return path

    # ---------------- EXPORT PDF ----------------
    def save_pdf(self, data, filename):
        os.makedirs("downloads", exist_ok=True)
        path = f"downloads/{filename}.pdf"

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=10)

        for p in data["products"]:
            pdf.multi_cell(0, 6, f"Name: {p.get('name')}")
            pdf.multi_cell(0, 6, f"Price: {p.get('price')}")
            pdf.multi_cell(0, 6, f"URL: {p.get('url')}")
            pdf.ln(5)

        pdf.output(path)
        return path

    # ---------------- EXPORT TEXT ----------------
    def save_txt(self, data, filename):
        os.makedirs("downloads", exist_ok=True)
        path = f"downloads/{filename}.txt"
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"AI SCRAPER - WEBSITE CRAWL RESULTS\n")
            f.write(f"="*50 + "\n\n")
            f.write(f"Base URL: {data.get('base_url', 'N/A')}\n")
            f.write(f"Total Products: {data.get('total_products', 0)}\n")
            f.write(f"Scraped At: {data.get('scraped_at', 'N/A')}\n\n")
            f.write(f"="*50 + "\n")
            f.write(f"PRODUCTS:\n")
            f.write(f"="*50 + "\n\n")
            
            for i, product in enumerate(data.get("products", []), 1):
                f.write(f"{i}. {product.get('name', 'Unknown')}\n")
                if product.get('price'):
                    f.write(f"   Price: {product['price']}\n")
                if product.get('url'):
                    f.write(f"   URL: {product['url']}\n")
                if product.get('description'):
                    f.write(f"   Description: {product['description'][:100]}...\n")
                f.write("\n")
        
        return path