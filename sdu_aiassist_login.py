import re, hashlib, json, requests, uuid
from uniform_login_des import strEnc
from datetime import datetime, timezone


def login(sduid: str, password: str, fingerprint: str | None = None):
    session = requests.Session()
    
    if fingerprint is None:
        fingerprint = str(uuid.uuid4())
    
    page = session.get(
        "https://pass.sdu.edu.cn/cas/login",
        params={
            "service": "https://aiassist.sdu.edu.cn/common/actionCasLogin?redirect_url=https%3A%2F%2Faiassist.sdu.edu.cn%2Fpage%2Fsite%2FnewPc%3Flogin_return%3Dtrue"})
    lt = re.findall(r'"lt" value="(.*?)"', page.text)[0]
    rsa = strEnc(sduid + password + lt, "1", "2", "3")
    execution = re.findall('"execution" value="(.*?)"', page.text)[0]
    event_id = re.findall('"_eventId" value="(.*?)"', page.text)[0]
    murmur_s = hashlib.sha256(fingerprint.encode()).hexdigest()
    device_status = session.post(
        "https://pass.sdu.edu.cn/cas/device",
        data={
            "u": strEnc(sduid, "1", "2", "3"),
            "p": strEnc(password, "1", "2", "3"),
            "m": "1",
            "d": fingerprint, "d_s": murmur_s,
            "d_md5": hashlib.md5(murmur_s.encode()).hexdigest(),
        }
    )
    device_status_dict = json.loads(device_status.text)
    match device_status_dict.get("info"):
        case "binded" | "pass":
            pass
        case "bind":
            print("2FA:" + device_status_dict.get("m"))
            tmp = session.post(
                "https://pass.sdu.edu.cn/cas/device",
                data={
                    "u": strEnc(sduid, "1", "2", "3"),
                    "p": strEnc(password, "1", "2", "3"),
                    "m": "2",
                    "d": fingerprint, "d_s": murmur_s,
                    "d_md5": hashlib.md5(murmur_s.encode()).hexdigest(),
                }
            )
            try:
                tmp_json = json.loads(tmp.text)
                print(f"SMS verification code sent.")
            except:
                print(f"Warning: SMS send response: {tmp.text[:200]}")
            body = {
                "d": murmur_s, "i": fingerprint, "m": "3", "u": sduid,
                "c": input("Verification Code: "), "s": "1" if input(
                    "Remember this device? (y/N)：") == "y" else "0"}
            k = session.post("https://pass.sdu.edu.cn/cas/device",
                           data=body)
            while k.text == '{"info":"codeErr"}':
                body["c"] = input("Wrong, please retry: ")
                k = session.post("https://pass.sdu.edu.cn/cas/device",
                               data=body)
            if k.text == '{"info":"ok"}':
                print("Login successful.")
                if body["s"] == "1":
                    print(
                        f"For device fingerprint: {fingerprint}, the next login will no longer require a verification code")
            else:
                print(f"Device verification response: {k.text}")
                raise SystemError(
                    "Device verification failed: {}".format(k.text))
        case _:
            raise SystemError(
                "Unknown device status: {}".format(str(device_status_dict)))
    
    page = session.post(
        "https://pass.sdu.edu.cn/cas/login",
        params={
            "service": "https://aiassist.sdu.edu.cn/common/actionCasLogin?redirect_url=https%3A%2F%2Faiassist.sdu.edu.cn%2Fpage%2Fsite%2FnewPc%3Flogin_return%3Dtrue"},
        data={"rsa": rsa, "ul": len(sduid), "pl": len(password), "lt": lt,
              "execution": execution, "_eventId": event_id})
    
    cookies = {}
    for cookie in session.cookies:
        cookies[cookie.name] = cookie.value
    session.close()
    
    return {
        "cookies": cookies,
        "expires": datetime.now(timezone.utc)
    }
