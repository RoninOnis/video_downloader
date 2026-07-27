# 0xONI Downloader v2.0

Универсальный веб-загрузчик видео с 1800+ сайтов на NiceGUI.

---

## ✨ Возможности

| Фича | Описание |
|------|----------|
| 🌐 **1800+ сайтов** | YouTube, Rutube, VK, VK Video, Dzen, Bilibili, Twitch и др. |
| 🔧 **Site-specific** | Автонастройка `extractor_args`, `referer`, `User-Agent` под каждую площадку |
| 🍪 **Browser cookies** | Автоматический подхват cookies из браузера для VK и Twitch |
| 📋 **Плейлисты/каналы** | Анализ, выбор видео, многопоточная загрузка (3 потока) |
| 📊 **Форматы с размерами** | Показывает размер файла для каждого качества перед загрузкой |
| 🎵 **MP3** | Извлечение аудиодорожки |
| 📝 **Субтитры** | Автоскачивание RU/EN субтитров |
| ✂️ **Обрезка** | Двойной ползунок (range slider) + ручной ввод — ffmpeg режет без перекодировки |
| 🔄 **Автообновление yt-dlp** | Проверка и установка свежей версии |
| ☀️🌙 **Тёмная/светлая тема** | Переключатель тем |
| 📜 **История + лог** | Полная история загрузок и детальный лог |

---

## 🚀 Запуск

```bash
pip install yt-dlp nicegui browser-cookie3 aiohttp
python yt-load.py
# Открыть http://localhost:8765
```

---

## 📦 Сборка в .exe (Windows)

```bash
python build.py web
```

EXE-файл будет в папке `dist/`. При запуске открывает браузер на `localhost:8765`.

---

## 🛠 Требования

- Python 3.8+
- FFmpeg (для конвертации в MP3 и обрезки)
- `yt-dlp`, `nicegui`, `browser-cookie3`, `aiohttp`

---

## 🔗 Ссылки

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — движок загрузки
- [NiceGUI](https://nicegui.io/) — веб-фреймворк
- [Video-Grabber](https://github.com/Almarus/Video-Grabber/) — вдохновение для site-specific фич
