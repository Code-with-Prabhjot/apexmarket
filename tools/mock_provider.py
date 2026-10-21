"""Mock OpenAI-compatible inference provider for offline testing.
Run: MOCK_NAME=spot1 MOCK_TTFT_MS=40 uvicorn tools.mock_provider:app --port 9001
Runtime chaos: POST /admin/config {"fail_rate":1.0} or {"degraded":true}
"""
import asyncio, hashlib, json, os, random, re
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


def _cfg_from_env() -> dict:
    return {
        "name": os.getenv("MOCK_NAME", "mock"),
        "ttft_ms": float(os.getenv("MOCK_TTFT_MS", "30")),
        "token_delay_ms": float(os.getenv("MOCK_TOKEN_DELAY_MS", "2")),
        "fail_rate": float(os.getenv("MOCK_FAIL_RATE", "0")),
        "fail_status": int(os.getenv("MOCK_FAIL_STATUS", "503")),
        "degraded": os.getenv("MOCK_DEGRADED", "0") == "1",
    }


def honest_text(prompt: str, max_tokens: int) -> str:
    """Deterministic: every honest node returns identical output for a prompt."""
    m_add = re.search(r"sum of (\d+) and (\d+)", prompt)
    if m_add:
        return str(int(m_add.group(1)) + int(m_add.group(2)))

    m_mult = re.search(r"product of (\d+) and (\d+)", prompt)
    if m_mult:
        return str(int(m_mult.group(1)) * int(m_mult.group(2)))

    m_json = re.search(r'From the JSON payload (\{.*?\}).*?numeric value of "([^"]+)"', prompt)
    if m_json:
        try:
            data = json.loads(m_json.group(1))
            val = data.get(m_json.group(2))
            if val is not None:
                return str(val)
        except Exception:
            pass

    h = hashlib.sha1(prompt.encode()).hexdigest()
    words = [f"w{h[i:i+3]}" for i in range(0, 30, 3)]
    return " ".join(words[: max(1, min(max_tokens, len(words)))])


def degraded_text(prompt: str, max_tokens: int) -> str:
    if any(k in prompt for k in ("sum of", "product of", "From the JSON payload")):
        return f"garbled calculation error {random.randint(1000000, 9999999)}"
    words = honest_text(prompt, max_tokens).split()
    random.Random(prompt).shuffle(words)
    return " ".join(["garbled"] + words[: max(1, len(words) // 2)])


def create_app(cfg: dict | None = None) -> FastAPI:
    app = FastAPI(title="Mock Provider")
    app.state.cfg = cfg or _cfg_from_env()

    @app.get("/health")
    async def health():
        return {"status": "ok", "name": app.state.cfg["name"]}

    @app.get("/v1/models")
    async def models():
        return {"data": [{"id": "mock-model", "object": "model"}]}

    @app.post("/admin/config")
    async def set_cfg(req: Request):
        app.state.cfg.update(await req.json())
        return app.state.cfg

    @app.post("/v1/chat/completions")
    async def chat(req: Request):
        c = app.state.cfg
        body = await req.json()
        if random.random() < c["fail_rate"]:
            return JSONResponse({"error": "injected failure"}, status_code=c["fail_status"])
        prompt = body["messages"][-1]["content"]
        max_tokens = int(body.get("max_tokens", 10))
        text = (degraded_text if c["degraded"] else honest_text)(prompt, max_tokens)
        words = text.split()
        usage = {"prompt_tokens": max(1, len(prompt.split())),
                 "completion_tokens": len(words)}
        model = body.get("model", "mock-model")
        await asyncio.sleep(c["ttft_ms"] / 1000)

        if not body.get("stream"):
            return {"id": "mock", "model": model, "usage": usage,
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": text}}]}

        async def gen():
            for i, w in enumerate(words):
                if i:
                    await asyncio.sleep(c["token_delay_ms"] / 1000)
                chunk = {"choices": [{"index": 0, "delta": {"content": w + (" " if i < len(words) - 1 else "")}}]}
                yield f"data: {json.dumps(chunk)}\n\n"
            yield f"data: {json.dumps({'choices': [], 'usage': usage})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


app = create_app()
