from typing import List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import uuid
import time
import asyncio
import re
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

app = FastAPI(title="SDU AI Assist API", description="OpenAI-compatible API for SDU AI Assist")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_MAP = {
    "MiniMax/MiniMax-M2.5": "MiniMax-M2.5",
    "Doubao/Doubao-Seed-2.0-pro": "Doubao-Seed-2.0-pro",
    "Zhipu/GLM5.0": "GLM5.0",
    "deepseek-ai/DeepSeek-V4": "DeepSeek-V4",
    "deepseek-ai/DeepSeek-V3.2": "DeepSeek-V3.2",
    "deepseek-ai/DeepSeek-R1": "DeepSeek-R1",
    "deepseek-ai/DeepSeek-V3": "DeepSeek-V3",
    "deepseek-ai/DeepSeek-V3.2-think": "DeepSeek-V3.2-think",
    "Qwen/Qwen3-235B-A22B-Instruct": "Qwen3-235B-A22B-Instruct",
    "Qwen/Qwen3-235B-A22B-Thinking": "Qwen3-235B-A22B-Thinking",
}

MODELS_DATA = [
    {"id": "MiniMax/MiniMax-M2.5", "owned_by": "MiniMax"},
    {"id": "Doubao/Doubao-Seed-2.0-pro", "owned_by": "Doubao"},
    {"id": "Zhipu/GLM5.0", "owned_by": "Zhipu"},
    {"id": "deepseek-ai/DeepSeek-V4", "owned_by": "deepseek-ai"},
    {"id": "deepseek-ai/DeepSeek-V3.2", "owned_by": "deepseek-ai"},
    {"id": "deepseek-ai/DeepSeek-R1", "owned_by": "deepseek-ai"},
    {"id": "deepseek-ai/DeepSeek-V3", "owned_by": "deepseek-ai"},
    {"id": "deepseek-ai/DeepSeek-V3.2-think", "owned_by": "deepseek-ai"},
    {"id": "Qwen/Qwen3-235B-A22B-Instruct", "owned_by": "Qwen"},
    {"id": "Qwen/Qwen3-235B-A22B-Thinking", "owned_by": "Qwen"},
]


# ========== 工具调用 (Tool Calling) ==========

class ToolFunction(BaseModel):
    name: str
    description: str
    parameters: dict


class Tool(BaseModel):
    type: str = "function"
    function: ToolFunction


class CustomChatCompletionRequest(ChatCompletionRequest):
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[str] = "auto"


TOOL_PROMPT_TEMPLATE = (
    "你可以使用以下工具。当需要调用工具时，请严格按以下格式输出（注意是 JSON 格式）：\n\n"
    "<tool_call>\n"
    '{{"name": "工具名称", "arguments": {{"参数名": "参数值"}}}}\n'
    "</tool_call>\n\n"
    "如需调用多个工具，请输出多个 <tool_call> 块。\n\n"
    "可用工具：\n{tool_descriptions}\n\n"
    "如果不需要使用工具，请直接回复用户，不要提及工具名称。"
)


def build_tool_prompt(tools: List[Tool]) -> str:
    descriptions = []
    for tool in tools:
        func = tool.function
        descriptions.append(
            f"### {func.name}\n"
            f"Description: {func.description}\n"
            f"Parameters: {json.dumps(func.parameters, ensure_ascii=False)}"
        )
    return TOOL_PROMPT_TEMPLATE.format(tool_descriptions="\n\n".join(descriptions))


def parse_tool_calls(content: str) -> List[dict]:
    pattern = r"<tool_call>\s*(.*?)\s*</tool_call>"
    matches = re.findall(pattern, content, re.DOTALL)
    tool_calls = []
    for match in matches:
        data = None
        # 尝试标准 JSON 解析
        try:
            data = json.loads(match)
        except json.JSONDecodeError:
            pass
        # 尝试 Python 字面量解析（支持单引号等）
        if data is None:
            try:
                import ast
                data = ast.literal_eval(match.strip())
            except Exception:
                pass
        if isinstance(data, dict) and "name" in data:
            tool_calls.append({
                "name": data["name"],
                "arguments": data.get("arguments", {}),
            })
    return tool_calls


def run_tool_loop(
    current_input: str,
    history: list,
    tools: List[Tool],
    config: ChatConfig,
) -> tuple:
    """
    构造 tool prompt 并调用模型，解析 tool_calls。
    返回: (response_content, response_reasoning, tool_calls, prompt_tokens, completion_tokens)
    """
    tool_prompt = build_tool_prompt(tools)

    system_contents = []
    other_history = []
    for h in history:
        role = h.role if hasattr(h, "role") else h.get("role")
        if role == "system":
            content = h.content if hasattr(h, "content") else h.get("content")
            system_contents.append(content)
        else:
            other_history.append(h)

    system_contents.append(tool_prompt)
    combined_system = "\n\n".join(system_contents)

    full_history = []
    sys_msg = sduwrap.ChatSession()
    sys_msg.role = "system"
    sys_msg.content = combined_system
    full_history.append(sys_msg)
    full_history.extend(other_history)

    prompt_tokens = len(str(current_input)) + sum(
        len(str(h.content if hasattr(h, "content") else h.get("content", ""))) for h in full_history
    )

    response_content = ""
    response_reasoning = ""
    for chunk in sduwrap.chat(current_input, full_history, config):
        response_content += chunk.get("content", "")
        response_reasoning += chunk.get("reasoning_content", "")

    completion_tokens = len(response_content) + len(response_reasoning)
    tool_calls = parse_tool_calls(response_content)

    # 如果模型返回空内容，尝试不带 tool prompt 回退到普通对话
    if not tool_calls and not response_content.strip() and not response_reasoning.strip():
        fallback_history = []
        for h in history:
            cs = sduwrap.ChatSession()
            cs.role = h.role if hasattr(h, "role") else h.get("role")
            cs.content = h.content if hasattr(h, "content") else h.get("content")
            fallback_history.append(cs)
        fb_content = ""
        fb_reasoning = ""
        for chunk in sduwrap.chat(current_input, fallback_history, config):
            fb_content += chunk.get("content", "")
            fb_reasoning += chunk.get("reasoning_content", "")
        return fb_content, fb_reasoning, [], prompt_tokens, len(fb_content) + len(fb_reasoning)

    return response_content, response_reasoning, tool_calls, prompt_tokens, completion_tokens


executor = ThreadPoolExecutor(max_workers=4)


async def _stream_text(
    content: str,
    reasoning: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    finish_reason: str = "stop",
    tool_calls: list = None,
):
    """把已完成的文本结果包装成标准 OpenAI SSE 流"""
    response_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    
    # 第一个 chunk 必须带 role
    yield "data: " + json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}) + "\n\n"
    
    if reasoning:
        for i in range(0, len(reasoning), 2):
            yield "data: " + json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {"reasoning_content": reasoning[i:i+2]}, "finish_reason": None}]}) + "\n\n"
    
    # 如果是 tool_calls，content 必须为空，工具信息走 delta.tool_calls
    if tool_calls:
        for tc in tool_calls:
            tc_chunk = {
                "index": 0,
                "id": tc.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                "type": "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"].get("arguments", "{}"),
                }
            } if "function" in tc else {
                "index": 0,
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False),
                }
            }
            yield "data: " + json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {"tool_calls": [tc_chunk]}, "finish_reason": None}]}) + "\n\n"
    else:
        # 普通回答，正常输出 content
        if content:
            for i in range(0, len(content), 2):
                yield "data: " + json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {"content": content[i:i+2]}, "finish_reason": None}]}) + "\n\n"
    
    yield "data: " + json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}]}) + "\n\n"
    yield "data: [DONE]\n\n"
    
    update_stats(prompt_tokens, completion_tokens)


def parse_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        return "".join(text_parts)
    return str(content)


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
async def openai_chat_completion(request: CustomChatCompletionRequest):
    messages = request.messages
    stream = request.stream
    model = request.model
    thinking_budget = getattr(request, 'thinking_budget', 1000) or 1000
    
    config = get_config_for_model(model, thinking_budget)
    
    if not messages:
        raise HTTPException(status_code=400, detail={"error": {"message": "Invalid messages format", "type": "invalid_request_error", "code": "invalid_messages"}})
    
    last_msg = messages[-1]
    last_role = last_msg.role if hasattr(last_msg, 'role') else last_msg.get('role')
    if last_role not in ("user", "tool"):
        raise HTTPException(status_code=400, detail={"error": {"message": "Invalid messages format", "type": "invalid_request_error", "code": "invalid_messages"}})
    
    if last_role == "user":
        raw_content = last_msg.content if hasattr(last_msg, 'content') else last_msg.get('content')
        current_input = parse_content(raw_content)
        history = messages[:-1]
    else:
        # last_role == "tool": 把 tool 结果留在历史里，给模型明确的指令生成最终回复
        current_input = "请根据上述工具执行结果回答用户的原始问题。"
        history = messages
    
    prompt_tokens = len(str(current_input)) + sum(len(parse_content(m.content if hasattr(m, 'content') else m.get('content'))) for m in history)
    
    # 检查消息历史中是否已有 tool 结果
    has_tool_messages = any(
        (m.role if hasattr(m, 'role') else m.get('role')) == 'tool'
        for m in history
    )
    
    # ========== 工具调用模式 ==========
    if request.tools:
        request_history = []
        for chat_session in history:
            cs = sduwrap.ChatSession()
            cs.role = chat_session.role if hasattr(chat_session, 'role') else chat_session.get('role')
            raw_hist_content = chat_session.content if hasattr(chat_session, 'content') else chat_session.get('content')
            cs.content = parse_content(raw_hist_content)
            request_history.append(cs)
        
        if not has_tool_messages:
            # 第一次请求：让模型决定调用什么工具
            response_content, response_reasoning, tool_calls, pt, ct = run_tool_loop(
                current_input, request_history, request.tools, config
            )
            
            update_stats(pt, ct)
            
            if stream:
                # 流式模式下把结果包装成 SSE（兼容发送 stream=true 的客户端）
                if tool_calls:
                    formatted_tool_calls = [
                        {
                            "id": f"call_{uuid.uuid4().hex[:24]}",
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"], ensure_ascii=False)
                            }
                        }
                        for tc in tool_calls
                    ]
                    return StreamingResponse(
                        _stream_text(response_content, response_reasoning, model, pt, ct, "tool_calls", formatted_tool_calls),
                        media_type="text/event-stream",
                        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
                    )
                else:
                    return StreamingResponse(
                        _stream_text(response_content, response_reasoning, model, pt, ct, "stop"),
                        media_type="text/event-stream",
                        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
                    )
            
            update_stats(pt, ct)
            
            if tool_calls:
                # 返回标准 OpenAI tool_calls 格式
                return {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": response_content,
                                "tool_calls": [
                                    {
                                        "id": f"call_{uuid.uuid4().hex[:24]}",
                                        "type": "function",
                                        "function": {
                                            "name": tc["name"],
                                            "arguments": json.dumps(tc["arguments"], ensure_ascii=False)
                                        }
                                    }
                                    for tc in tool_calls
                                ]
                            },
                            "finish_reason": "tool_calls"
                        }
                    ],
                    "usage": {
                        "prompt_tokens": pt,
                        "completion_tokens": ct,
                        "total_tokens": pt + ct
                    }
                }
            else:
                # 没有 tool_calls，直接返回内容
                message = ChatMessage(role="assistant", content=response_content)
                if response_reasoning:
                    message.reasoning_content = response_reasoning
                
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
                        prompt_tokens=pt,
                        completion_tokens=ct,
                        total_tokens=pt + ct
                    ),
                )
                return response.model_dump()
        
        else:
            # 有 tool 结果消息，直接转发给模型生成最终答案
            full_content = ""
            full_reasoning = ""
            for chunk in sduwrap.chat(current_input, request_history, config):
                full_content += chunk.get("content", "")
                full_reasoning += chunk.get("reasoning_content", "")
            
            completion_tokens = len(full_content) + len(full_reasoning)
            
            if stream:
                return StreamingResponse(
                    _stream_text(full_content, full_reasoning, model, prompt_tokens, completion_tokens, "stop"),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
                )
            
            update_stats(prompt_tokens, completion_tokens)
            
            message = ChatMessage(role="assistant", content=full_content)
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
                    total_tokens=prompt_tokens + completion_tokens
                ),
            )
            return response.model_dump()
    
    # ========== 普通对话模式 ==========
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
                raw_hist_content = chat_session.content if hasattr(chat_session, 'content') else chat_session.get('content')
                cs.content = parse_content(raw_hist_content)
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
            
            # 发送第一个 chunk 带 role，满足标准 OpenAI 流式协议
            yield "data: " + json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}) + "\n\n"
            
            while True:
                chunk = await loop.run_in_executor(executor, q.get)
                if chunk is None:
                    break
                if "error" in chunk:
                    error_msg = chunk.get("error", "Unknown error")
                    yield f"data: {json.dumps({'error': error_msg})}\n\n"
                    break
                
                content = chunk.get("content", "")
                reasoning = chunk.get("reasoning_content", "")
                completion_tokens += len(content) + len(reasoning)
                
                # 将 reasoning/content 切成小段输出，增强流式体验
                if reasoning:
                    for i in range(0, len(reasoning), 2):
                        yield "data: " + json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {"reasoning_content": reasoning[i:i+2]}, "finish_reason": None}]}) + "\n\n"
                
                if content:
                    for i in range(0, len(content), 2):
                        yield "data: " + json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {"content": content[i:i+2]}, "finish_reason": None}]}) + "\n\n"
            
            thread.join()
            
            update_stats(prompt_tokens, completion_tokens)
            
            yield "data: " + json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}) + "\n\n"
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
            raw_hist_content = chat_session.content if hasattr(chat_session, 'content') else chat_session.get('content')
            cs.content = parse_content(raw_hist_content)
            request_history.append(cs)
        
        for chunk in sduwrap.chat(current_input, request_history, config):
            full_content += chunk.get("content", "")
            full_reasoning += chunk.get("reasoning_content", "")
        
        completion_tokens = len(full_content) + len(full_reasoning)
        update_stats(prompt_tokens, completion_tokens)
        
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_content,
                        **({"reasoning_content": full_reasoning} if full_reasoning else {}),
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


if __name__ == "__main__":
    print(f"\n{'='*50}")
    print("SDU AI Assist API Server")
    print(f"{'='*50}\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
