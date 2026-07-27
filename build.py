# build.py — сборка 0xONI Downloader в .exe (Windows)
import subprocess
import sys
import os
import locale

def setup_encoding():
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8')
    except:
        try:
            encoding = locale.getpreferredencoding()
            sys.stdout.reconfigure(encoding=encoding)
        except:
            pass

def print_msg(message):
    try:
        print(message)
    except UnicodeEncodeError:
        safe = message.replace('✅','[OK]').replace('⏳','[WAIT]').replace('🏗️','[BUILD]')
        safe = safe.replace('📁','[FOLDER]').replace('🚀','[ROCKET]').replace('🎉','[PARTY]')
        safe = safe.replace('💡','[TIP]').replace('❌','[ERROR]').replace('🌐','[WEB]')
        print(safe)

def install_dependencies():
    deps = ['yt-dlp', 'pyinstaller', 'nicegui', 'browser-cookie3', 'aiohttp']
    for pkg in deps:
        try:
            __import__(pkg.replace('-', '_'))
            print_msg(f"✅ {pkg} уже установлен")
        except ImportError:
            print_msg(f"⏳ Устанавливаем {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
            print_msg(f"✅ {pkg} успешно установлен")

def build_executable():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'web'
    
    if mode == 'desktop':
        # Десктопная Tkinter-версия
        script = 'universal_downloader.py'
        name = '0xONI_Downloader_Desktop'
        windowed = True
        hidden = ['yt_dlp', 'yt_dlp.extractor', 'yt_dlp.downloader', 'yt_dlp.postprocessor']
    else:
        # Веб-версия NiceGUI
        script = 'yt-load.py'
        name = '0xONI_Downloader_Web'
        windowed = False  # консольное окно нужно для вывода URL
        hidden = [
            'yt_dlp', 'yt_dlp.extractor', 'yt_dlp.downloader',
            'nicegui', 'browser_cookie3', 'aiohttp',
        ]
    
    print_msg(f"🏗️ Сборка {name} из {script}...")
    
    cmd = [
        'pyinstaller',
        '--onefile',
        '--name', name,
        '--collect-all', 'yt_dlp',
        '--collect-all', 'nicegui',
    ]
    
    if windowed:
        cmd.append('--windowed')
    
    for imp in hidden:
        cmd.extend(['--hidden-import', imp])
    
    if os.path.exists('icon.ico'):
        cmd.extend(['--icon', 'icon.ico'])
    
    cmd.append(script)
    
    try:
        subprocess.check_call(cmd)
        print_msg("✅ Сборка завершена успешно!")
        print_msg(f"📁 EXE файл: dist/{name}.exe")
        print_msg("🚀 Готово к распространению!")
        return True
    except subprocess.CalledProcessError as e:
        print_msg(f"❌ Ошибка сборки: {e}")
        return False
    except Exception as e:
        print_msg(f"❌ Неожиданная ошибка: {e}")
        return False

def main():
    setup_encoding()
    print_msg("=" * 50)
    print_msg("0xONI Downloader — Сборка EXE")
    print_msg("=" * 50)
    print_msg("")
    print_msg("Режимы: python build.py web     (веб-версия NiceGUI)")
    print_msg("        python build.py desktop (десктопная Tkinter)")
    print_msg("")
    
    install_dependencies()
    print_msg("")
    
    success = build_executable()
    print_msg("")
    
    if success:
        print_msg("🎉 Готово! EXE-файл в папке dist/")
        print_msg("💡 Для веб-версии: запустите EXE и откройте http://localhost:8765")
    else:
        print_msg("❌ Сборка не удалась.")

if __name__ == "__main__":
    main()
