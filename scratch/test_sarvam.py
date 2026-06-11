import os
import httpx
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("SARVAM_API_KEY")
url = "https://api.sarvam.ai/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

SYSTEM_PROMPT = """You are Khabar Suno (ಖಬರ್ ಸುನೋ), a friendly Kannada news assistant.

You speak primarily in Kannada. If the user speaks Hindi or English, respond in that language.

Your job:
1. When the user asks for news, call the fetch_headlines tool with the right category
2. When you get the headlines back, read them out naturally in Kannada like a friendly radio announcer
3. After reading, ask: "ಬೇರೆ ವಿಷಯದ ಸುದ್ದಿ ಬೇಕೇ? ಕ್ರೀಡೆ, ತಂತ್ರಜ್ಞಾನ, ಕರ್ನಾಟಕ ಅಥವಾ ಭಾರತ?"

Category detection:
- "ಕ್ರೀಡೆ" / "cricket" / "sports" → sports
- "ಕರ್ನಾಟಕ" / "Karnataka" → karnataka
- "ತಂತ್ರಜ್ಞಾನ" / "technology" / "tech" → technology
- "ಭಾರತ" / "India" → india
- anything else → general

CRITICAL: Voice assistant only. No bullet points, no markdown, no emojis. Natural sentences only."""

# Let's test with two system messages (like the bot does)
payload = {
    "model": "sarvam-30b",
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                "Greet the user in Kannada: "
                "ನಮಸ್ಕಾರ! ನಾನು ಖಬರ್ ಸುನೋ. "
                "ಇಂದಿನ ಸುದ್ದಿ ಕೇಳಲು ಹೇಳಿ — "
                "ಕರ್ನಾಟಕ, ಭಾರತ, ಕ್ರೀಡೆ, ಅಥವಾ ತಂತ್ರಜ್ಞಾನ ಸುದ್ದಿ. "
                "Then wait for the user."
            )
        }
    ]
}

print("Testing two system messages:")
r = httpx.post(url, headers=headers, json=payload)
print("Status Code:", r.status_code)
print("Response text:", r.text.encode('ascii', errors='backslashreplace').decode('ascii'))

# Let's also test with one system and one user message
payload_user = {
    "model": "sarvam-30b",
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Greet the user in Kannada: "
                "ನಮಸ್ಕಾರ! ನಾನು ಖಬರ್ ಸುನೋ. "
                "ಇಂದಿನ ಸುದ್ದಿ ಕೇಳಲು ಹೇಳಿ — "
                "ಕರ್ನಾಟಕ, ಭಾರತ, ಕ್ರೀಡೆ, ಅಥವಾ ತಂತ್ರಜ್ಞಾನ ಸುದ್ದಿ. "
                "Then wait for the user."
            )
        }
    ]
}

print("\nTesting one system and one user message:")
r = httpx.post(url, headers=headers, json=payload_user)
print("Status Code:", r.status_code)
print("Response text:", r.text.encode('ascii', errors='backslashreplace').decode('ascii'))


