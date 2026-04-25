import subprocess
import sys
import time
import signal
import json
import uuid
import requests
import sduwrap
import sdu_aiassist_login as login
import getpass
import warnings

try:
    import readline
except ImportError:
    readline = None

warnings.filterwarnings("ignore")

HISTORY_FILE = ".cli_history"
API_BASE = "http://127.0.0.1:8000"


def load_or_login():
    try:
        with open("./cookies.json", "r") as f:
            cookies = json.load(f)
            if not cookies:
                raise FileNotFoundError
        sduwrap.cookies = cookies
        print("已加载登录状态")
    except FileNotFoundError:
        print("未找到cookies.json，正在登录...")
        sdu_id = input("请输入您的SDU学号: ")
        password = getpass.getpass("请输入您的密码: ")

        try:
            with open("./fingerprint.txt", "r") as f:
                fingerprint = f.read().strip()
        except FileNotFoundError:
            fingerprint = input("请输入设备指纹(留空自动生成): ")
            if not fingerprint:
                fingerprint = str(uuid.uuid4())
            with open("./fingerprint.txt", "w") as f:
                f.write(fingerprint)
        fingerprint = str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint))

        login_result = login.login(sdu_id, password, fingerprint)
        cookies = login_result["cookies"]
        if not cookies:
            raise Exception("登录失败")

        sduwrap.cookies = cookies

        with open("./cookies.json", "w") as f:
            json.dump(cookies, f)
        print("登录成功，已保存cookies")


def start_server():
    print("[Server] 正在启动本地 API 服务...")
    log_file = open("server.log", "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"],
        stdout=subprocess.DEVNULL,
        stderr=log_file,
    )
    for _ in range(30):
        try:
            r = requests.get(f"{API_BASE}/v1/models", timeout=1)
            if r.status_code == 200:
                print("[Server] 服务已就绪 (日志: server.log)")
                return proc
        except Exception:
            pass
        time.sleep(0.5)
    print("[Server] 启动超时，请检查 server.log 查看错误日志")
    proc.terminate()
    sys.exit(1)


def setup_readline():
    if readline is None:
        return
    try:
        readline.read_history_file(HISTORY_FILE)
        readline.set_history_length(1000)
    except FileNotFoundError:
        pass


def save_readline_history():
    if readline is None:
        return
    try:
        readline.write_history_file(HISTORY_FILE)
    except Exception:
        pass


def select_model(model_ids):
    print("可用模型：")
    for i, m in enumerate(model_ids, 1):
        print(f"  {i}. {m}")
    while True:
        choice = input("请选择模型编号: ").strip()
        if not choice:
            print("无效选择，请重新输入")
            continue
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(model_ids):
                return model_ids[idx]
        except ValueError:
            pass
        print("无效选择，请重新输入")


def print_stream(resp):
    full_content = ""
    full_reasoning = ""
    got_data = False
    for line in resp.iter_lines():
        if line:
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if text.startswith("data: "):
                data = text[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    got_data = True
                    if chunk.get("error"):
                        print(f"\n[API错误]: {chunk['error']}", end="", flush=True)
                        continue
                    delta = chunk["choices"][0].get("delta", {})
                    if delta.get("reasoning_content"):
                        print(f"\n[思考]: {delta['reasoning_content']}", end="", flush=True)
                        full_reasoning += delta["reasoning_content"]
                    if delta.get("content"):
                        print(delta["content"], end="", flush=True)
                        full_content += delta["content"]
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"\n[解析错误]: {e} | 原始数据: {data[:200]}", end="", flush=True)
    if not got_data:
        print("\n[警告] 服务端未返回任何数据", end="", flush=True)
    elif not full_content and not full_reasoning:
        print("\n[警告] 服务端返回了空内容", end="", flush=True)
    print()
    return full_content, full_reasoning


# ========== 客户端工具定义 ==========

def execute_tool(name: str, arguments: dict) -> str:
    if name == "get_random_number":
        import random
        min_val = arguments.get("min", 1)
        max_val = arguments.get("max", 100)
        return str(random.randint(min_val, max_val))
    elif name == "get_system_time":
        from datetime import datetime
        return datetime.now().strftime("%Y年%m月%d日 %H时%M分%S秒 %A")
    elif name == "calculator":
        import ast
        import operator
        expression = arguments.get("expression", "")
        allowed_ops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.USub: operator.neg,
            ast.Pow: operator.pow,
        }
        def eval_node(node):
            if isinstance(node, ast.Constant):
                return node.value
            elif isinstance(node, ast.BinOp):
                op = allowed_ops.get(type(node.op))
                if op is None:
                    raise ValueError(f"不支持的运算符: {type(node.op)}")
                return op(eval_node(node.left), eval_node(node.right))
            elif isinstance(node, ast.UnaryOp):
                op = allowed_ops.get(type(node.op))
                if op is None:
                    raise ValueError(f"不支持的一元运算符: {type(node.op)}")
                return op(eval_node(node.operand))
            elif isinstance(node, ast.Expression):
                return eval_node(node.body)
            else:
                raise ValueError(f"不支持的表达式类型: {type(node)}")
        try:
            tree = ast.parse(expression, mode="eval")
            result = eval_node(tree)
            return str(result)
        except Exception as e:
            return f"计算错误: {str(e)}"
    else:
        return f"错误: 未知工具 '{name}'"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_random_number",
            "description": "获取一个指定范围内的随机整数",
            "parameters": {
                "type": "object",
                "properties": {
                    "min": {"type": "integer", "description": "最小值，默认为 1"},
                    "max": {"type": "integer", "description": "最大值，默认为 100"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_time",
            "description": "获取当前系统时间和日期信息",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算器，执行简单的数学表达式（支持 + - * / 和括号）",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式，例如 1+2*3"}
                },
                "required": ["expression"],
            },
        },
    },
]


def parse_tool_calls_from_content(content: str) -> List[dict]:
    """客户端 fallback 解析 content 中的 <tool_call> 标签"""
    import re
    pattern = r"<tool_call>\s*(.*?)\s*</tool_call>"
    matches = re.findall(pattern, content, re.DOTALL)
    tool_calls = []
    for match in matches:
        data = None
        try:
            data = json.loads(match)
        except json.JSONDecodeError:
            try:
                import ast
                data = ast.literal_eval(match.strip())
            except Exception:
                pass
        if isinstance(data, dict) and "name" in data:
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": data["name"],
                    "arguments": json.dumps(data.get("arguments", {}), ensure_ascii=False)
                }
            })
    return tool_calls


def _stream_chat(model_name: str, history: list) -> str:
    """发送流式请求并逐字打印"""
    payload = {
        "model": model_name,
        "messages": history,
        "stream": True,
    }
    resp = requests.post(
        f"{API_BASE}/v1/chat/completions",
        json=payload,
        stream=True,
        timeout=300,
    )
    resp.raise_for_status()
    full_content, _ = print_stream(resp)
    return full_content


def chat_with_tools(model_name: str, history: list, tools: list) -> str:
    """客户端 ReAct 循环：发送请求 → 执行工具 → 获取最终答案
    
    策略：
    - 第一轮必须非流式，以便可靠解析 tool_calls
    - 若不需要工具，重发流式请求给用户看打字机效果
    - 执行工具后，第二轮直接走流式输出最终答案
    """
    max_rounds = 5
    for round_idx in range(max_rounds):
        # 如果已经执行过工具（round_idx > 0），直接走流式输出最终答案
        if round_idx > 0:
            return _stream_chat(model_name, history)

        # 第一轮：非流式判断是否需要工具
        payload = {
            "model": model_name,
            "messages": history,
            "tools": tools,
            "stream": False,
        }
        resp = requests.post(
            f"{API_BASE}/v1/chat/completions",
            json=payload,
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        message = choice["message"]

        tool_calls = message.get("tool_calls", [])
        
        # Fallback：如果服务端没解析到 tool_calls，但 content 里有 <tool_call>，客户端自己解析
        if not tool_calls and message.get("content"):
            tool_calls = parse_tool_calls_from_content(message["content"])

        if choice["finish_reason"] == "tool_calls" or tool_calls:
            if not tool_calls:
                # 服务端标记了 tool_calls 但解析不到，直接输出 content
                content = message.get("content", "")
                reasoning = message.get("reasoning_content", "")
                if reasoning:
                    print(f"\n[思考]: {reasoning}")
                print(content)
                return content

            # 添加 assistant 的 tool_calls 到历史
            history.append({
                "role": "assistant",
                "content": message.get("content", ""),
                "tool_calls": tool_calls,
            })

            # 执行工具
            for tc in tool_calls:
                fn = tc["function"]
                name = fn["name"]
                arguments = json.loads(fn["arguments"])
                result = execute_tool(name, arguments)
                print(f"[调用工具] {name}({json.dumps(arguments, ensure_ascii=False)}) → {result}")
                history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": f"[{name}] 执行结果：{result}",
                })
            # 继续下一轮（会走 _stream_chat 流式输出最终答案）
        else:
            # 不需要工具，这是普通对话。重发流式请求给用户看打字机效果
            return _stream_chat(model_name, history)

    return "[错误] 工具调用轮数超过上限"


def main():
    load_or_login()
    server_proc = start_server()

    def cleanup(signum=None, frame=None):
        print("\n[Server] 正在关闭...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()
        save_readline_history()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    setup_readline()

    models_resp = requests.get(f"{API_BASE}/v1/models").json()
    model_ids = [m["id"] for m in models_resp.get("data", [])]
    if not model_ids:
        print("[Error] 无法获取模型列表")
        cleanup()

    model_name = select_model(model_ids)

    use_tools = True
    history = []

    print("\n=== 山东大学AI助手CLI对话工具 ===")
    print("输入 'quit' 或 'exit' 退出")
    print("输入 'clear' 清空对话历史")
    print("输入 'model' 切换模型")
    print("输入 'tools' 开启/关闭工具调用")
    print("支持方向键移动光标、上下键查看历史输入、退格删除中文\n")
    print(f"当前模型: {model_name}")
    print(f"工具调用: {'开启' if use_tools else '关闭'}\n")

    while True:
        try:
            user_input = input("\n你: ").strip()
        except (KeyboardInterrupt, EOFError):
            cleanup()

        if user_input.lower() in ["quit", "exit"]:
            cleanup()

        if user_input.lower() == "clear":
            history = []
            print("对话历史已清空")
            continue

        if user_input.lower() == "model":
            model_name = select_model(model_ids)
            print(f"已切换模型: {model_name}")
            continue

        if user_input.lower() == "tools":
            use_tools = not use_tools
            print(f"工具调用: {'开启' if use_tools else '关闭'}")
            continue

        if not user_input:
            continue

        history.append({"role": "user", "content": user_input})

        try:
            if use_tools:
                print(f"{model_name}: ", end="", flush=True)
                content = chat_with_tools(model_name, history, TOOLS)
                history.append({"role": "assistant", "content": content})
            else:
                payload = {
                    "model": model_name,
                    "messages": history,
                    "stream": True,
                }
                print(f"{model_name}: ", end="", flush=True)
                resp = requests.post(
                    f"{API_BASE}/v1/chat/completions",
                    json=payload,
                    stream=True,
                    timeout=300,
                )
                resp.raise_for_status()
                full_content, _ = print_stream(resp)
                history.append({"role": "assistant", "content": full_content})

        except Exception as e:
            print(f"\n错误: {e}")

    cleanup()


if __name__ == "__main__":
    main()
