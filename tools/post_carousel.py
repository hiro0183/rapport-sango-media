"""Threadsにスワイプ（カルーセル）投稿する。
使い方: python tools/post_carousel.py <投稿定義.json>
定義: {"images": [公開URL...], "text": 1連目, "replies": [2連目以降...], "topic_tag": 任意}
トークンは threads_tool_rapport のものを使う（@rapport.sango）。
"""
import json
import sys
import time

sys.path.insert(0, r"C:\Users\tujid\threads_tool_rapport")
import requests
from threads_api import ThreadsAPI

BASE = "https://graph.threads.net/v1.0"


def wait_ready(api, cid, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        st = api._get(f"/{cid}", {"fields": "status,error_message"})
        if st.get("status") == "FINISHED":
            return
        if st.get("status") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"コンテナ失敗 {cid}: {st}")
        time.sleep(3)
    raise TimeoutError(f"コンテナ待ち超過 {cid}")


def create(api, uid, data):
    try:
        return api._post(f"/{uid}/threads", data)["id"]
    except requests.HTTPError as e:
        raise RuntimeError(f"作成失敗: {e.response.text[:400]}") from e


def main():
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    api = ThreadsAPI()
    uid = api._get("/me", {"fields": "id,username"})
    assert uid["username"] == "rapport.sango", f"投稿先が産後垢ではない: {uid['username']}"
    uid = uid["id"]

    children = []
    for url in spec["images"]:
        cid = create(api, uid, {"media_type": "IMAGE", "image_url": url, "is_carousel_item": "true"})
        children.append(cid)
    for cid in children:
        wait_ready(api, cid)

    parent = {"media_type": "CAROUSEL", "children": ",".join(children), "text": spec["text"]}
    if spec.get("topic_tag"):
        parent["topic_tag"] = spec["topic_tag"]
    try:
        pid = create(api, uid, parent)
    except RuntimeError:
        parent.pop("topic_tag", None)
        pid = create(api, uid, parent)
    wait_ready(api, pid)
    root = api._post(f"/{uid}/threads_publish", {"creation_id": pid})["id"]
    print("親投稿:", root)

    prev = root
    for t in spec.get("replies", []):
        time.sleep(5)
        rid = create(api, uid, {"media_type": "TEXT", "text": t, "reply_to_id": prev})
        wait_ready(api, rid)
        prev = api._post(f"/{uid}/threads_publish", {"creation_id": rid})["id"]
        print("返信:", prev)

    link = api._get(f"/{root}", {"fields": "permalink"}).get("permalink")
    print("URL:", link)


if __name__ == "__main__":
    main()
