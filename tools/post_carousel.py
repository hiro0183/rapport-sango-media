"""Threadsにスワイプ（カルーセル）投稿する。
使い方: python tools/post_carousel.py <投稿定義.json>
定義: {"images": [公開URL...], "text": 1連目, "replies": [2連目以降...], "topic_tag": 任意}
トークンは threads_tool_rapport の tokens.json（@rapport.sango）を使う。作業フォルダはどこでもよい。
"""
import json
import os
import sys
import time

RAPPORT = r"C:\Users\tujid\threads_tool_rapport"
sys.path.insert(0, RAPPORT)
import requests


def _api():
    # threads_auth は tokens.json を作業フォルダから読むので、読む間だけ移動する
    cwd = os.getcwd()
    os.chdir(RAPPORT)
    try:
        from threads_auth import load_tokens
        tokens = load_tokens()
    finally:
        os.chdir(cwd)
    if not tokens:
        raise RuntimeError("tokens.json が読めない（認証フローは起動しない）")
    from threads_api import ThreadsAPI
    api = ThreadsAPI.__new__(ThreadsAPI)
    api.access_token = tokens["access_token"]
    api.user_id = None
    return api


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


def post(spec: dict) -> tuple[str, str]:
    """投稿して (親投稿ID, URL) を返す"""
    api = _api()
    me = api._get("/me", {"fields": "id,username"})
    if me["username"] != "rapport.sango":
        raise RuntimeError(f"投稿先が産後垢ではない: {me['username']}")
    uid = me["id"]

    children = [create(api, uid, {"media_type": "IMAGE", "image_url": u, "is_carousel_item": "true"})
                for u in spec["images"]]
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

    prev = root
    for t in spec.get("replies", []):
        time.sleep(5)
        rid = create(api, uid, {"media_type": "TEXT", "text": t, "reply_to_id": prev})
        wait_ready(api, rid)
        prev = api._post(f"/{uid}/threads_publish", {"creation_id": rid})["id"]

    link = api._get(f"/{root}", {"fields": "permalink"}).get("permalink", "")
    return root, link


if __name__ == "__main__":
    root, link = post(json.load(open(sys.argv[1], encoding="utf-8")))
    print("親投稿:", root)
    print("URL:", link)
