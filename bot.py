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
    """Определяет ID текущего временного окна (UTC+2)"""
    now_utc = datetime.utcnow()
    # Хельсинки/Киев/Рига (UTC+2)
    now_local = now_utc + timedelta(hours=2)
    hour = now_local.hour
    date_str = now_local.strftime('%Y-%m-%d')
    
    if 11 <= hour < 13:
        return f"morning_{date_str}"
    elif 19 <= hour < 20:
        return f"evening_{date_str}"
    return None

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log(f"Ошибка чтения state.json: {e}")
    return {"initialized": False, "youtube": {}, "boosty": {}, "last_success_window": None}

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def send_telegram_notification(caption, photo_url=None):
    if not TOKEN or not CHAT_ID:
        log("ОШИБКА: Секреты не настроены!")
        return False
    
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
    state = load_state()
    window_id = get_current_window_id()
    
    # ПРОВЕРКА ЛИМИТА: если в этом окне (утро/вечер) уже был успех, выходим сразу
    if window_id and state.get('last_success_window') == window_id:
        log(f"В окне {window_id} контент уже опубликован. Спим до следующего цикла.")
        return

    any_new_post = False
    
    # 1. Проверка YouTube
    if YT_CHANNEL_IDS_STR:
        for channel_id in YT_CHANNEL_IDS_STR.split(','):
            channel_id = channel_id.strip()
            log(f"Проверка YouTube: {channel_id}")
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
                    if any_new_post: break # Нашли один — достаточно

    # 2. Проверка Boosty (если на YT ничего не нашли в этом проходе)
    if not any_new_post:
        log("Проверка Boosty...")
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
        except Exception as e:
            log(f"Boosty error: {e}")

    # ФИНАЛИЗАЦИЯ: если был пост, закрываем это окно
    if any_new_post and window_id:
        state['last_success_window'] = window_id
        log(f"Успех! Окно {window_id} помечено как выполненное.")

    if not state.get('initialized'):
        state['initialized'] = True
    
    save_state(state)

if __name__ == "__main__":
    main()
