from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv('GROQ_API_KEY')
print(f'API Key found: {api_key[:10]}...{api_key[-10:] if api_key else "None"}')
print(f'Full length: {len(api_key) if api_key else 0}')

if api_key and len(api_key) > 50:
    print('✅ API Key format looks correct')
    
    # Test Groq API
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': 'Hello'}],
            max_tokens=10
        )
        print('✅ API Key is VALID and working')
    except Exception as e:
        print(f'❌ API Key test failed: {e}')
else:
    print('❌ API Key format issue')
