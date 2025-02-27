import selenium
from selenium import webdriver
import time

# 打开 https://aiassist.sdu.edu.cn/ 等待跳转到 https://aiassist.sdu.edu.cn/page/site/newPc 再读取cookies

def login():
    driver = webdriver.Edge()
    driver.get("https://aiassist.sdu.edu.cn/")

    # 判断是否跳转到 https://aiassist.sdu.edu.cn/page/site/newPc
    while not driver.current_url.startswith("https://aiassist.sdu.edu.cn/page/site/newPc"):
        # Sleep 1s
        time.sleep(1)

    print(driver.current_url)

    cookies = driver.get_cookies()
    driver.quit()

    cookies = {cookie["name"]: cookie["value"] for cookie in cookies}

    return cookies


if __name__ == "__main__":
    print(login())