import os
import asyncio
from dotenv import load_dotenv
import google.genai as genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("You must set the GEMINI_API_KEY environment variable.")

# Create client (NEW SDK)
client = genai.Client(api_key=API_KEY)

async def call_gemini(prompt: str) -> str:
    loop = asyncio.get_event_loop()

    def sync_call():
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
        )
        return response.text

    return await loop.run_in_executor(None, sync_call)
