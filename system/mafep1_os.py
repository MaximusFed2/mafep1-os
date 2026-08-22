# MaFe P1 OS v0.9.1
# WebREPL + FTP + BLE + Google Drive + Symbols Keyboard + Fixed WiFi Save

import machine, time, os, network, gc, json, socket, struct
import st7789, vga1_16x16 as font16, vga1_8x8 as font8

# === ДИСПЛЕЙ ===
spi = machine.SPI(2, baudrate=40000000, polarity=1, phase=1,
                  sck=machine.Pin(12), mosi=machine.Pin(11), miso=machine.Pin(13))
display = st7789.ST7789(spi, 240, 240,
                        dc=machine.Pin(4, machine.Pin.OUT),
                        reset=machine.Pin(5, machine.Pin.OUT), cs=None)

# === ДЖОЙСТИКИ ===
joy1_x = machine.ADC(machine.Pin(6))
joy1_y = machine.ADC(machine.Pin(7))
joy1_btn = machine.Pin(8, machine.Pin.IN, machine.Pin.PULL_UP)

joy2_x = machine.ADC(machine.Pin(1))
joy2_y = machine.ADC(machine.Pin(2))
joy2_btn = machine.Pin(15, machine.Pin.IN, machine.Pin.PULL_UP)

for adc in [joy1_x, joy1_y, joy2_x, joy2_y]:
    adc.atten(machine.ADC.ATTN_11DB)

# === БУЗЕР ===
buzzer = machine.PWM(machine.Pin(9))
buzzer.freq(1000)
buzzer.duty_u16(0)

def beep(freq=1000, duration=50, volume=32768):
    buzzer.freq(freq)
    buzzer.duty_u16(volume)
    time.sleep_ms(duration)
    buzzer.duty_u16(0)

def sound_nav():
    beep(800, 30, 16384)

def sound_select():
    beep(1200, 80, 32768)
    time.sleep_ms(30)
    beep(1600, 80, 32768)

def sound_back():
    beep(600, 50, 24576)

def sound_error():
    beep(400, 150, 32768)
    time.sleep_ms(50)
    beep(300, 150, 32768)

# === КЛАСС ДЖОЙСТИКА ===
class Joystick:
    def __init__(self, x_adc, y_adc, btn_pin):
        self.x = x_adc
        self.y = y_adc
        self.btn = btn_pin
        self.last_time = 0
        self.threshold = 600
    
    def read(self):
        x = self.x.read()
        y = self.y.read()
        if y < 2048 - self.threshold:
            return 'up'
        elif y > 2048 + self.threshold:
            return 'down'
        elif x < 2048 - self.threshold:
            return 'left'
        elif x > 2048 + self.threshold:
            return 'right'
        return 'center'
    
    def btn_pressed(self, debounce_ms=200):
        now = time.ticks_ms()
        if self.btn.value() == 0 and time.ticks_diff(now, self.last_time) > debounce_ms:
            self.last_time = now
            return True
        return False

joy1 = Joystick(joy1_x, joy1_y, joy1_btn)
joy2 = Joystick(joy2_x, joy2_y, joy2_btn)

# === ЦВЕТА ===
BLACK = 0x0000
DARK_BLUE = 0x0011
MEDIUM_BLUE = 0x0022
CYAN = 0x07FF
GREEN = 0x07E0
WHITE = 0xFFFF
RED = 0xF800
YELLOW = 0xFFE0
BLUE = 0x001F

# === УТИЛИТЫ ===
def clear():
    display.fill(BLACK)

def text(msg, x, y, color=WHITE, font=font16):
    display.text(font, msg, x, y, color)

def draw_status_bar(title):
    display.fill_rect(0, 0, 240, 25, MEDIUM_BLUE)
    text(title, 5, 5, WHITE, font8)

def draw_hints():
    display.fill_rect(0, 215, 240, 25, MEDIUM_BLUE)
    text("Joy1:Nav", 5, 220, WHITE, font8)
    text("Joy1BTN:OK", 70, 220, GREEN, font8)
    text("Joy2BTN:Back", 140, 220, RED, font8)

# === МОНТИРОВАНИЕ SD ===
def mount_sd():
    try:
        import sdcard
        sd_spi = machine.SoftSPI(baudrate=1000000, polarity=0, phase=0,
                                 sck=machine.Pin(14), mosi=machine.Pin(17), miso=machine.Pin(18))
        sd = sdcard.SDCard(sd_spi, machine.Pin(16))
        os.mount(sd, '/sd')
        return True
    except OSError as e:
        if "EPERM" in str(e):
            return True
        return False
    except:
        return False

def get_files(folder):
    try:
        files = [f for f in os.listdir(folder) if f.endswith('.py')]
        files.sort()
        return files
    except:
        return []

# === ЗАПУСК ФАЙЛА ===
def launch_file(path):
    clear()
    draw_status_bar("Loading...")
    text("Loading:", 60, 80, WHITE, font16)
    
    name = path.split('/')[-1].replace('.py', '')
    text(name, 70, 110, CYAN, font16)
    
    try:
        with open(path, 'r') as f:
            code = f.read()
        
        text("OK!", 100, 140, GREEN, font16)
        time.sleep_ms(500)
        
        gc.collect()
        exec(code, {'__name__': '__main__'})
        
    except Exception as e:
        sound_error()
        clear()
        draw_status_bar("Error!")
        text("Failed to run:", 40, 80, RED, font16)
        text(name, 60, 110, WHITE, font16)
        err_msg = str(e)[:20]
        text(err_msg, 50, 140, YELLOW, font8)
        text("Joy2BTN: Back", 50, 180, WHITE, font8)
        
        while True:
            if joy2.btn_pressed():
                sound_back()
                return
            time.sleep_ms(50)

# === КЛАВИАТУРА v3 (ИСПРАВЛЕННОЕ ВЫДЕЛЕНИЕ + ПРОКРУТКА) ===
def keyboard_input(title="Enter text", default=""):
    layouts_lower = [
        "qwertyuiop",
        "asdfghjkl",
        "zxcvbnm",
    ]
    layouts_upper = [
        "QWERTYUIOP",
        "ASDFGHJKL",
        "ZXCVBNM",
    ]
    layouts_numbers = "1234567890"
    layouts_symbols = "/._-:;!?()[]"
    
    special_keys = ["SPACE", "BACK", "SHIFT", "OK", "CANCEL"]
    
    text_result = default
    row = 0
    col = 0
    special_idx = 0
    mode = 0  # 0=строчные, 1=заглавные, 2=цифры, 3=символы, 4=special
    shift_active = False
    cursor_pos = 0  # Позиция курсора для прокрутки
    
    def get_current_layouts():
        if mode == 0:
            return layouts_lower
        elif mode == 1:
            return layouts_upper
        return None
    
    while True:
        clear()
        draw_status_bar(title)
        
        # Поле ввода с прокруткой
        display.fill_rect(10, 35, 220, 30, MEDIUM_BLUE)
        display.rect(10, 35, 220, 30, CYAN)
        
        # Прокрутка: показываем текст вокруг курсора
        display_text = text_result
        if len(display_text) > 18:
            if cursor_pos < 9:
                display_text = display_text[:18]
            elif cursor_pos > len(display_text) - 9:
                display_text = display_text[-18:]
            else:
                display_text = display_text[cursor_pos-9:cursor_pos+9]
        
        text(display_text, 15, 42, WHITE, font16)
        
        # Режим
        mode_names = ["abc", "ABC", "123", "#+=", "KEYS"]
        text(mode_names[mode] if mode < 4 else "", 180, 5, YELLOW, font8)
        if shift_active:
            text("SHIFT", 200, 5, GREEN, font8)
        
        current_layouts = get_current_layouts()
        
        if current_layouts:
            # Режим букв
            key_y = 72
            for r in range(3):
                layout = current_layouts[r]
                key_x = 5
                for c, char in enumerate(layout):
                    width = 22
                    height = 20
                    
                    if r == row and c == col:
                        display.fill_rect(key_x, key_y, width, height, CYAN)
                        text_color = BLACK
                    else:
                        display.fill_rect(key_x, key_y, width, height, DARK_BLUE)
                        text_color = WHITE
                    
                    display.rect(key_x, key_y, width, height, CYAN)
                    text(char, key_x + 6, key_y + 3, text_color, font8)
                    key_x += width + 2
                key_y += 22
        else:
            # Режим цифр или символов (ОДНА строка)
            layout = layouts_numbers if mode == 2 else layouts_symbols
            key_y = 72
            key_x = 5
            for c, char in enumerate(layout):
                width = 22
                height = 20
                
                # ИСПРАВЛЕНО: используем col для выделения
                if c == col:
                    display.fill_rect(key_x, key_y, width, height, CYAN)
                    text_color = BLACK
                else:
                    display.fill_rect(key_x, key_y, width, height, DARK_BLUE)
                    text_color = WHITE
                
                display.rect(key_x, key_y, width, height, CYAN)
                text(char, key_x + 6, key_y + 3, text_color, font8)
                key_x += width + 2
        
        # Специальные клавиши
        key_y = 175
        key_x = 5
        for i, key in enumerate(special_keys):
            width = 44
            height = 20
            
            if mode == 4 and i == special_idx:
                display.fill_rect(key_x, key_y, width, height, CYAN)
                text_color = BLACK
            else:
                display.fill_rect(key_x, key_y, width, height, DARK_BLUE)
                text_color = WHITE
            
            display.rect(key_x, key_y, width, height, CYAN)
            text(key, key_x + 3, key_y + 3, text_color, font8)
            key_x += width + 2
        
        draw_hints()
        
        direction = joy1.read()
        
        if direction == 'up':
            if mode == 4:
                mode = 3
                col = 0
                sound_nav()
            elif mode == 3:
                mode = 2
                col = 0
                sound_nav()
            elif mode == 2:
                mode = 1 if shift_active else 0
                col = min(col, 9)
                sound_nav()
            elif mode == 1 and row > 0:
                row -= 1
                col = min(col, len(layouts_upper[row]) - 1)
                sound_nav()
            elif mode == 0 and row > 0:
                row -= 1
                col = min(col, len(layouts_lower[row]) - 1)
                sound_nav()
            time.sleep_ms(150)
        
        elif direction == 'down':
            if mode == 0 and row < 2:
                row += 1
                col = min(col, len(layouts_lower[row]) - 1)
                sound_nav()
            elif mode == 1 and row < 2:
                row += 1
                col = min(col, len(layouts_upper[row]) - 1)
                sound_nav()
            elif mode in (0, 1) and row == 2:
                mode = 2
                col = 0
                sound_nav()
            elif mode == 2:
                mode = 3
                col = 0
                sound_nav()
            elif mode == 3:
                mode = 4
                special_idx = 0
                sound_nav()
            time.sleep_ms(150)
        
        elif direction == 'left':
            if mode < 2:
                if col > 0:
                    col -= 1
                    sound_nav()
            elif mode in (2, 3):
                if col > 0:
                    col -= 1
                    sound_nav()
            elif mode == 4:
                if special_idx > 0:
                    special_idx -= 1
                    sound_nav()
            time.sleep_ms(150)
        
        elif direction == 'right':
            if mode == 0:
                if col < len(layouts_lower[row]) - 1:
                    col += 1
                    sound_nav()
            elif mode == 1:
                if col < len(layouts_upper[row]) - 1:
                    col += 1
                    sound_nav()
            elif mode == 2:
                if col < len(layouts_numbers) - 1:
                    col += 1
                    sound_nav()
            elif mode == 3:
                if col < len(layouts_symbols) - 1:
                    col += 1
                    sound_nav()
            elif mode == 4:
                if special_idx < len(special_keys) - 1:
                    special_idx += 1
                    sound_nav()
            time.sleep_ms(150)
        
        elif joy1.btn_pressed():
            if mode == 4:
                key = special_keys[special_idx]
                if key == "SPACE":
                    text_result += " "
                    cursor_pos = len(text_result)
                    sound_select()
                elif key == "BACK":
                    text_result = text_result[:-1]
                    cursor_pos = max(0, cursor_pos - 1)
                    sound_back()
                elif key == "SHIFT":
                    shift_active = not shift_active
                    mode = 1 if shift_active else 0
                    row = 0
                    sound_select()
                elif key == "OK":
                    sound_select()
                    return text_result
                elif key == "CANCEL":
                    sound_back()
                    return default
            else:
                if mode == 0:
                    char = layouts_lower[row][col]
                elif mode == 1:
                    char = layouts_upper[row][col]
                elif mode == 2:
                    char = layouts_numbers[col]
                elif mode == 3:
                    char = layouts_symbols[col]
                
                text_result += char
                cursor_pos = len(text_result)
                sound_select()
                
                if shift_active and mode == 1:
                    shift_active = False
                    mode = 0
                
                time.sleep_ms(100)
        
        elif joy2.btn_pressed():
            sound_back()
            return default
        
        time.sleep_ms(50)

# === GITHUB GAME CATALOG ===
CATALOG_URL = "https://raw.githubusercontent.com/MaximusFed2/mafep1-os/main/catalog.txt"

def load_catalog():
    """Загружает каталог игр с GitHub"""
    ssid, password = load_wifi_config()
    if not ssid:
        ssid = "MaximusFed2WiFi"
        password = "57256062"
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    
    clear()
    draw_status_bar("Loading Catalog")
    text("Connecting...", 60, 80, YELLOW, font16)
    
    for i in range(20):
        if wlan.isconnected():
            break
        text(".", 100 + i*5, 120, GREEN, font8)
        time.sleep_ms(500)
    
    if not wlan.isconnected():
        sound_error()
        text("WiFi failed!", 60, 150, RED, font16)
        time.sleep_ms(2000)
        wlan.active(False)
        return None
    
    try:
        import urequests
        
        text("Downloading...", 50, 150, CYAN, font16)
        
        response = urequests.get(CATALOG_URL)
        
        if response.status_code == 200:
            catalog_text = response.text
            response.close()
            wlan.disconnect()
            wlan.active(False)
            
            # Парсим каталог
            games = []
            for line in catalog_text.split('\n'):
                line = line.strip()
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        url = parts[1].strip()
                        version = parts[2].strip() if len(parts) > 2 else "1.0"
                        games.append((name, url, version))
            
            return games
        else:
            response.close()
            wlan.disconnect()
            wlan.active(False)
            sound_error()
            return None
            
    except Exception as e:
        try:
            wlan.disconnect()
            wlan.active(False)
        except:
            pass
        sound_error()
        return None

def download_game(name, url):
    """Скачивает игру по URL"""
    ssid, password = load_wifi_config()
    if not ssid:
        ssid = "MaximusFed2WiFi"
        password = "57256062"
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    
    clear()
    draw_status_bar("Downloading")
    text("Connecting...", 60, 80, YELLOW, font16)
    
    for i in range(20):
        if wlan.isconnected():
            break
        time.sleep_ms(500)
    
    if not wlan.isconnected():
        sound_error()
        text("WiFi failed!", 60, 120, RED, font16)
        time.sleep_ms(2000)
        wlan.active(False)
        return False
    
    try:
        import urequests
        
        text("Downloading...", 50, 120, CYAN, font16)
        text(name[:20], 50, 140, WHITE, font8)
        
        response = urequests.get(url)
        
        if response.status_code == 200:
            # Сохраняем в /sd/downloads/
            filepath = "/sd/downloads/" + name + ".py"
            try:
                os.mkdir("/sd/downloads")
            except:
                pass
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            response.close()
            wlan.disconnect()
            wlan.active(False)
            
            sound_select()
            clear()
            draw_status_bar("Success!")
            text("Downloaded!", 60, 80, GREEN, font16)
            text(name[:20], 50, 110, WHITE, font16)
            size = os.stat(filepath)[6]
            text(str(size) + " bytes", 60, 140, CYAN, font8)
            time.sleep_ms(2000)
            return True
        else:
            response.close()
            wlan.disconnect()
            wlan.active(False)
            sound_error()
            clear()
            draw_status_bar("Error")
            text("HTTP " + str(response.status_code), 50, 100, RED, font16)
            time.sleep_ms(2000)
            return False
            
    except Exception as e:
        try:
            wlan.disconnect()
            wlan.active(False)
        except:
            pass
        sound_error()
        clear()
        draw_status_bar("Error")
        text("Error: " + str(e)[:20], 40, 100, RED, font16)
        time.sleep_ms(2000)
        return False

def github_catalog():
    """Главное меню каталога GitHub"""
    clear()
    draw_status_bar("GitHub Catalog")
    text("Loading...", 60, 100, YELLOW, font16)
    
    games = load_catalog()
    
    if games is None:
        sound_error()
        text("Failed to load", 45, 100, RED, font16)
        text("catalog!", 70, 120, RED, font16)
        text("Joy2BTN: Back", 50, 160, WHITE, font8)
        
        while True:
            if joy2.btn_pressed():
                sound_back()
                return
            time.sleep_ms(50)
        return
    
    if not games:
        text("No games found", 45, 100, YELLOW, font16)
        text("Joy2BTN: Back", 50, 160, WHITE, font8)
        
        while True:
            if joy2.btn_pressed():
                sound_back()
                return
            time.sleep_ms(50)
        return
    
    selected = 0
    
    while True:
        clear()
        draw_status_bar("GitHub Catalog (" + str(len(games)) + ")")
        
        start_idx = max(0, selected - 2)
        end_idx = min(len(games), start_idx + 5)
        
        for i in range(start_idx, end_idx):
            y = 50 + (i - start_idx) * 35
            name, url, version = games[i]
            
            name_color = WHITE
            if i == selected:
                display.fill_rect(10, y-5, 220, 30, MEDIUM_BLUE)
                display.rect(10, y-5, 220, 30, CYAN)
                name_color = CYAN
            
            display_name = name[:18] if len(name) > 18 else name
            text(display_name, 20, y+5, name_color, font16)
            text("v" + version, 180, y+10, GREEN, font8)
        
        draw_hints()
        
        direction = joy1.read()
        
        if direction == 'up' and selected > 0:
            selected -= 1
            sound_nav()
            time.sleep_ms(150)
        elif direction == 'down' and selected < len(games) - 1:
            selected += 1
            sound_nav()
            time.sleep_ms(150)
        elif joy1.btn_pressed():
            name, url, version = games[selected]
            sound_select()
            
            # Подтверждение скачивания
            clear()
            draw_status_bar("Download?")
            text("Download:", 60, 70, WHITE, font16)
            text(name[:20], 50, 100, CYAN, font16)
            text("v" + version, 90, 130, GREEN, font8)
            text("", 0, 150, WHITE, font8)
            text("Joy1BTN: Yes", 50, 170, GREEN, font8)
            text("Joy2BTN: No", 55, 190, RED, font8)
            
            confirm = False
            while True:
                if joy1.btn_pressed():
                    confirm = True
                    sound_select()
                    break
                elif joy2.btn_pressed():
                    sound_back()
                    break
                time.sleep_ms(50)
            
            if confirm:
                download_game(name, url)
        
        elif joy2.btn_pressed():
            sound_back()
            return
        
        time.sleep_ms(50)

# === GOOGLE DRIVE С ИЗБРАННЫМИ ФАЙЛАМИ ===
def google_drive_browser():
    # Список избранных файлов (можно расширять)
    favorites = [
        ("Snake Game", "1ABC123_file_id_here"),
        ("Tetris", "1DEF456_file_id_here"),
        ("Custom File", ""),  # Пустой = ручной ввод
    ]
    
    clear()
    draw_status_bar("Google Drive")
    text("Select file:", 50, 50, WHITE, font16)
    
    selected = 0
    
    while True:
        clear()
        draw_status_bar("Google Drive")
        
        for i, (name, file_id) in enumerate(favorites):
            y = 70 + i * 35
            if i == selected:
                display.fill_rect(10, y-5, 220, 30, MEDIUM_BLUE)
                display.rect(10, y-5, 220, 30, CYAN)
                text(name, 20, y+5, CYAN, font16)
            else:
                text(name, 20, y+5, WHITE, font16)
        
        draw_hints()
        
        direction = joy1.read()
        
        if direction == 'up' and selected > 0:
            selected -= 1
            sound_nav()
            time.sleep_ms(150)
        elif direction == 'down' and selected < len(favorites) - 1:
            selected += 1
            sound_nav()
            time.sleep_ms(150)
        elif joy1.btn_pressed():
            name, file_id = favorites[selected]
            sound_select()
            
            if not file_id:
                # Ручной ввод
                file_id = keyboard_input("Enter File ID")
                if not file_id:
                    continue
            
            # Скачивание
            download_url = "https://drive.google.com/uc?export=download&id=" + file_id
            
            clear()
            draw_status_bar("Downloading...")
            text("Connecting...", 60, 80, YELLOW, font16)
            
            ssid, password = load_wifi_config()
            if not ssid:
                ssid = "MaximusFed2WiFi"
                password = "57256062"
            
            wlan = network.WLAN(network.STA_IF)
            wlan.active(True)
            wlan.connect(ssid, password)
            
            for i in range(20):
                if wlan.isconnected():
                    break
                text(".", 100 + i*5, 120, GREEN, font8)
                time.sleep_ms(500)
            
            if not wlan.isconnected():
                sound_error()
                text("WiFi failed!", 60, 150, RED, font16)
                time.sleep_ms(2000)
                wlan.active(False)
                continue
            
            try:
                import urequests
                
                text("Downloading...", 50, 150, CYAN, font16)
                
                response = urequests.get(download_url)
                
                if response.status_code == 200:
                    save_name = keyboard_input("Save as:", name + ".py")
                    if not save_name:
                        save_name = name + ".py"
                    
                    filepath = "/sd/downloads/" + save_name
                    try:
                        os.mkdir("/sd/downloads")
                    except:
                        pass
                    
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    
                    sound_select()
                    text("Saved!", 80, 180, GREEN, font16)
                    text(save_name, 50, 200, WHITE, font8)
                    time.sleep_ms(2000)
                else:
                    sound_error()
                    text("Error " + str(response.status_code), 40, 150, RED, font16)
                    time.sleep_ms(2000)
                
                response.close()
                
            except Exception as e:
                sound_error()
                text("Error: " + str(e)[:20], 40, 150, RED, font16)
                time.sleep_ms(2000)
            
            wlan.disconnect()
            wlan.active(False)
        
        elif joy2.btn_pressed():
            sound_back()
            return
        
        time.sleep_ms(50)

# === WEBREPL APP ===
def webrepl_app():
    clear()
    draw_status_bar("WebREPL")
    text("WebREPL", 70, 50, CYAN, font16)
    text("File Transfer", 50, 80, WHITE, font16)
    text("", 0, 100, WHITE, font8)
    text("1. Enable:", 40, 110, YELLOW, font8)
    text("import webrepl_setup", 30, 125, WHITE, font8)
    text("2. Open browser:", 40, 145, YELLOW, font8)
    text("micropython.org/webrepl", 20, 160, CYAN, font8)
    text("3. Connect to:", 40, 180, YELLOW, font8)
    
    ip = "192.168.4.1"
    try:
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
    except:
        pass
    
    text("ws://" + ip + ":8266/", 25, 195, GREEN, font8)
    text("Joy2BTN: Back", 50, 215, WHITE, font8)
    
    while True:
        if joy2.btn_pressed():
            sound_back()
            return
        time.sleep_ms(50)

# === FTP SERVER APP ===
def ftp_server_app():
    clear()
    draw_status_bar("FTP Server")
    text("FTP Server", 60, 50, CYAN, font16)
    text("Info", 90, 80, WHITE, font16)
    text("", 0, 100, WHITE, font8)
    text("Use FileZilla or", 45, 110, YELLOW, font8)
    text("any FTP client", 50, 125, YELLOW, font8)
    text("", 0, 140, WHITE, font8)
    text("Connect to:", 50, 150, YELLOW, font8)
    text("ftp://192.168.4.1", 45, 165, GREEN, font8)
    text("Port: 21", 75, 180, WHITE, font8)
    text("", 0, 195, WHITE, font8)
    text("Joy2BTN: Back", 50, 210, WHITE, font8)
    
    while True:
        if joy2.btn_pressed():
            sound_back()
            return
        time.sleep_ms(50)

# === BLUETOOTH SERIAL APP ===
def bluetooth_serial_app():
    clear()
    draw_status_bar("Bluetooth UART")
    text("BLE UART", 70, 50, CYAN, font16)
    text("Serial over BT", 50, 80, WHITE, font16)
    text("", 0, 100, WHITE, font8)
    text("Install app:", 50, 110, YELLOW, font8)
    text("Android: Serial BT", 35, 125, WHITE, font8)
    text("iOS: LightBlue", 50, 140, WHITE, font8)
    text("", 0, 155, WHITE, font8)
    text("Connect to:", 50, 165, YELLOW, font8)
    text("MaFeP1-BT", 60, 180, GREEN, font16)
    text("", 0, 200, WHITE, font8)
    text("Joy2BTN: Back", 50, 210, WHITE, font8)
    
    while True:
        if joy2.btn_pressed():
            sound_back()
            return
        time.sleep_ms(50)

# === СКАНЕР WiFi ===
def wifi_scanner():
    clear()
    draw_status_bar("WiFi Scanner")
    text("Scanning...", 60, 100, YELLOW, font16)
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    time.sleep_ms(1000)
    
    networks = wlan.scan()
    
    if not networks:
        sound_error()
        text("No networks!", 55, 100, RED, font16)
        text("Joy2BTN: Back", 50, 130, WHITE, font8)
        while True:
            if joy2.btn_pressed():
                sound_back()
                wlan.active(False)
                return None, None
            time.sleep_ms(50)
    
    networks.sort(key=lambda x: x[3], reverse=True)
    
    selected = 0
    
    while True:
        clear()
        draw_status_bar("Select WiFi (" + str(len(networks)) + ")")
        
        start_idx = max(0, selected - 2)
        end_idx = min(len(networks), start_idx + 5)
        
        for i in range(start_idx, end_idx):
            y = 40 + (i - start_idx) * 35
            ssid = networks[i][0].decode('utf-8', 'ignore')
            rssi = networks[i][3]
            auth = networks[i][4]
            
            display_ssid = ssid[:15] if len(ssid) > 15 else ssid
            lock_icon = "*" if auth > 0 else " "
            
            name_color = WHITE
            if i == selected:
                display.rect(5, y-3, 230, 26, CYAN)
                name_color = CYAN
            
            text(display_ssid, 10, y+2, name_color, font16)
            text(lock_icon + str(rssi), 180, y+5, GREEN, font8)
        
        draw_hints()
        
        direction = joy1.read()
        
        if direction == 'up' and selected > 0:
            selected -= 1
            sound_nav()
            time.sleep_ms(150)
        elif direction == 'down' and selected < len(networks) - 1:
            selected += 1
            sound_nav()
            time.sleep_ms(150)
        elif joy1.btn_pressed():
            ssid = networks[selected][0].decode('utf-8', 'ignore')
            auth = networks[selected][4]
            sound_select()
            wlan.active(False)
            
            if auth > 0:
                password = keyboard_input("Password: " + ssid[:12])
                return ssid, password
            else:
                return ssid, ""
        elif joy2.btn_pressed():
            sound_back()
            wlan.active(False)
            return None, None
        
        time.sleep_ms(50)

# === СОХРАНЕНИЕ/ЗАГРУЗКА WiFi ===
def save_wifi_config(ssid, password):
    try:
        mount_sd()
        try:
            os.mkdir('/sd/system')
        except OSError:
            pass
        
        with open('/sd/system/wifi_config.txt', 'w') as f:
            f.write(ssid + '\n' + password)
        
        print("WiFi config saved: " + ssid)
        return True
    except Exception as e:
        print("Save error: " + str(e))
        return False

def load_wifi_config():
    try:
        mount_sd()
        with open('/sd/system/wifi_config.txt', 'r') as f:
            lines = f.read().split('\n')
            if len(lines) >= 2:
                return lines[0].strip(), lines[1].strip()
    except:
        pass
    return None, None

# === НАСТРОЙКИ WiFi ===
def wifi_settings():
    menu_items = [
        ("Scan & Connect", GREEN),
        ("Saved Networks", CYAN),
        ("WebREPL Info", YELLOW),
        ("FTP Server", BLUE),
        ("Bluetooth", RED),
        ("Disconnect", WHITE),
    ]
    
    selected = 0
    
    while True:
        clear()
        draw_status_bar("WiFi Settings")
        
        text("Settings", 60, 40, CYAN, font16)
        
        for i, (name, color) in enumerate(menu_items):
            y = 75 + i * 30
            if i == selected:
                display.fill_rect(30, y-5, 180, 28, MEDIUM_BLUE)
                display.rect(30, y-5, 180, 28, color)
                text(name, 40, y+5, color, font16)
            else:
                text(name, 40, y+5, WHITE, font16)
        
        draw_hints()
        
        direction = joy1.read()
        
        if direction == 'up' and selected > 0:
            selected -= 1
            sound_nav()
            time.sleep_ms(150)
        elif direction == 'down' and selected < len(menu_items) - 1:
            selected += 1
            sound_nav()
            time.sleep_ms(150)
        elif joy1.btn_pressed():
            sound_select()
            
            if selected == 0:
                ssid, password = wifi_scanner()
                if ssid:
                    clear()
                    draw_status_bar("Connecting...")
                    text("To: " + ssid[:18], 40, 80, WHITE, font16)
                    
                    wlan = network.WLAN(network.STA_IF)
                    wlan.active(True)
                    wlan.connect(ssid, password)
                    
                    for i in range(20):
                        if wlan.isconnected():
                            break
                        text(".", 100 + i*5, 120, GREEN, font8)
                        time.sleep_ms(500)
                    
                    if wlan.isconnected():
                        sound_select()
                        text("Connected!", 60, 150, GREEN, font16)
                        ip = wlan.ifconfig()[0]
                        text("IP: " + ip, 50, 180, WHITE, font8)
                        
                        text("Saving...", 70, 200, YELLOW, font8)
                        if save_wifi_config(ssid, password):
                            text("Saved!", 80, 200, GREEN, font8)
                        else:
                            text("Save failed!", 60, 200, RED, font8)
                        
                        time.sleep_ms(2500)
                    else:
                        sound_error()
                        text("Failed!", 70, 150, RED, font16)
                        time.sleep_ms(2000)
                    
                    wlan.active(False)
            
            elif selected == 1:
                show_saved_networks()
            
            elif selected == 2:
                webrepl_app()
            
            elif selected == 3:
                ftp_server_app()
            
            elif selected == 4:
                bluetooth_serial_app()
            
            elif selected == 5:
                wlan = network.WLAN(network.STA_IF)
                wlan.disconnect()
                wlan.active(False)
                sound_select()
                clear()
                draw_status_bar("Disconnected")
                text("WiFi disabled", 55, 100, YELLOW, font16)
                time.sleep_ms(1500)
        
        elif joy2.btn_pressed():
            sound_back()
            return
        
        time.sleep_ms(50)

def show_saved_networks():
    clear()
    draw_status_bar("Saved Networks")
    
    mount_sd()
    
    try:
        files = os.listdir('/sd/system')
        if 'wifi_config.txt' not in files:
            text("Config file", 55, 80, RED, font16)
            text("not found!", 65, 100, RED, font16)
            text("Connect to WiFi", 45, 130, YELLOW, font8)
            text("first to save", 55, 145, YELLOW, font8)
            text("Joy2BTN: Back", 50, 180, WHITE, font8)
            
            while True:
                if joy2.btn_pressed():
                    sound_back()
                    return
                time.sleep_ms(50)
            return
    except:
        text("/sd/system/", 50, 80, RED, font16)
        text("folder missing!", 45, 100, RED, font16)
        text("Joy2BTN: Back", 50, 180, WHITE, font8)
        
        while True:
            if joy2.btn_pressed():
                sound_back()
                return
            time.sleep_ms(50)
        return
    
    ssid, password = load_wifi_config()
    
    if ssid:
        text("Saved:", 60, 80, GREEN, font16)
        text(ssid[:20], 50, 110, WHITE, font16)
        text("Pass: " + ("*" * len(password)), 50, 140, YELLOW, font8)
    else:
        text("No saved", 60, 100, YELLOW, font16)
        text("networks", 70, 120, YELLOW, font16)
    
    text("Joy2BTN: Back", 50, 180, WHITE, font8)
    
    while True:
        if joy2.btn_pressed():
            sound_back()
            return
        time.sleep_ms(50)

# === МЕНЮ ПРИЛОЖЕНИЙ (С DOWNLOADS) ===
def apps_menu():
    mount_sd()
    
    games = get_files('/sd/games')
    apps = get_files('/sd/apps')
    downloads = get_files('/sd/downloads')
    
    items = []
    for g in games:
        items.append(('game', g.replace('.py', ''), '/sd/games/' + g))
    for a in apps:
        items.append(('app', a.replace('.py', ''), '/sd/apps/' + a))
    for d in downloads:
        items.append(('down', d.replace('.py', ''), '/sd/downloads/' + d))
    
    if not items:
        clear()
        draw_status_bar("Apps")
        text("No apps found!", 50, 80, YELLOW, font16)
        text("Add .py files to:", 40, 110, WHITE, font8)
        text("/sd/games/", 60, 130, GREEN, font8)
        text("/sd/apps/", 60, 150, CYAN, font8)
        text("/sd/downloads/", 60, 170, BLUE, font8)
        text("Joy2BTN: Back", 50, 200, WHITE, font8)
        
        while True:
            if joy2.btn_pressed():
                sound_back()
                return
            time.sleep_ms(50)
        return
    
    selected = 0
    
    while True:
        clear()
        draw_status_bar("Apps Menu")
        
        start_idx = max(0, selected - 2)
        end_idx = min(len(items), start_idx + 5)
        
        for i in range(start_idx, end_idx):
            y = 40 + (i - start_idx) * 35
            item_type, name, path = items[i]
            
            if item_type == 'game':
                icon, icon_color = "G", GREEN
            elif item_type == 'app':
                icon, icon_color = "A", CYAN
            else:
                icon, icon_color = "D", BLUE
            
            display.fill_rect(10, y, 20, 20, icon_color)
            text(icon, 14, y+2, WHITE, font8)
            
            name_color = WHITE
            if i == selected:
                display.rect(5, y-3, 230, 26, CYAN)
                name_color = CYAN
            
            display_name = name[:18] if len(name) > 18 else name
            text(display_name, 35, y+2, name_color, font16)
        
        draw_hints()
        
        direction = joy1.read()
        
        if direction == 'up' and selected > 0:
            selected -= 1
            sound_nav()
            time.sleep_ms(150)
        elif direction == 'down' and selected < len(items) - 1:
            selected += 1
            sound_nav()
            time.sleep_ms(150)
        elif joy1.btn_pressed():
            _, _, path = items[selected]
            sound_select()
            launch_file(path)
            mount_sd()
        elif joy2.btn_pressed():
            sound_back()
            return
        
        time.sleep_ms(50)

# === WI-FI ОБНОВЛЕНИЕ ===
def wifi_update():
    clear()
    draw_status_bar("WiFi Update")
    text("Checking...", 60, 80, WHITE, font16)
    
    WIFI_SSID, WIFI_PASS = load_wifi_config()
    if not WIFI_SSID:
        WIFI_SSID = "MaximusFed2WiFi"
        WIFI_PASS = "57256062"
    
    GITHUB_URL = "https://raw.githubusercontent.com/MaximusFed2/mafep1-os/main/system/mafep1_os.py"
    
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.connect(WIFI_SSID, WIFI_PASS)
        
        text("Connecting...", 55, 110, YELLOW, font16)
        text("WiFi: " + WIFI_SSID[:15], 40, 130, WHITE, font8)
        for i in range(30):
            if wlan.isconnected():
                break
            text("." * (i+1), 100 + i*5, 140, GREEN, font8)
            time.sleep_ms(500)
        
        if not wlan.isconnected():
            sound_error()
            text("No internet!", 60, 170, RED, font16)
            text("Joy2BTN: Back", 50, 200, WHITE, font8)
            wlan.active(False)
            while True:
                if joy2.btn_pressed():
                    sound_back()
                    return
                time.sleep_ms(50)
            return
        
        ip = wlan.ifconfig()[0]
        sound_select()
        text("Connected!", 65, 170, GREEN, font16)
        text("IP: " + ip, 70, 190, WHITE, font8)
        time.sleep_ms(1000)
        
        text("Downloading...", 50, 50, CYAN, font16)
        import urequests
        response = urequests.get(GITHUB_URL)
        
        if response.status_code == 200:
            github_code = response.text
            response.close()
            
            github_ver = get_version(github_code)
            local_ver = get_version_file('/sd/system/mafep1_os.py')
            
            text("Local: v" + str(local_ver[0]) + "." + str(local_ver[1]), 40, 80, WHITE, font8)
            text("GitHub: v" + str(github_ver[0]) + "." + str(github_ver[1]), 40, 100, CYAN, font8)
            time.sleep_ms(1500)
            
            if github_ver > local_ver:
                text("New version!", 60, 130, GREEN, font16)
                text("Updating...", 60, 150, YELLOW, font16)
                time.sleep_ms(1000)
                
                with open('/sd/system/mafep1_os_new.py', 'w') as f:
                    f.write(github_code)
                
                try:
                    os.remove('/sd/system/mafep1_os.py')
                except:
                    pass
                
                os.rename('/sd/system/mafep1_os_new.py', '/sd/system/mafep1_os.py')
                
                text("Success!", 70, 180, GREEN, font16)
                text("Rebooting...", 60, 200, YELLOW, font16)
                beep(1500, 200)
                time.sleep_ms(1000)
                
                wlan.disconnect()
                wlan.active(False)
                machine.reset()
            else:
                text("Already latest", 50, 130, YELLOW, font16)
                text("Joy2BTN: Back", 50, 160, WHITE, font8)
                wlan.disconnect()
                wlan.active(False)
                while True:
                    if joy2.btn_pressed():
                        sound_back()
                        return
                    time.sleep_ms(50)
        else:
            sound_error()
            text("Download failed", 40, 130, RED, font16)
            response.close()
            time.sleep(2)
        
    except Exception as e:
        sound_error()
        text("Error: " + str(e)[:20], 40, 130, RED, font16)
        text("Joy2BTN: Back", 50, 160, WHITE, font8)
        while True:
            if joy2.btn_pressed():
                sound_back()
                return
            time.sleep_ms(50)

def get_version(code):
    for line in code.split('\n'):
        if 'MaFe P1 OS v' in line:
            start = line.find('v') + 1
            end = line.find(' ', start)
            if end == -1:
                end = len(line)
            ver = line[start:end].strip()
            try:
                parts = ver.split('.')
                return (int(parts[0]), int(parts[1]))
            except:
                return (0, 0)
    return (0, 0)

def get_version_file(filepath):
    try:
        with open(filepath, 'r') as f:
            return get_version(f.read())
    except:
        return (0, 0)

# === О ПРОГРАММЕ ===
def about_screen():
    clear()
    draw_status_bar("About")
    text("MaFe P1 OS", 60, 50, CYAN, font16)
    text("Version 0.6", 65, 80, WHITE, font16)
    text("", 0, 100, WHITE, font8)
    text("Features:", 60, 120, YELLOW, font16)
    text("- WebREPL support", 50, 140, WHITE, font8)
    text("- FTP Server", 50, 155, WHITE, font8)
    text("- Bluetooth UART", 50, 170, WHITE, font8)
    text("- Google Drive", 50, 185, WHITE, font8)
    text("- Symbols keyboard", 50, 200, WHITE, font8)
    text("Joy2BTN to exit", 50, 215, YELLOW, font8)
    
    while True:
        if joy2.btn_pressed():
            sound_back()
            return
        time.sleep_ms(50)

# === ГЛАВНОЕ МЕНЮ ===
def main_menu():
    mount_sd()
    
    menu_items = [
        ("Games & Apps", apps_menu, GREEN),
        ("Google Drive", google_drive_browser, CYAN),
        ("WiFi Update", wifi_update, BLUE),
        ("Settings", wifi_settings, YELLOW),
        ("About", about_screen, WHITE),
    ]
    
    selected = 0
    
    beep(800, 50, 192)
    time.sleep_ms(50)
    beep(1200, 80, 256)
    
    while True:
        clear()
        draw_status_bar("MaFe P1 OS v0.6")
        
        text("MaFe P1", 70, 40, CYAN, font16)
        
        for i, (name, _, color) in enumerate(menu_items):
            y = 75 + i * 35
            if i == selected:
                display.fill_rect(30, y-5, 180, 30, MEDIUM_BLUE)
                display.rect(30, y-5, 180, 30, color)
                text(name, 50, y+5, color, font16)
            else:
                text(name, 50, y+5, WHITE, font16)
        
        draw_hints()
        
        direction = joy1.read()
        
        if direction == 'up' and selected > 0:
            selected -= 1
            sound_nav()
            time.sleep_ms(150)
        elif direction == 'down' and selected < len(menu_items) - 1:
            selected += 1
            sound_nav()
            time.sleep_ms(150)
        elif joy1.btn_pressed():
            _, func, _ = menu_items[selected]
            if func:
                sound_select()
                func()
                mount_sd()
        
        time.sleep_ms(50)

# === ЗАПУСК ===
print("MaFe P1 OS v0.6 starting...")
print("Controls: Joy1=Nav, Joy1BTN=OK, Joy2BTN=Back")
print("New: WebREPL, FTP, BLE, Google Drive, Symbols")
main_menu()
