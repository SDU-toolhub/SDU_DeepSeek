import requests
import json

cookies = {}

url = "https://aiassist.sdu.edu.cn/site/ai/compose_chat"


class ChatSession:
    def __init__(self):
        self.role = "user"  # user or assistant
        self.content = ""


class ChatConfig:
    def __init__(self):
        self.compose_id = 73
        self.auth_tag = "本科生"
        self.deep_search = 1  # 深度思考
        self.internet_search = 1  # 网络搜索


def history_to_form_data(history):
    form_data = {}
    for i, chat_session in enumerate(history):
        form_data[f"history[{i}][role]"] = chat_session.role
        form_data[f"history[{i}][content]"] = chat_session.content
    return form_data


def make_chat_request(content, history, config):
    form_data = history_to_form_data(history)
    form_data["content"] = content
    form_data["compose_id"] = config.compose_id
    form_data["auth_tag"] = config.auth_tag
    form_data["deep_search"] = config.deep_search
    form_data["internet_search"] = config.internet_search
    return form_data


def chat(content, history, config):
    form_data = make_chat_request(content, history, config)
    # response = requests.post(url, data=form_data, cookies=cookies,verify=False)

    # 流式输出
    response = requests.post(url, data=form_data, cookies=cookies, stream=True, verify=False) # 防止开了代理没法用
    for line in response.iter_lines():
        if line:
            # line.decode('utf-8') - data: {"e":0,"m":"操作成功","d":{"type":"0","answer":"<think>好的","url":"","message_id":"","id":"","recommend_data":[],"source":[],"ext":[]}}
            text = line.decode('utf-8')
            if text.startswith('data: '):
                text = text[6:]
                json_data = json.loads(text)

                yield json_data["d"]["answer"]


if __name__ == "__main__":
    for i in chat("如何评价山东大学", [], ChatConfig()):
        print(i, end="")
