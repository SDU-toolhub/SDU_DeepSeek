from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import uuid
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
import queue
import threading
import os
import sduwrap
from sduwrap import ChatConfig
from fastchat.protocol.openai_api_protocol import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatCompletionResponseStreamChoice,
    ChatCompletionStreamResponse,
    ChatMessage,
    DeltaMessage,
    UsageInfo,
    ModelList,
    ModelCard,
)

COOKIES_FILE = "./cookies.json"
CREDENTIALS_FILE = "./credentials.json"

token_stats = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "requests": 0,
}
stats_lock = threading.Lock()


def load_cookies():
    global sduwrap
    try:
        with open(COOKIES_FILE, "r") as f:
            sduwrap.cookies = json.load(f)
            if not sduwrap.cookies:
                raise FileNotFoundError
        print("[Cookies] Loaded from file")
        return True
    except FileNotFoundError:
        print("[Cookies] No cookies.json found")
        return False


def save_cookies():
    with open(COOKIES_FILE, "w") as f:
        json.dump(sduwrap.cookies, f)
    print("[Cookies] Saved to file")


def load_credentials():
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save_credentials(sdu_id: str, password: str, fingerprint: str = None):
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump({
            "sdu_id": sdu_id,
            "password": password,
            "fingerprint": fingerprint
        }, f)
    print("[Credentials] Saved to file")


def login(sdu_id: str = None, password: str = None, fingerprint: str = None):
    import sdu_aiassist_login as login_module
    import getpass
    
    if not sdu_id or not password:
        creds = load_credentials()
        if creds:
            sdu_id = creds.get("sdu_id")
            password = creds.get("password")
            fingerprint = creds.get("fingerprint")
    
    if not sdu_id:
        sdu_id = input("Please enter your SDU ID: ")
    if not password:
        password = getpass.getpass("Please enter your password: ")
    if not fingerprint:
        fingerprint_input = input("Enter device fingerprint (press Enter to auto-generate): ").strip()
        if fingerprint_input:
            fingerprint = fingerprint_input
        else:
            fingerprint = str(uuid.uuid4())
            print(f"[Login] Generated fingerprint: {fingerprint}")
    
    print(f"[Login] Logging in as {sdu_id}...")
    
    result = login_module.login(sdu_id, password, fingerprint)
    cookies = result.get("cookies", {})
    
    if not cookies:
        print("[Login] Failed!")
        return False
    
    sduwrap.cookies = cookies
    save_cookies()
    
    save_credentials(sdu_id, password, fingerprint)
    
    print("[Login] Success!")
    return True


def check_and_refresh_cookies():
    if not sduwrap.cookies:
        print("[Refresh] No cookies, need login")
        return login()
    
    test_content = "ping"
    try:
        list(sduwrap.chat(test_content, [], ChatConfig()))
        print("[Refresh] Cookies valid")
        return True
    except Exception as e:
        print(f"[Refresh] Cookies expired: {e}")
        return login()


def update_stats(prompt_tokens: int, completion_tokens: int):
    with stats_lock:
        token_stats["prompt_tokens"] += prompt_tokens
        token_stats["completion_tokens"] += completion_tokens
        token_stats["total_tokens"] += prompt_tokens + completion_tokens
        token_stats["requests"] += 1
        
        print(f"\n{'='*60}")
        print(f"[Stats] Requests: {token_stats['requests']} | "
              f"Prompt: {token_stats['prompt_tokens']} | "
              f"Completion: {token_stats['completion_tokens']} | "
              f"Total: {token_stats['total_tokens']}")
        print(f"{'='*60}\n", flush=True)


def print_stats_summary():
    with stats_lock:
        print(f"\n[Stats Summary] "
              f"Requests: {token_stats['requests']} | "
              f"Prompt: {token_stats['prompt_tokens']} | "
              f"Completion: {token_stats['completion_tokens']} | "
              f"Total: {token_stats['total_tokens']}")


if not load_cookies():
    login()

app = FastAPI(title="SDU DeepSeek API", description="OpenAI-compatible API for SDU DeepSeek")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_MAP = {
    "deepseek-ai/DeepSeek-V3.2": "DeepSeek-V3.2",
    "deepseek-ai/DeepSeek-R1": "DeepSeek-R1",
    "deepseek-ai/DeepSeek-V3": "DeepSeek-V3",
    "deepseek-ai/DeepSeek-V3.2-think": "DeepSeek-V3.2-think",
    "Qwen/Qwen3-235B-A22B-Instruct": "Qwen3-235B-A22B-Instruct",
    "Qwen/Qwen3-235B-A22B-Thinking": "Qwen3-235B-A22B-Thinking",
}

MODELS_DATA = [
    {"id": "deepseek-ai/DeepSeek-V3.2", "owned_by": "deepseek-ai"},
    {"id": "deepseek-ai/DeepSeek-R1", "owned_by": "deepseek-ai"},
    {"id": "deepseek-ai/DeepSeek-V3", "owned_by": "deepseek-ai"},
    {"id": "deepseek-ai/DeepSeek-V3.2-think", "owned_by": "deepseek-ai"},
    {"id": "Qwen/Qwen3-235B-A22B-Instruct", "owned_by": "Qwen"},
    {"id": "Qwen/Qwen3-235B-A22B-Thinking", "owned_by": "Qwen"},
]

executor = ThreadPoolExecutor(max_workers=4)


def get_config_for_model(model: str, thinking_budget: int = 1000) -> ChatConfig:
    config = ChatConfig()
    internal_model = MODEL_MAP.get(model, "DeepSeek-V3.2-think")
    config.set_model(internal_model)
    config.thinking_budget = thinking_budget
    return config


@app.get("/v1/models")
async def list_models():
    models = [
        ModelCard(
            id=m["id"],
            object="model",
            created=1700000000,
            owned_by=m["owned_by"],
        )
        for m in MODELS_DATA
    ]
    return ModelList(data=models).model_dump()


@app.get("/v1/models/{model_id}")
async def get_model(model_id: str):
    for m in MODELS_DATA:
        if m["id"] == model_id:
            model = ModelCard(
                id=m["id"],
                object="model",
                created=1700000000,
                owned_by=m["owned_by"],
            )
            return model.model_dump()
    raise HTTPException(status_code=404, detail={"error": {"message": f"Model {model_id} not found", "type": "invalid_request_error", "code": "model_not_found"}})


@app.post("/v1/chat/completions")
async def openai_chat_completion(request: ChatCompletionRequest):
    messages = request.messages
    stream = request.stream
    model = request.model
    thinking_budget = getattr(request, 'thinking_budget', 1000) or 1000
    
    config = get_config_for_model(model, thinking_budget)
    
    if not messages:
        raise HTTPException(status_code=400, detail={"error": {"message": "Invalid messages format", "type": "invalid_request_error", "code": "invalid_messages"}})
    
    last_msg = messages[-1]
    last_role = last_msg.role if hasattr(last_msg, 'role') else last_msg.get('role')
    if last_role != "user":
        raise HTTPException(status_code=400, detail={"error": {"message": "Invalid messages format", "type": "invalid_request_error", "code": "invalid_messages"}})
    
    current_input = last_msg.content if hasattr(last_msg, 'content') else last_msg.get('content')
    history = messages[:-1]
    
    prompt_tokens = len(str(current_input)) + sum(len(str(m.content if hasattr(m, 'content') else m.get('content', ''))) for m in history)
    
    if stream:
        async def generate_stream():
            completion_tokens = 0
            response_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
            created = int(time.time())
            
            q = queue.Queue()
            loop = asyncio.get_event_loop()
            
            request_history = []
            for chat_session in history:
                cs = sduwrap.ChatSession()
                cs.role = chat_session.role if hasattr(chat_session, 'role') else chat_session.get('role')
                cs.content = chat_session.content if hasattr(chat_session, 'content') else chat_session.get('content')
                request_history.append(cs)
            
            def run_chat():
                try:
                    for chunk in sduwrap.chat(current_input, request_history, config):
                        q.put(chunk)
                except Exception as e:
                    q.put({"error": str(e)})
                finally:
                    q.put(None)
            
            thread = threading.Thread(target=run_chat)
            thread.start()
            
            while True:
                chunk = await loop.run_in_executor(executor, q.get)
                if chunk is None:
                    break
                if "error" in chunk:
                    break
                
                content = chunk.get("content", "")
                reasoning = chunk.get("reasoning_content", "")
                completion_tokens += len(content) + len(reasoning)
                
                if reasoning:
                    stream_response = ChatCompletionStreamResponse(
                        id=response_id,
                        object="chat.completion.chunk",
                        created=created,
                        model=model,
                        choices=[
                            ChatCompletionResponseStreamChoice(
                                index=0,
                                delta=DeltaMessage(reasoning_content=reasoning),
                                finish_reason=None,
                            )
                        ],
                    )
                    yield f"data: {stream_response.model_dump_json()}\n\n"
                
                if content:
                    stream_response = ChatCompletionStreamResponse(
                        id=response_id,
                        object="chat.completion.chunk",
                        created=created,
                        model=model,
                        choices=[
                            ChatCompletionResponseStreamChoice(
                                index=0,
                                delta=DeltaMessage(content=content),
                                finish_reason=None,
                            )
                        ],
                    )
                    yield f"data: {stream_response.model_dump_json()}\n\n"
            
            thread.join()
            
            update_stats(prompt_tokens, completion_tokens)
            
            final_response = ChatCompletionStreamResponse(
                id=response_id,
                object="chat.completion.chunk",
                created=created,
                model=model,
                choices=[
                    ChatCompletionResponseStreamChoice(
                        index=0,
                        delta=DeltaMessage(),
                        finish_reason="stop",
                    )
                ],
            )
            yield f"data: {final_response.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    
    else:
        full_content = ""
        full_reasoning = ""
        
        request_history = []
        for chat_session in history:
            cs = sduwrap.ChatSession()
            cs.role = chat_session.role if hasattr(chat_session, 'role') else chat_session.get('role')
            cs.content = chat_session.content if hasattr(chat_session, 'content') else chat_session.get('content')
            request_history.append(cs)
        
        for chunk in sduwrap.chat(current_input, request_history, config):
            full_content += chunk.get("content", "")
            full_reasoning += chunk.get("reasoning_content", "")
        
        completion_tokens = len(full_content) + len(full_reasoning)
        update_stats(prompt_tokens, completion_tokens)
        
        message = ChatMessage(
            role="assistant",
            content=full_content,
        )
        if full_reasoning:
            message.reasoning_content = full_reasoning
        
        response = ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
            object="chat.completion",
            created=int(time.time()),
            model=model,
            choices=[
                ChatCompletionResponseChoice(
                    index=0,
                    message=message,
                    finish_reason="stop",
                )
            ],
            usage=UsageInfo(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )
        
        return response.model_dump()


if __name__ == "__main__":
    print(f"\n{'='*50}")
    print("SDU DeepSeek API Server")
    print(f"{'='*50}\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
