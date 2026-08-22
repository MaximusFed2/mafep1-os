# MaFe P1 OS v0.5
# Settings + WiFi Scanner + On-screen Keyboard

import machine, time, os, network, gc, json
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

# === МЕНЮ ПРИЛОЖЕНИЙ ===
def apps_menu():
    mount_sd()
    
    games = get_files('/sd/games')
    apps = get_files('/sd/apps')
    
    items = []
    for g in games:
        items.append(('game', g.replace('.py', ''), '/sd/games/' + g))
    for a in apps:
        items.append(('app', a.replace('.py', ''), '/sd/apps/' + a))
    
    if not items:
        clear()
        draw_status_bar("Apps")
        text("No apps found!", 50, 80, YELLOW, font16)
        text("Add .py files to:", 40, 110, WHITE, font8)
        text("/sd/games/", 60, 130, GREEN, font8)
        text("/sd/apps/", 60, 150, CYAN, font8)
        text("Joy2BTN: Back", 50, 190, WHITE, font8)
        
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
            
            icon = "G" if item_type == 'game' else "A"
            icon_color = GREEN if item_type == 'game' else CYAN
            
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

# === КЛАВИАТУРА ===
def keyboard_input(title="Enter text", default=""):
    """Экранная клавиатура"""
    layouts = [
        "qwertyuiop",
        "asdfghjkl",
        "zxcvbnm",
        "1234567890",
        "!@#$%^&*()"
    ]
    
    special_keys = ["SPACE", "BACK", "OK", "CANCEL"]
    
    text_result = default
    row = 0
    col = 0
    special_idx = 0
    in_special = False
    
    while True:
        clear()
        draw_status_bar(title)
        
        # Поле ввода
        display.fill_rect(10, 35, 220, 30, MEDIUM_BLUE)
        display.rect(10, 35, 220, 30, CYAN)
        
        display_text = text_result[-18:] if len(text_result) > 18 else text_result
        text(display_text, 15, 42, WHITE, font16)
        
        # Рисуем клавиатуру (3 строки букв)
        key_y = 80
        for r in range(3):
            layout = layouts[r]
            key_x = 5
            for c, char in enumerate(layout):
                width = 22
                height = 25
                
                if r == row and c == col and not in_special:
                    display.fill_rect(key_x, key_y, width, height, CYAN)
                    text_color = BLACK
                else:
                    display.fill_rect(key_x, key_y, width, height, DARK_BLUE)
                    text_color = WHITE
                
                display.rect(key_x, key_y, width, height, CYAN)
                text(char, key_x + 6, key_y + 5, text_color, font8)
                
                key_x += width + 2
            
            key_y += 28
        
        # Специальные клавиши
        key_y = 170
        key_x = 5
        for i, key in enumerate(special_keys):
            width = 55
            height = 25
            
            if in_special and i == special_idx:
                display.fill_rect(key_x, key_y, width, height, CYAN)
                text_color = BLACK
            else:
                display.fill_rect(key_x, key_y, width, height, DARK_BLUE)
                text_color = WHITE
            
            display.rect(key_x, key_y, width, height, CYAN)
            text(key, key_x + 5, key_y + 5, text_color, font8)
            
            key_x += width + 2
        
        draw_hints()
        
        direction = joy1.read()
        
        if direction == 'up':
            if in_special:
                in_special = False
                row = 2
                col = min(col, len(layouts[2]) - 1)
                sound_nav()
            elif row > 0:
                row -= 1
                col = min(col, len(layouts[row]) - 1)
                sound_nav()
            time.sleep_ms(150)
        
        elif direction == 'down':
            if not in_special and row < 2:
                row += 1
                col = min(col, len(layouts[row]) - 1)
                sound_nav()
            elif not in_special and row == 2:
                in_special = True
                special_idx = 0
                sound_nav()
            time.sleep_ms(150)
        
        elif direction == 'left':
            if in_special:
                if special_idx > 0:
                    special_idx -= 1
                    sound_nav()
            else:
                if col > 0:
                    col -= 1
                    sound_nav()
            time.sleep_ms(150)
        
        elif direction == 'right':
            if in_special:
                if special_idx < len(special_keys) - 1:
                    special_idx += 1
                    sound_nav()
            else:
                if col < len(layouts[row]) - 1:
                    col += 1
                    sound_nav()
            time.sleep_ms(150)
        
        elif joy1.btn_pressed():
            if in_special:
                key = special_keys[special_idx]
                if key == "SPACE":
                    text_result += " "
                    sound_select()
                elif key == "BACK":
                    text_result = text_result[:-1]
                    sound_back()
                elif key == "OK":
                    sound_select()
                    return text_result
                elif key == "CANCEL":
                    sound_back()
                    return default
            else:
                char = layouts[row][col]
                text_result += char
                sound_select()
                time.sleep_ms(100)
        
        elif joy2.btn_pressed():
            sound_back()
            return default
        
        time.sleep_ms(50)

# === СКАНЕР WiFi ===
def wifi_scanner():
    """Сканирует доступные WiFi сети"""
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

# === НАСТРОЙКИ WiFi ===
def wifi_settings():
    """Настройки WiFi подключения"""
    menu_items = [
        ("Scan & Connect", GREEN),
        ("Saved Networks", CYAN),
        ("WebREPL Info", YELLOW),
        ("Disconnect", RED),
    ]
    
    selected = 0
    
    while True:
        clear()
        draw_status_bar("WiFi Settings")
        
        text("Settings", 60, 40, CYAN, font16)
        
        for i, (name, color) in enumerate(menu_items):
            y = 80 + i * 35
            if i == selected:
                display.fill_rect(30, y-5, 180, 30, MEDIUM_BLUE)
                display.rect(30, y-5, 180, 30, color)
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
                        
                        save_wifi_config(ssid, password)
                        time.sleep_ms(2500)
                    else:
                        sound_error()
                        text("Failed!", 70, 150, RED, font16)
                        time.sleep_ms(2000)
                    
                    wlan.active(False)
            
            elif selected == 1:
                show_saved_networks()
            
            elif selected == 2:
                show_webrepl_info()
            
            elif selected == 3:
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

def save_wifi_config(ssid, password):
    try:
        with open('/sd/system/wifi_config.txt', 'w') as f:
            f.write(ssid + '\n' + password)
        print("WiFi config saved")
    except Exception as e:
        print("Save error: " + str(e))

def load_wifi_config():
    try:
        with open('/sd/system/wifi_config.txt', 'r') as f:
            lines = f.read().split('\n')
            if len(lines) >= 2:
                return lines[0], lines[1]
    except:
        pass
    return None, None

def show_saved_networks():
    clear()
    draw_status_bar("Saved Networks")
    
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

def show_webrepl_info():
    clear()
    draw_status_bar("WebREPL Info")
    text("WebREPL", 60, 50, CYAN, font16)
    text("File transfer", 50, 80, WHITE, font16)
    text("via browser:", 50, 100, WHITE, font16)
    text("", 0, 120, WHITE, font8)
    text("1. Enable in REPL:", 40, 130, YELLOW, font8)
    text("import webrepl_setup", 30, 145, WHITE, font8)
    text("2. Open on phone:", 40, 165, YELLOW, font8)
    text("micropython.org/webrepl", 20, 180, CYAN, font8)
    text("Joy2BTN: Back", 50, 210, WHITE, font8)
    
    while True:
        if joy2.btn_pressed():
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
    text("Version 0.5", 65, 80, WHITE, font16)
    text("", 0, 100, WHITE, font8)
    text("Features:", 60, 120, YELLOW, font16)
    text("- App menu", 50, 140, WHITE, font8)
    text("- Game loader", 50, 155, WHITE, font8)
    text("- WiFi updates", 50, 170, WHITE, font8)
    text("- Settings menu", 50, 185, WHITE, font8)
    text("- WiFi scanner", 50, 200, WHITE, font8)
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
        ("WiFi Update", wifi_update, CYAN),
        ("Settings", wifi_settings, YELLOW),
        ("About", about_screen, WHITE),
    ]
    
    selected = 0
    
    beep(800, 50, 192)
    time.sleep_ms(50)
    beep(1200, 80, 256)
    
    while True:
        clear()
        draw_status_bar("MaFe P1 OS v0.5")
        
        text("MaFe P1", 70, 40, CYAN, font16)
        
        for i, (name, _, color) in enumerate(menu_items):
            y = 80 + i * 35
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
print("MaFe P1 OS v0.5 starting...")
print("Controls: Joy1=Nav, Joy1BTN=OK, Joy2BTN=Back")
print("New: Settings, WiFi scanner, keyboard")
main_menu()
