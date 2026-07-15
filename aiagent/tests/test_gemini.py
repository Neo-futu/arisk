from google import genai

API_KEY = "AQ.Ab8RN6Jj0OXyCT7SYxG10bp5oRUn4RU13aU2JeSptyoEAuG9Dw"

client = genai.Client(api_key=API_KEY)

try:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Say 'API key is working' in one sentence.",
    )
    print("Success:", response.text)
except Exception as e:
    print("Failed:", e)
