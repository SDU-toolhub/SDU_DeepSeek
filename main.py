from fastapi import FastAPI
import sduwrap
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse
import uvicorn
import json
import uuid
import time


app = FastAPI()

# 假设这是用户已有的生成器函数（需自行实现具体逻辑）
def chat(content: str, history: list) -> str:
    request_history = []
    for chat_session in history:
        cs = sduwrap.ChatSession()
        cs.role = chat_session["role"]
        cs.content = chat_session["content"]

        request_history.append(cs)


    for response in sduwrap.chat(content, request_history,sduwrap.ChatConfig()):
        yield response

@app.post("/v1/chat/completions")
async def openai_chat_completion(request: Request):
    # 解析请求体
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    # 提取必要参数
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    model = body.get("model", "deepseek")  # 模型名称按需处理

    # 校验消息格式
    if not messages or messages[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="Invalid messages format")

    # 提取当前输入和历史记录
    current_input = messages[-1]["content"]
    history = messages[:-1]  # 按需调整历史处理逻辑

    # 流式响应处理
    if stream:
        def generate_stream():
            # 生成唯一响应ID
            response_id = f"sdu_ds-{uuid.uuid4()}"
            created = int(time.time())

            # 遍历生成器生成事件流
            for chunk in chat(current_input, history):
                event_data = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": chunk},
                        "finish_reason": None
                    }]
                }
                yield f"data: {json.dumps(event_data)}\n\n"

            # 结束事件
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream"
        )

    # 非流式响应处理
    else:
        # 收集完整响应
        full_response = "".join([
            chunk for chunk in chat(current_input, history)
        ])

        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": full_response
                },
                "finish_reason": "stop"
            }],
            "usage": {  # 按需实现实际token计算
                "prompt_tokens": len(current_input),
                "completion_tokens": len(full_response),
                "total_tokens": len(current_input) + len(full_response)
            }
        }


if __name__ == "__main__":
    # 判断 ./cookies.json 是否存在
    try:
        with open("./cookies.json", "r") as f:
            sduwrap.cookies = json.load(f)
            if not sduwrap.cookies:
                raise FileNotFoundError
    except FileNotFoundError:
        import login

        cookies = login.login()
        if not cookies:
            raise Exception("Login failed")

        sduwrap.cookies = cookies

        with open("./cookies.json", "w") as f:
            json.dump(cookies, f)

    uvicorn.run(app, host="127.0.0.1", port=8000)
