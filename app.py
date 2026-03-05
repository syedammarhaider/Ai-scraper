# app.py

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from groq import Groq
from scraper import UltraScraper
import os, json, time

# Load .env variables
load_dotenv()

# Initialize FastAPI
app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
 
# ---------- GROQ ----------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

# Initialize Groq client without proxies
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ---------- HOME ----------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ---------- HEALTH ----------
@app.get("/health")
async def health():
    return {"status": "healthy"}

# ------------------- RAG SYSTEM -------------------
# Global RAG variables for professional large data handling
embedder = SentenceTransformer('all-MiniLM-L6-v2')  # Fast, accurate embedder
vector_index = None
full_data_chunks = []  # Store full chunks globally
chunk_metadata = []  # Store metadata for each chunk

# Professional RAG functions for handling large scraped data

def create_rag_chunks(scraped_data):
    """Professional RAG chunking - splits large data into semantic chunks"""
    global vector_index, full_data_chunks, chunk_metadata
    
    # Extract all text content from scraped data
    all_text = []
    chunk_metadata = []  # Initialize local metadata list
    
    if 'pages' in scraped_data:
        # Multi-page data
        for page_idx, page in enumerate(scraped_data['pages']):
            page_text = f"PAGE {page_idx + 1}: {page.get('title', 'No Title')}\n"
            page_text += f"URL: {page.get('url', '')}\n"
            
            if page.get('description'):
                page_text += f"Description: {page['description']}\n"
            
            # Add headings
            if page.get('headings'):
                for level, headings in page['headings'].items():
                    if headings:
                        page_text += f"{level.upper()}: {', '.join(headings[:5])}\n"
            
            # Add paragraphs
            if page.get('paragraphs'):
                page_text += "Content:\n"
                for para in page['paragraphs'][:10]:
                    page_text += f"- {para}\n"
            
            # Add ALL internal links
            if page.get('internal_links'):
                page_text += f"Internal Links ({len(page['internal_links'])} total):\n"
                for link in page['internal_links']:
                    page_text += f"- {link.get('url', 'No URL')}\n"
            
            # Add ALL external links
            if page.get('external_links'):
                page_text += f"External Links ({len(page['external_links'])} total):\n"
                for link in page['external_links']:
                    page_text += f"- {link.get('url', 'No URL')}\n"
            
            all_text.append(page_text)
            chunk_metadata.append({
                'page': page_idx + 1,
                'title': page.get('title', 'No Title'),
                'url': page.get('url', ''),
                'type': 'full_page'
            })
    else:
        # Single page data
        page_text = f"PAGE: {scraped_data.get('title', 'No Title')}\n"
        page_text += f"URL: {scraped_data.get('url', '')}\n"
        
        if scraped_data.get('description'):
            page_text += f"Description: {scraped_data['description']}\n"
        
        # Add headings
        if scraped_data.get('headings'):
            for level, headings in scraped_data['headings'].items():
                if headings:
                    page_text += f"{level.upper()}: {', '.join(headings[:5])}\n"
        
        # Add paragraphs
        if scraped_data.get('paragraphs'):
            page_text += "Content:\n"
            for para in scraped_data['paragraphs'][:15]:
                page_text += f"- {para}\n"
        
        # Add ALL internal links
        if scraped_data.get('internal_links'):
            page_text += f"Internal Links ({len(scraped_data['internal_links'])} total):\n"
            for link in scraped_data['internal_links']:
                page_text += f"- {link.get('url', 'No URL')}\n"
        
        # Add ALL external links
        if scraped_data.get('external_links'):
            page_text += f"External Links ({len(scraped_data['external_links'])} total):\n"
            for link in scraped_data['external_links']:
                page_text += f"- {link.get('url', 'No URL')}\n"
        
        all_text.append(page_text)
        chunk_metadata.append({
            'page': 1,
            'title': scraped_data.get('title', 'No Title'),
            'url': scraped_data.get('url', ''),
            'type': 'full_page'
        })
    
    # Create chunks of ~1000 characters each
    chunks = []
    chunk_metadatas = []
    
    for text_idx, text in enumerate(all_text):
        # Split into smaller chunks if text is too long
        words = text.split()
        current_chunk = []
        current_length = 0
        
        for word in words:
            current_chunk.append(word)
            current_length += len(word) + 1
            
            if current_length >= 1000:  # ~250 tokens per chunk
                chunk_text = " ".join(current_chunk)
                chunks.append(chunk_text)
                chunk_metadatas.append(chunk_metadata[text_idx].copy())
                current_chunk = []
                current_length = 0
        
        # Add remaining words
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(chunk_text)
            chunk_metadatas.append(chunk_metadata[text_idx].copy())
    
    return chunks, chunk_metadatas

def embed_and_store_chunks(chunks):
    """Embed chunks and store in FAISS vector database"""
    global vector_index, full_data_chunks
    
    if not chunks:
        return False
    
    try:
        # Embed all chunks
        print(f"🔄 Embedding {len(chunks)} chunks...")
        embeddings = embedder.encode(chunks)
        
        # Create FAISS index
        dim = embeddings.shape[1]
        vector_index = faiss.IndexFlatL2(dim)
        vector_index.add(np.array(embeddings))
        
        # Store chunks globally
        full_data_chunks = chunks
        
        print(f"✅ Successfully embedded and stored {len(chunks)} chunks")
        return True
        
    except Exception as e:
        print(f"❌ Error embedding chunks: {str(e)}")
        return False

def retrieve_relevant_chunks(query, k=5):
    """Retrieve most relevant chunks for a query"""
    global vector_index, full_data_chunks, chunk_metadata
    
    if not vector_index or not full_data_chunks:
        return []
    
    try:
        # Embed query
        query_embedding = embedder.encode([query])
        
        # Search for similar chunks
        distances, indices = vector_index.search(query_embedding, k)
        
        # Retrieve relevant chunks
        relevant_chunks = []
        for i, idx in enumerate(indices[0]):
            if idx < len(full_data_chunks):
                chunk_info = {
                    'text': full_data_chunks[idx],
                    'metadata': chunk_metadata[idx] if idx < len(chunk_metadata) else {},
                    'similarity': float(1.0 / (1.0 + distances[0][i]))  # Convert distance to similarity
                }
                relevant_chunks.append(chunk_info)
        
        return relevant_chunks
        
    except Exception as e:
        print(f"❌ Error retrieving chunks: {str(e)}")
        return []

# ---------- SCRAPE ----------
@app.post("/scrape")
async def scrape(request: Request):
    form = await request.form()
    url = form.get("url")
    mode = form.get("mode", "comprehensive")

    if not url:
        return {"success": False, "error": "URL required"}

    if not url.startswith("http"):
        url = "https://" + url

    data = scraper.scrape_website(url, mode)

    if "error" in data:
        return {"success": False, "error": data["error"]}

    # ── RAG PROCESSING: Chunk & Embed full data ──
    try:
        print(f"🔍 Processing scraped data for RAG...")
        
        # Create chunks from scraped data
        chunks, metadatas = create_rag_chunks(data)
        
        if chunks:
            # Embed and store chunks in vector database
            success = embed_and_store_chunks(chunks)
            
            if success:
                print(f"✅ RAG system initialized with {len(chunks)} chunks")
                data["rag_enabled"] = True
                data["total_chunks"] = len(chunks)
            else:
                print(f"⚠️ RAG embedding failed, using fallback method")
                data["rag_enabled"] = False
        else:
            print(f"⚠️ No chunks created from scraped data")
            data["rag_enabled"] = False
            
    except Exception as e:
        print(f"❌ RAG processing error: {str(e)}")
        data["rag_enabled"] = False

    return {"success": True, "data": data}

# ---------- GROQ CHAT ----------
@app.post("/groq-chat")
async def chat(request: Request):
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not set or invalid"}

    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")

    if not message or not scraped:
        return {"success": False, "error": "Missing data"}

    data = json.loads(scraped)

    # ── RAG RETRIEVAL: Get relevant chunks ──
    try:
        # Check if RAG is enabled and available
        if data.get("rag_enabled") and vector_index is not None:
            print(f"🔍 Using RAG retrieval for: {message[:50]}...")
            
            # Retrieve relevant chunks using semantic search
            relevant_chunks = retrieve_relevant_chunks(message, k=5)
            
            if relevant_chunks:
                # Build context from retrieved chunks
                rag_context = "RETRIEVED FROM SCRAPED DATA USING RAG:\n\n"
                for i, chunk in enumerate(relevant_chunks):
                    rag_context += f"CHUNK {i+1} (Page {chunk['metadata'].get('page', 'N/A')}):\n"
                    rag_context += chunk['text'] + "\n\n"
                
                rag_context += f"USER QUESTION: {message}"
                
                print(f"✅ Retrieved {len(relevant_chunks)} relevant chunks")
                
                # Enhanced system prompt for RAG
                system_prompt = """You are an EXACT factual AI assistant using RAG (Retrieval-Augmented Generation).

Rules:
1. ONLY answer from the RETRIEVED CHUNKS provided below
2. The chunks contain the most relevant information from the scraped website
3. If information not found in chunks, say: "This information is not available in the retrieved scraped data."
4. NEVER guess or use outside knowledge
5. Provide ANSWERS, not explanations about the retrieval process
6. Be precise and factual based on the retrieved content
7. For URL requests, extract ALL URLs from the retrieved chunks
"""
                
                context = rag_context
                
            else:
                # Fallback to traditional method if no chunks retrieved
                print(f"⚠️ No relevant chunks found, using fallback method")
                context = f"SCRAPED DATA:\n{json.dumps(data, indent=2)[:8000]}\n\nQUESTION:\n{message}"
                system_prompt = """You are an EXACT factual AI assistant.
Rules:
1. ONLY answer from provided scraped data.
2. If answer not found, say: "This information is not available in the scraped website data."
3. Never guess or use outside knowledge.
4. Be precise and factual.
"""
        else:
            # Traditional method for non-RAG data
            context = f"SCRAPED DATA:\n{json.dumps(data, indent=2)[:8000]}\n\nQUESTION:\n{message}"
            system_prompt = """You are an EXACT factual AI assistant.
Rules:
1. ONLY answer from provided scraped data.
2. If answer not found, say: "This information is not available in the scraped website data."
3. Never guess or use outside knowledge.
4. Be precise and factual.
"""
            
    except Exception as e:
        print(f"❌ RAG retrieval error: {str(e)}")
        # Fallback to traditional method
        context = f"SCRAPED DATA:\n{json.dumps(data, indent=2)[:8000]}\n\nQUESTION:\n{message}"
        system_prompt = """You are an EXACT factual AI assistant.
Rules:
1. ONLY answer from provided scraped data.
2. If answer not found, say: "This information is not available in the scraped website data."
3. Never guess or use outside knowledge.
4. Be precise and factual.
"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0,
            max_tokens=4000  # Increased for better responses
        )

        answer = getattr(getattr(response.choices[0], "message", None), "content", None)
        if not answer:
            answer = "Groq API did not return any answer."

        return {"success": True, "response": answer.strip()}

    except Exception as e:
        return {"success": False, "error": f"Groq API error: {str(e)}"}

# ---------- GROK MODE ----------
@app.post("/grok-mode")
async def grok_mode(request: Request):
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not set or invalid"}

    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")
    analysis_type = form.get("analysis_type", "comprehensive")

    if not message or not scraped:
        return {"success": False, "error": "Missing message or scraped data"}

    data = json.loads(scraped)

    system_prompt = (
        "You are GROK MODE - An advanced AI for universal questions. "
        "RULES: 1. UNIVERSAL KNOWLEDGE ONLY - Use your comprehensive knowledge base. "
        "2. DO NOT use scraped data - ignore website content. "
        "3. PROVIDE expert answers on any topic. "
        "4. BE helpful and comprehensive. "
        "5. Use your full knowledge for all responses."
    )

    full_context = f"USER QUESTION:\n{message}\n\n(Note: This is a universal knowledge question. Provide comprehensive answer using your knowledge base.)"

    try:
        response = client.chat.completions.create(
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_context}  # Removed character limit for unlimited answers
            ],
            temperature=0.2,
            max_tokens=8000  # Increased from 2000 to 8000 for much longer answers
        )

        answer = getattr(response.choices[0].message, 'content', None)
        if not answer:
            answer = "No response generated."

        return {"success": True, "response": answer.strip(), "mode": "grok_mode"}

    except Exception as e:
        return {"success": False, "error": f"Grok Mode error: {str(e)}"}

# ---------- GROK SUMMARY ----------
@app.post("/grok-summary")
async def grok_summary(request: Request):
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not set or invalid"}

    form = await request.form()
    scraped = form.get("scraped_data")

    if not scraped:
        return {"success": False, "error": "Missing scraped data"}

    data = json.loads(scraped)

    system_prompt = (
        "GROK SUMMARY - Extract key facts. "
        "Provide: 1. MAIN TOPIC. 2. KEY POINTS (3-5). 3. STATISTICS. 4. CONCLUSION. "
        "Only use page data."
    )

    context_parts = ["URL: " + data.get('url', '')]
    if data.get('title'):
        context_parts.append("Title: " + data['title'])
    if data.get('paragraphs'):
        context_parts.append("\n".join(data['paragraphs'][:15]))

    try:
        response = client.chat.completions.create(
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n\n".join(context_parts)}
            ],
            temperature=0.1,
            max_tokens=500
        )

        answer = getattr(response.choices[0].message, 'content', 'No summary.')
        return {"success": True, "summary": answer.strip(), "mode": "grok_summary"}

    except Exception as e:
        return {"success": False, "error": f"Summary error: {str(e)}"}

# ---------- EXPORT ----------
@app.post("/export")
async def export(request: Request):
    body = await request.json()
    fmt = body.get("format")
    data = body.get("data")

    if not fmt or not data:
        return {"success": False, "error": "Missing format or data"}

    filename = f"scraped_{int(time.time())}"

    handlers = {
        "json": scraper.save_as_json,
        "csv": scraper.save_as_csv,
        "excel": scraper.save_as_excel,
        "txt": scraper.save_as_text,
        "pdf": scraper.save_as_pdf
    }

    if fmt not in handlers:
        return {"success": False, "error": f"Unsupported format: {fmt}"}

    path = handlers[fmt](data, filename)
    return FileResponse(path, filename=os.path.basename(path))
    