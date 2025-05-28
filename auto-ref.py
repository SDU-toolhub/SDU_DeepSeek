
import json
import uuid
import sdu_aiassist_login as login
import time

while True:
    print("Please confirm that you have successfully logged in and then leave this program running.")
    with open("./userinfo.csv", "r") as f:
        sdu_id, password = f.read().strip().split(",")
    if not sdu_id or not password:
        exit(1)
    # fingerprint = input("Please enter your fingerprint(Any String For Generate Random UUID): ")
    # try read fingerprint from file
    try:
        with open("./fingerprint.txt", "r") as f:
            fingerprint = f.read().strip()
    except FileNotFoundError:
        # generate random uuid
        fingerprint = input("Please enter your fingerprint(Empty to generate one): ")
        if not fingerprint:
            fingerprint = str(uuid.uuid4())
        with open("./fingerprint.txt", "w") as f:
            f.write(fingerprint)
    fingerprint = str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint))

    cookies = login.login(sdu_id, password, fingerprint)["cookies"]
    if not cookies:
        raise Exception("Login failed")

    with open("./cookies.json", "w") as f:
        json.dump(cookies, f)

    print("Login successful, cookies saved to ./cookies.json")
    print("You can now leave this program running.")
    print("It will automatically refresh the cookies every 24 hours.")
    print("Press Ctrl+C to exit.")

    
    time.sleep(24 * 60 * 60)  # Sleep for 24 hours

    # If you want to exit the loop, you can use a keyboard interrupt (Ctrl+C)
