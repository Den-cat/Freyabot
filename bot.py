import os
import json
import requests
import feedparser
import re
from bs4 import BeautifulSoup

# Настройки мониторинга
YT_CHANNELS = [{"id": "UCpGzQ8G8qL3Qf1-n3-Y_rGg", "name": "voicemail"}]
BOOSTY_URL = "https://boosty.to/freyavoise"
STATE_FILE = "state.json"

def get_yt_latest(channel_id):
    try:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        feed = feedparser.parse(url)
        if not feed.entries: return None
        e = feed.entries[0]
        return {"id": e.yt_videoid, "url": e.link, "title": e.title, "img": f"https://i.ytimg.com/vi/{e.yt_videoid}/hqdefault.jpg"}
    except: return None

def get_boosty_latest():
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(BOOSTY_URL, headers=h, timeout=10)
        s = BeautifulSoup(r.text, 'lxml')
        sc = s.find("script", string=re.compile("initialState"))
        m = re.search(r'window.__initialState__s*=s*({.*?});', sc.string)
        d = json.loads(m.group(1))
        p = d.get('posts', {}).get('list', [])[0]
        return {"id": str(p['id']), "url": f"https://boosty.to/freyavoise/posts/{p['id']}", "title": p.get('title') or "Новое на Boosty", "img": p.get('teaser', [{}])[0].get('url', '') if p.get('teaser') else ""}
    except: return None

def send_tg(text, photo):
    t = os.environ.get("TELEGRAM_BOT_TOKEN")
    c = os.environ.get("TELEGRAM_CHAT_ID")
    if not t or not c: return
    try:
        if photo: requests.post(f"https://api.telegram.org/bot{t}/sendPhoto", data={"chat_id": c, "caption": text, "photo": photo, "parse_mode": "HTML"})
        else: requests.post(f"https://api.telegram.org/bot{t}/sendMessage", data={"chat_id": c, "text": text, "parse_mode": "HTML"})
    except: pass

def main():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f: state = json.load(f)
    else: state = {"initialized": False, "youtube": {}, "boosty": None}
    
    save = False
    for ch in YT_CHANNELS:
        l = get_yt_latest(ch['id'])
        if l and state.get("youtube", {}).get(ch['id']) != l['id']:
            if state.get("initialized"): send_tg(f"<b>{l['title']}</b>\n\nYouTube Update!\n{l['url']}", l['img'])
            state.setdefault("youtube", {})[ch['id']] = l['id']
            save = True
    
    b = get_boosty_latest()
    if b and state.get("boosty") != b['id']:
        if state.get("initialized"): send_tg(f"<b>{b['title']}</b>\n\nBoosty Exclusive!\n{b['url']}", b['img'])
        state["boosty"] = b['id']
        save = True
    
    if save or not state.get("initialized"):
        state["initialized"] = True
        with open(STATE_FILE, 'w') as f: json.dump(state, f, indent=2)

if __name__ == "__main__":
    main()