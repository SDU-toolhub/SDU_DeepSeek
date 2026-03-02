import sduwrap
from sduwrap import ChatConfig
import json
import uuid
import sdu_aiassist_login as login
import getpass
import warnings

warnings.filterwarnings("ignore")


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


def main():
    load_or_login()

    print("\n=== 山东大学DeepSeek CLI对话工具 ===")
    print("输入 'quit' 或 'exit' 退出")
    print("输入 'clear' 清空对话历史\n")

    history = []
    config = ChatConfig()

    while True:
        try:
            user_input = input("\n你: ").strip()
        except KeyboardInterrupt:
            print("\n再见！")
            break

        if user_input.lower() in ["quit", "exit"]:
            print("再见！")
            break

        if user_input.lower() == "clear":
            history = []
            print("对话历史已清空")
            continue

        if not user_input:
            continue

        print("DeepSeek: ", end="", flush=True)
        full_response = ""
        try:
            for chunk in sduwrap.chat(user_input, history, config):
                print(chunk, end="", flush=True)
                full_response += chunk
            print()

            user_session = sduwrap.ChatSession()
            user_session.role = "user"
            user_session.content = user_input
            history.append(user_session)

            assistant_session = sduwrap.ChatSession()
            assistant_session.role = "assistant"
            assistant_session.content = full_response
            history.append(assistant_session)

        except Exception as e:
            print(f"\n错误: {e}")


if __name__ == "__main__":
    main()
