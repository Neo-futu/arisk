"""
OpenRouter 聚合大模型測試
測試多個模型組：OpenAI / Anthropic / Google / Qwen / Mistral
"""
import requests

API_KEY = "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"
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "http://localhost:5173",
    "X-Title": "ARISK FSI Platform",
}

MODEL_GROUPS = {
    "Group 1 - OpenAI": [
        "openai/gpt-4o-mini",
        "openai/gpt-4.1-nano",
    ],
    "Group 2 - Anthropic": [
        "anthropic/claude-haiku-4-5",
        "anthropic/claude-3-haiku",
    ],
    "Group 3 - Google": [
        "google/gemini-flash-1.5-8b",
        "google/gemini-2.0-flash-001",
    ],
    "Group 4 - Qwen": [
        "qwen/qwen3-8b",
        "qwen/qwen-2.5-7b-instruct",
        "qwen/qwen3-30b-a3b",
    ],
    "Group 5 - Mistral / DeepSeek": [
        "mistralai/mistral-7b-instruct",
        "deepseek/deepseek-chat-v3-0324:free",
    ],
    "Group 6 - xAI Grok (HK available)": [
        "x-ai/grok-4.20",
        "x-ai/grok-4.3",
        "x-ai/grok-4.20-multi-agent",
        "x-ai/grok-build-0.1",
    ],
}

PROMPT = "Reply in one short sentence: what is risk management in finance?"


def test_model(model_id: str) -> tuple[bool, str]:
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 80,
    }
    try:
        resp = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=20)
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"].strip()
            return True, text[:100]
        else:
            err = resp.json().get("error", {}).get("message", resp.text)[:80]
            return False, f"HTTP {resp.status_code}: {err}"
    except Exception as e:
        return False, str(e)[:80]


if __name__ == "__main__":
    print(f"{'='*65}")
    print("  OpenRouter 多模型聚合測試")
    print(f"{'='*65}\n")

    total_ok = 0
    total = 0

    for group, models in MODEL_GROUPS.items():
        print(f"\n--- {group} ---")
        for model in models:
            total += 1
            ok, msg = test_model(model)
            status = "OK" if ok else "FAIL"
            if ok:
                total_ok += 1
            print(f"  [{status}] {model}")
            print(f"         {msg}")

    print(f"\n{'='*65}")
    print(f"  結果: {total_ok}/{total} 模型可用")
    print(f"{'='*65}")
