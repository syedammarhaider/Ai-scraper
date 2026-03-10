import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import asyncio

# ---------------- Existing single-page scraper (UNCHANGED) ---------------- #
async def scrape_website(url: str):
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    data = {
        "url": url,
        "title": soup.title.string.strip() if soup.title else "",
        "meta_description": "",
        "headings": {"h1": [], "h2": [], "h3": [], "h4": [], "h5": [], "h6": []},
        "paragraphs": [],
        "links": [],
        "lists": [],
        "images": [],
        "tables": []
    }

    # Meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        data["meta_description"] = meta["content"]

    # Headings by level
    for level in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        for tag in soup.find_all(level):
            text = tag.get_text(strip=True)
            if text:
                data["headings"][level].append(text)

    # Paragraphs (clean and complete)
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text and len(text) > 10:  # Only meaningful paragraphs
            data["paragraphs"].append(text)

    # Links
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if href and text:
            data["links"].append({
                "url": urljoin(url, href),
                "text": text
            })

    # Lists
    for ul in soup.find_all(["ul", "ol"]):
        items = []
        for li in ul.find_all("li"):
            text = li.get_text(strip=True)
            if text:
                items.append(text)
        if items:
            data["lists"].append(items)

    # Images
    for img in soup.find_all("img"):
        src = img.get("src", "")
        alt = img.get("alt", "")
        if src:
            data["images"].append({
                "url": urljoin(url, src),
                "alt": alt
            })

    # Tables
    for table in soup.find_all("table"):
        table_data = []
        for row in table.find_all("tr"):
            row_data = []
            for cell in row.find_all(["td", "th"]):
                text = cell.get_text(strip=True)
                row_data.append(text)
            if row_data:
                table_data.append(row_data)
        if table_data:
            data["tables"].append(table_data)

    # Remove empty fields
    for key in data:
        if isinstance(data[key], list) and not data[key]:
            data[key] = []

    return data

# ---------------- NEW: Site-wide product scraper ---------------- #

def is_product_url(url: str) -> bool:
    """
    Heuristic to detect product pages
    Works for Shopify, WooCommerce, custom sites
    """
    keywords = [
        "/product", "/products", "/item", "/shop",
        "/p/", "/buy", "sku", "variant"
    ]
    return any(k in url.lower() for k in keywords)


async def get_all_internal_links(base_url: str):
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(base_url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    base_domain = urlparse(base_url).netloc

    links = set()

    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        parsed = urlparse(href)

        if parsed.netloc == base_domain:
            links.add(href.split("#")[0])

    return list(links)


async def scrape_full_site_products(site_url: str):
    """
    Main function:
    1. Get all internal links
    2. Filter product URLs
    3. Scrape each product page
    """
    all_links = await get_all_internal_links(site_url)

    product_links = [url for url in all_links if is_product_url(url)]

    results = []

    for url in product_links:
        try:
            product_data = await scrape_website(url)
            results.append(product_data)
        except Exception as e:
            results.append({
                "url": url,
                "error": str(e)
            })

    return {
        "site": site_url,
        "total_products": len(results),
        "products": results
    }


async def get_internal_links(base_url: str):
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(base_url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    base_domain = urlparse(base_url).netloc

    links = set()

    for a in soup.find_all("a", href=True):
        full_url = urljoin(base_url, a["href"])
        parsed = urlparse(full_url)

        if parsed.netloc == base_domain:
            clean_url = full_url.split("#")[0]
            links.add(clean_url)

    return list(links)


async def scrape_full_website(site_url: str, limit: int = 30):
    """
    Crawls and scrapes multiple pages of a website
    """
    links = await get_internal_links(site_url)

    # Limit pages to avoid overload (VERY IMPORTANT)
    links = links[:limit]

    results = []

    for link in links:
        try:
            page_data = await scrape_website(link)
            results.append(page_data)
        except Exception as e:
            results.append({
                "url": link,
                "error": str(e)
            })

    return {
        "site": site_url,
        "total_pages_scraped": len(results),
        "pages": results
    }
