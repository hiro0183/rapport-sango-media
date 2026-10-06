"""毎朝9:00（PCのタスクスケジューラ）: 今日の posts/YYYY-MM-DD.json があればスワイプ投稿する。
- 二重投稿防止: posted/YYYY-MM-DD.json があれば何もしない
- 失敗したら hisho repo に Issue「🚨 産後マンガ投稿失敗」を立てる（GitHubから通知が届く）
- PCが寝ていて遅れて起動した場合、12:00を過ぎていたら投稿せず Issue だけ立てる（昼以降に朝の投稿が出るのを防ぐ）
- トークンの期限が20日を切ったら更新し、hisho の見張り用 Secret も更新する
"""
import base64
import datetime as dt
import json
import subprocess
import sys
import traceback
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from post_carousel import post, RAPPORT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
JST = dt.timezone(dt.timedelta(hours=9))
HISHO = "hiro0183/hisho"
LATEST_HOUR = 12


def gh_token() -> str:
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True).stdout
    return next(l.split("=", 1)[1] for l in out.splitlines() if l.startswith("password="))


def gh(method, path, **kw):
    r = requests.request(method, f"https://api.github.com{path}",
                         headers={"Authorization": f"token {gh_token()}",
                                  "Accept": "application/vnd.github+json"}, timeout=60, **kw)
    r.raise_for_status()
    return r.json() if r.text else {}


def alert(title: str, body: str):
    try:
        gh("POST", f"/repos/{HISHO}/issues", json={"title": title, "body": body, "labels": ["🚨産後マンガ"]})
    except Exception as e:  # 通知の失敗で落ちない
        print("Issue作成も失敗:", e)


def refresh_token_if_needed():
    tf = Path(RAPPORT) / "tokens.json"
    t = json.loads(tf.read_text())
    left = dt.datetime.fromisoformat(t["expires_at"]) - dt.datetime.now()
    if left > dt.timedelta(days=20):
        return
    r = requests.get("https://graph.threads.net/refresh_access_token",
                     params={"grant_type": "th_refresh_token", "access_token": t["access_token"]}, timeout=60)
    r.raise_for_status()
    new = r.json()
    now = dt.datetime.now()
    t.update(access_token=new["access_token"], expires_in=new["expires_in"], refreshed_at=now.isoformat(),
             expires_at=(now + dt.timedelta(seconds=new["expires_in"])).isoformat())
    tf.write_text(json.dumps(t, indent=2))
    update_secret("SANGO_THREADS_TOKEN", new["access_token"])
    print("トークン更新:", t["expires_at"])


def update_secret(name: str, value: str):
    from nacl import encoding, public
    key = gh("GET", f"/repos/{HISHO}/actions/secrets/public-key")
    box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
    enc = base64.b64encode(box.encrypt(value.encode())).decode()
    gh("PUT", f"/repos/{HISHO}/actions/secrets/{name}", json={"encrypted_value": enc, "key_id": key["key_id"]})


def main():
    now = dt.datetime.now(JST)
    day = now.strftime("%Y-%m-%d")
    spec_file = ROOT / "posts" / f"{day}.json"
    done_file = ROOT / "posted" / f"{day}.json"
    if done_file.exists():
        print("投稿済み:", day)
        return
    if not spec_file.exists():
        print("今日の投稿定義なし:", day)
        return
    if now.hour >= LATEST_HOUR:
        alert(f"🚨 産後マンガ {day} 9:00に投稿できず（PCが{now:%H:%M}まで起動せず）",
              f"PCが寝ていたため、9:00の投稿が出ていません。{now:%H:%M}に起動しましたが、昼を過ぎたので自動では出していません。\n"
              f"出すなら Claude に「{day}の産後マンガを今出して」と頼んでください。")
        return
    try:
        refresh_token_if_needed()
    except Exception as e:
        print("トークン更新失敗（投稿は続ける）:", e)
    try:
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
        root, link = post(spec)
        done_file.parent.mkdir(exist_ok=True)
        done_file.write_text(json.dumps({"root": root, "url": link, "at": now.isoformat()}, ensure_ascii=False))
        print("投稿成功:", link)
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        alert(f"🚨 産後マンガ {day} 9:00の投稿に失敗", f"エラー内容:\n```\n{tb[-3000:]}\n```")
        sys.exit(1)


if __name__ == "__main__":
    main()
