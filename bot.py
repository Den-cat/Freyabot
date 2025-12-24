import os
import json
import time
import requests
import feedparser
from bs4 import BeautifulSoup

# --- НАСТРОЙКИ ИЗ СЕКРЕТОВ GITHUB ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')  # Например, @freyasstory
YT_API_KEY = os.getenv('YOUTUBE_API_KEY')
# Если ID канала не задан в секретах, можно вставить его прямо сюда вместо None
YT_CHANNEL_ID = os.getenv('YOUTUBE_CHANNEL_ID', 'UC_ваша_строка_id') 
BOOSTY_URL = "https://boosty.to/freyasstory"

STATE_FILE = 'state.json'

def log(message):
    print(f"[LOG] {message}")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"initialized": False, "youtube": {}, "boosty": {}}

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        log("ОШИБКА: Токен или Chat ID не настроены!")
        return False
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload)
        if r.status_code == 200:
            log("Сообщение успешно отправлено в Telegram!")
            return True
        else:
            log(f"ОШИБКА TG: {r.text}")
            return False
    except Exception as e:
        log(f"Ошибка при отправке: {e}")
        return False

def check_youtube(state):
    log("Проверяю YouTube...")
    video_id = None
    video_title = None
    video_url = None

    # ПРИОРЕТЕТ 1: YouTube API (Быстрый режим)
    if YT_API_KEY and YT_CHANNEL_ID:
        log("Использую YouTube API v3 для мгновенной проверки.")
        api_url = f"https://www.googleapis.com/youtube/v3/search?key={YT_API_KEY}&channelId={YT_CHANNEL_ID}&part=snippet,id&order=date&maxResults=1"
        try:
            res = requests.get(api_url).json()
            item = res.get('items', [])[0]
            video_id = item['id']['videoId']
            video_title = item['snippet']['title']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
        except Exception as e:
            log(f"Ошибка API (возможно, лимиты): {e}. Пробую RSS...")

    # ПРИОРЕТЕТ 2: RSS (Запасной / Медленный режим)
    if not video_id:
        log("Использую RSS ленту.")
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YT_CHANNEL_ID}"
        feed = feedparser.parse(rss_url)
        if feed.entries:
            entry = feed.entries[0]
            video_id = entry.yt_videoid
            video_title = entry.title
            video_url = entry.link

    if not video_id:
        log("Видео на YouTube не найдены.")
        return state

    # Проверка на новизну
    last_id = state['youtube'].get('last_id')
    if last_id != video_id:
        log(f"НАЙДЕНО НОВОЕ ВИДЕО: {video_title}")
        if state.get('initialized'):
            msg = f"<b>Новое видео на YouTube!</b>\n\n{video_title}\n\n<a href='{video_url}'>Смотреть прямо сейчас</a>"
            send_telegram(msg)
        state['youtube']['last_id'] = video_id
        state['youtube']['last_title'] = video_title
    else:
        log("Новых видео на YouTube нет.")
    
    return state

def check_boosty(state):
    log("Проверяю Boosty...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(BOOSTY_URL, headers=headers)
        soup = BeautifulSoup(r.text, 'lxml')
        
        # Поиск последнего поста (упрощенный поиск по селекторам Boosty)
        # Примечание: Boosty часто меняет классы, это базовый пример
        post = soup.find('div', class_=lambda x: x and 'Post_root' in x)
        if not post:
            log("Не удалось найти посты на Boosty (возможно, изменился дизайн сайта).")
            return state

        # Генерируем ID поста на основе текста или ссылки, если нет явного
        post_link = BOOSTY_URL
        post_title = "Новый эксклюзивный пост!"
        
        # Пытаемся найти уникальный идентификатор
        post_id = str(hash(post.text[:100])) 

        last_id = state['boosty'].get('last_id')
        if last_id != post_id:
            log("НАЙДЕН НОВЫЙ ПОСТ НА BOOSTY!")
            if state.get('initialized'):
                msg = f"<b>Новый пост на Boosty!</b>\n\n{post_title}\n\n<a href='{post_link}'>Перейти к посту</a>"
                send_telegram(msg)
            state['boosty']['last_id'] = post_id
        else:
            log("Новых постов на Boosty нет.")
    except Exception as e:
        log(f"Ошибка при проверке Boosty: {e}")
    
    return state

def main():
    log("Запуск проверки контента...")
    state = load_state()
    
    # Проверяем ресурсы
    state = check_youtube(state)
    state = check_boosty(state)
    
    # Если это был первый запуск, помечаем систему как инициализированную
    if not state.get('initialized'):
        log("Первая инициализация завершена. Теперь я буду присылать только новые посты.")
        state['initialized'] = True
    
    save_state(state)
    log("Проверка завершена успешно.")

if __name__ == "__main__":
    main()
