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

try:
    with open("./cookies.json", "r") as f:
        sduwrap.cookies = json.load(f)
        if not sduwrap.cookies:
            raise FileNotFoundError
except FileNotFoundError:
    print("Warning: No cookies.json found. Please login first.")

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


def sync_chat_producer(content: str, history: list, config: ChatConfig, q: queue.Queue):
    request_history = []
    for chat_session in history:
        cs = sduwrap.ChatSession()
        cs.role = chat_session.role if hasattr(chat_session, 'role') else chat_session.get('role')
        cs.content = chat_session.content if hasattr(chat_session, 'content') else chat_session.get('content')
        request_history.append(cs)
    
    try:
        for chunk in sduwrap.chat(content, request_history, config):
            q.put(chunk)
    except Exception as e:
        q.put({"error": str(e)})
    finally:
        q.put(None)


async def chat_stream(content: str, history: list, config: ChatConfig):
    q = queue.Queue()
    
    loop = asyncio.get_event_loop()
    
    def run_producer():
        request_history = []
        for chat_session in history:
            cs = sduwrap.ChatSession()
            cs.role = chat_session.role if hasattr(chat_session, 'role') else chat_session.get('role')
            cs.content = chat_session.content if hasattr(chat_session, 'content') else chat_session.get('content')
            request_history.append(cs)
        
        try:
            for chunk in sduwrap.chat(content, request_history, config):
                q.put(chunk)
        except Exception as e:
            q.put({"error": str(e)})
        finally:
            q.put(None)
    
    await loop.run_in_executor(executor, run_producer)
    
    while True:
        chunk = await loop.run_in_executor(executor, q.get)
        if chunk is None:
            break
        if "error" in chunk:
            raise Exception(chunk["error"])
        yield chunk


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
    
    if stream:
        async def generate_stream():
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
                prompt_tokens=len(str(current_input)),
                completion_tokens=len(full_content) + len(full_reasoning),
                total_tokens=len(str(current_input)) + len(full_content) + len(full_reasoning),
            ),
        )
        
        return response.model_dump()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
