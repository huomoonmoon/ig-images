#!/usr/bin/env python3
"""雲端發文（GitHub Actions 執行）：從 queue/ 挑最舊、還沒發的一篇發到 @symbiosis_ore。

queue/post-NN/ 裡放 01.jpg…（2–10 張）與 caption.txt；發完寫 published.json。
流程依 Meta〈內容發佈〉：圖片 JPEG、公開網址 → 每張建 is_carousel_item 容器 → CAROUSEL 容器
→ 等 status_code=FINISHED → media_publish。權杖來自 GitHub secret IG_TOKEN。
DRY_RUN=1 時建好輪播容器就停，不發佈。
"""
import datetime, glob, json, os, subprocess, time, urllib.error, urllib.parse, urllib.request

PAGES = "https://huomoonmoon.github.io/ig-images"
IG_ID = "17841442829112510"
API = "https://graph.instagram.com/v26.0"
TOKEN = os.environ["IG_TOKEN"]
DRY = os.environ.get("DRY_RUN") == "1"


def call(method, path, **params):
    data = urllib.parse.urlencode(params).encode() if method == "POST" else None
    url = f"{API}/{path}" + ("" if method == "POST" else "?" + urllib.parse.urlencode(params))
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"API 錯誤 {path}：{e.read().decode()[:300]}")


def pending():
    return [d for d in sorted(glob.glob("queue/post-*")) if not os.path.exists(f"{d}/published.json")]


def main():
    todo = pending()
    if not todo:
        raise SystemExit("存稿用完了，沒有可發的篇")
    post = todo[0]
    imgs = sorted(glob.glob(f"{post}/0[1-9].jpg")) + sorted(glob.glob(f"{post}/10.jpg"))
    if not 2 <= len(imgs) <= 10:
        raise SystemExit(f"{post} 圖片數 {len(imgs)} 不在 2–10 張")
    caption = open(f"{post}/caption.txt", encoding="utf-8").read().strip()
    urls = [f"{PAGES}/{p}" for p in imgs]
    for u in urls:  # 確認 Pages 上真的抓得到
        urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=30)
    kids = [call("POST", f"{IG_ID}/media", image_url=u, is_carousel_item="true")["id"] for u in urls]
    cid = call("POST", f"{IG_ID}/media", media_type="CAROUSEL", children=",".join(kids), caption=caption)["id"]
    for _ in range(30):
        s = call("GET", cid, fields="status_code").get("status_code")
        if s == "FINISHED":
            break
        if s in ("ERROR", "EXPIRED"):
            raise SystemExit(f"輪播容器狀態 {s}")
        time.sleep(10)
    else:
        raise SystemExit("輪播容器 5 分鐘內沒處理完")
    if DRY:
        print(f"[dry-run] {post}：{len(kids)} 張已建成輪播草稿，未發佈")
        return
    mid = call("POST", f"{IG_ID}/media_publish", creation_id=cid)["id"]
    link = call("GET", mid, fields="permalink").get("permalink", "")
    json.dump({"published_at": datetime.datetime.utcnow().isoformat() + "Z", "media_id": mid, "permalink": link},
              open(f"{post}/published.json", "w"), ensure_ascii=False, indent=1)
    print(f"已發佈 {post} {link}")
    left = len(pending())
    print(f"剩餘存稿 {left} 篇")
    if left <= 2:  # 開 issue，GitHub 會寄信通知
        subprocess.run(["gh", "issue", "create", "-t", f"IG 存稿剩 {left} 篇，該做下一批了",
                        "-b", f"剛發佈 {post}（{link}）。請跟 Claude 說「做一批」。"], check=False)


if __name__ == "__main__":
    main()
