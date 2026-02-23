# 🤖 ULTRA PROFESSIONAL AI SCRAPER - GEMINI 3 FLASH PREVIEW

## 📋 Project Overview

Zero Compromise - 10000% Working - Ultra Smart - Roman Comments

Yeh ek **professional AI web scraper** hai jo **Gemini 3 Flash Preview** use karta hai. Isme **dual mode** functionality hai aur **5 export formats** available hain.

## 🚀 Features

### 🔥 DUAL MODE GEMINI:
- **Website Mode** - Sirf scraped data ke sawaal
- **General Mode** - Koi bhi sawaal (general chat)

### 🌓 DARK/LIGHT MODE:
- Smooth toggle with localStorage
- Automatic theme detection

### 📊 COMPREHENSIVE SCRAPING:
- Full page data - kuch miss nahi
- Images with alt text
- Internal/External links classification
- Headings (h1-h6)
- Paragraphs, Lists, Tables
- Meta tags, Open Graph, Twitter cards

### 💾 5 EXPORT FORMATS:
- **JSON** - Structured data
- **CSV** - Simple spreadsheet
- **Excel** - Multi-sheet with formatting
- **Text** - Human readable
- **PDF** - Professional report

### ⚡ PERFORMANCE:
- Caching - 5 minute cache
- Async operations
- Optimized scraping

### 🎨 UI/UX:
- Tailwind CSS - Beautiful design
- Responsive - Mobile friendly
- Smooth animations
- Tabbed interface
- Real-time chat

## 📁 Project Structure

```
ai-scraper/
│
├── app.py                 # 🎯 Main Flask app - Server + Routes + Gemini Config
├── scraper.py             # 🕷️ Scraping Engine - Data nikaalne ki machine
├── requirements.txt       # 📦 Python dependencies
├── .env                   # 🔑 API keys and secrets
├── README.md              # 📖 Project documentation
├── templates/
│   └── index.html         # 🎨 UI - Gemini Div + 2 Modes + Dark/Light + Tailwind
└── downloads/             # 📥 Yahan automatically files save hongi
```

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.8+
- Gemini API Key

### Step 1: Clone/Download Project
```bash
# Project folder mein jaao
cd ai-scraper
```

### Step 2: Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Environment Setup
`.env` file banain aur API key add karo:

```env
# 📝 .env file - API Keys and Secrets
GEMINI_API_KEY=AIzaSyDGXvCQBrUyHfTLwdZjQCEH6oXVwWyI308
SECRET_KEY=your-super-secret-key-change-this
```

**Important:** `GEMINI_API_KEY` ko apni actual Gemini API key se replace karo!

### Step 5: Run Application
```bash
python app.py
```

Server chal jaayega: **http://localhost:5000**

## 🎯 Usage Guide

### 1. Website Scrape Karna
1. URL input mein website ka URL daalo
2. Export format choose karo (JSON, CSV, Excel, Text, PDF)
3. "SCRAPE WEBSITE WITH GEMINI AI" button click karo
4. Wait for scraping to complete

### 2. Gemini AI Chat
Scraping ke baad Gemini AI chat interface active ho jaayega:

#### Website Mode:
- Sirf scraped website ke baare mein sawaal poocho
- Example: "Is website ka main topic kya hai?"
- Example: "Kitne images hain is page mein?"

#### General Mode:
- Koi bhi general sawaal poocho
- Example: "Python kya hai?"
- Example: "2+2 kitna hai?"

### 3. Data Export
- Scraped data ko 5 formats mein export kar sakte hain
- Files automatically `downloads/` folder mein save hoti hain
- Download button se file download kar sakte hain

## 🔧 API Endpoints

### POST /scrape
Website scraping ke liye

**Request:**
```json
{
    "url": "https://example.com",
    "format": "json",
    "use_javascript": false,
    "depth": "comprehensive"
}
```

**Response:**
```json
{
    "success": true,
    "data": { /* scraped data */ },
    "file": {
        "name": "scrape_20231218_143022.json",
        "path": "downloads/scrape_20231218_143022.json",
        "format": "json",
        "size": 12345
    }
}
```

### POST /gemini-chat
Gemini AI chat ke liye

**Request:**
```json
{
    "message": "Your question here",
    "mode": "website" // or "general"
}
```

**Response:**
```json
{
    "success": true,
    "response": "AI response here",
    "mode": "website"
}
```

### GET /download/<filename>
File download ke liye

## 🐛 Troubleshooting

### Common Issues

1. **Gemini API Error**
   - Check API key in `.env` file
   - Ensure API key is valid and active

2. **Scraping Failed**
   - Check if URL is accessible
   - Some websites may block scraping

3. **Dependencies Error**
   - Ensure all packages installed: `pip install -r requirements.txt`
   - Check Python version (3.8+)

4. **Port Already in Use**
   - Change port in `app.py`: `app.run(debug=True, port=5001)`

### Debug Mode
Debug mode already enabled in `app.py`. Console mein detailed logs milegi.

## 🤝 Contributing

Contributions welcome hain! Please:

1. Fork karo
2. Feature branch banayo
3. Commit karo
4. Push karo
5. Pull request bhejo

## 📄 License

MIT License - feel free to use commercially!

## 🙏 Acknowledgments

- **Google Gemini AI** - AI integration ke liye
- **BeautifulSoup** - HTML parsing ke liye
- **Tailwind CSS** - Beautiful UI ke liye
- **Flask** - Backend framework ke liye

## 📞 Support

Koi issue ho toh:
1. Console logs check karo
2. README follow karo
3. GitHub issues mein post karo

---

**Made with ❤️ using Gemini 3 Flash Preview**

**Status**: ✅ 10000% Working Guaranteed
