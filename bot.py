import os
import json
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- НАСТРОЙКИ ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
YT_API_KEY = os.getenv('YOUTUBE_API_KEY')
YT_CHANNEL_IDS_STR = os.getenv('YOUTUBE_CHANNEL_ID', '') 
BOOSTY_BASE_URL = "https://boosty.to/freyasstory"
STATE_FILE = 'state.json'

def log(message):
    print(f"[LOG] {message}")

def get_current_window_id():
    """Определяет ID текущего окна (UTC+2) — ровно 60 минут"""
    now_utc = datetime.utcnow()
    now_local = now_utc + timedelta(hours=2)
    hour = now_local.hour
    minute = now_local.minute
    date_str = now_local.strftime('%Y-%m-%d')
    
    # Окно 1: 11:15 — 12:15
    if (hour == 11 and minute >= 15) or (hour == 12 and minute <= 15):
        return f"morning_{date_str}"
    
    # Окно 2: 19:15 — 20:15
    if (hour == 19 and minute >= 15) or (hour == 20 and minute <= 15):
        return f"evening_{date_str}"
        
    return None

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {"initialized": False, "youtube": {}, "boosty": {}, "last_success_window": None}

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def send_telegram_notification(caption, photo_url=None):
    if not TOKEN or not CHAT_ID: return False
    
    if photo_url:
        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        payload = {"chat_id": CHAT_ID, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200: return True
        except: pass

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except: return False

def main():
    window_id = get_current_window_id()
    
    if not window_id:
        log("SLEEP: Вне рабочих окон (11:15-12:15 или 19:15-20:15).")
        return

    state = load_state()
    
    if state.get('last_success_window') == window_id:
        log(f"DONE: В окне {window_id} уже была публикация.")
        return

    log(f"RUN: Проверка контента в окне {window_id}...")
    any_new_post = False
    
    # YouTube
    if YT_CHANNEL_IDS_STR:
        for channel_id in YT_CHANNEL_IDS_STR.split(','):
            channel_id = channel_id.strip()
            feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
            if feed.entries:
                entry = feed.entries[0]
                v_id, v_title, v_url = entry.yt_videoid, entry.title, entry.link
                chan_state = state['youtube'].get(channel_id, {})
                
                if chan_state.get('last_id') != v_id:
                    if state.get('initialized'):
                        caption = f"<b>НОВОЕ ВИДЕО ТРЭШ ИСТОРИИ УЖЕ НА ЮТУБ</b>\n\n<a href='{v_url}'>{v_title}</a>"
                        photo = f"https://img.youtube.com/vi/{v_id}/sddefault.jpg"
                        if send_telegram_notification(caption, photo):
                            any_new_post = True
                    state['youtube'][channel_id] = {"last_id": v_id, "title": v_title}
                    if any_new_post: break

    # Boosty
    if not any_new_post:
        try:
            r = requests.get(BOOSTY_BASE_URL, timeout=15)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                og_title = soup.find("meta", property="og:title")
                og_image = soup.find("meta", property="og:image")
                og_url = soup.find("meta", property="og:url")
                
                title = og_title.get("content", "") if og_title else ""
                image = og_image.get("content", "") if og_image else None
                link = og_url.get("content", BOOSTY_BASE_URL) if og_url else BOOSTY_BASE_URL
                fingerprint = f"{title}_{link}"

                if title and state['boosty'].get('last_id') != fingerprint:
                    if state.get('initialized'):
                        caption = f"<b>НОВОЕ ВИДЕО ТРЭШ ИСТОРИИ УЖЕ НА БУСТИ</b>\n\n<a href='{link}'>{title}</a>"
                        if send_telegram_notification(caption, image):
                            any_new_post = True
                    state['boosty']['last_id'] = fingerprint
        except: pass

    if any_new_post:
        state['last_success_window'] = window_id
        log(f"SUCCESS: Пост опубликован, окно {window_id} закрыто.")

    if not state.get('initialized'):
        state['initialized'] = True
    
    save_state(state)

if __name__ == "__main__":
    main()
