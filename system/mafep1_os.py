# MaFe P1 OS v2.2
# Исправленная версия с рабочими кнопками

import machine, time, os, gc, ubinascii
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

def sound_nav(): beep(800, 30, 16384)
def sound_select():
    beep(1200, 80, 32768)
    time.sleep_ms(30)
    beep(1600, 80, 32768)
def sound_back(): beep(600, 50, 24576)
def sound_error():
    beep(400, 150, 32768)
    time.sleep_ms(50)
    beep(300, 150, 32768)

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
        if y < 2048 - self.threshold: return 'up'
        elif y > 2048 + self.threshold: return 'down'
        elif x < 2048 - self.threshold: return 'left'
        elif x > 2048 + self.threshold: return 'right'
        return 'center'
    def btn_pressed(self, debounce_ms=200):
        now = time.ticks_ms()
        # Джойстики: LOW = нажата
        if self.btn.value() == 0 and time.ticks_diff(now, self.last_time) > debounce_ms:
            self.last_time = now
            return True
        return False

joy1 = Joystick(joy1_x, joy1_y, joy1_btn)
joy2 = Joystick(joy2_x, joy2_y, joy2_btn)

# === КНОПКИ (11 штук) - ИСПРАВЛЕНО: HIGH = нажата ===
try:
    from mafep1_control import Control
    control = Control()
    HAS_BUTTONS = True
except:
    HAS_BUTTONS = False

BLACK, DARK_BLUE, MEDIUM_BLUE = 0x0000, 0x0011, 0x0022
CYAN, GREEN, WHITE, RED, YELLOW, BLUE = 0x07FF, 0x07E0, 0xFFFF, 0xF800, 0xFFE0, 0x001F

def clear(): display.fill(BLACK)
def text(msg, x, y, color=WHITE, font=font16): display.text(font, msg, x, y, color)

def draw_status_bar(title):
    display.fill_rect(0, 0, 240, 25, MEDIUM_BLUE)
    text(title, 5, 5, WHITE, font8)

def draw_hints():
    display.fill_rect(0, 215, 240, 25, MEDIUM_BLUE)
    text("Joy1/UP-DOWN:Nav", 5, 220, WHITE, font8)
    text("A:OK", 110, 220, GREEN, font8)
    text("B:Back", 140, 220, RED, font8)

def draw_wrapped_text(msg, x, y, color=WHITE, font=font8):
    max_chars = 26
    lines = [msg[i:i+max_chars] for i in range(0, len(msg), max_chars)]
    for line in lines:
        text(line, x, y, color, font)
        y += 12
        if y > 200: break

def mount_sd():
    try:
        import sdcard
        sd_spi = machine.SoftSPI(baudrate=1000000, polarity=0, phase=0,
                                 sck=machine.Pin(14), mosi=machine.Pin(17), miso=machine.Pin(18))
        sd = sdcard.SDCard(sd_spi, machine.Pin(16))
        os.mount(sd, '/sd')
        return True
    except OSError as e:
        if "EPERM" in str(e): return True
        return False
    except: return False

def get_files(folder):
    try:
        files = [f for f in os.listdir(folder) if f.endswith('.py')]
        files.sort()
        return files
    except: return []

def launch_file(path):
    clear()
    draw_status_bar("Loading...")
    text("Loading:", 10, 80, WHITE, font16)
    name = path.split('/')[-1].replace('.py', '')
    text(name[:15], 10, 110, CYAN, font16)
    try:
        with open(path, 'r') as f: code = f.read()
        text("OK!", 10, 140, GREEN, font16)
        time.sleep_ms(500)
        gc.collect()
        exec(code, {'__name__': '__main__'})
    except Exception as e:
        sound_error()
        clear()
        draw_status_bar("Error!")
        text("Failed:", 10, 40, RED, font16)
        text(name[:15], 10, 60, WHITE, font16)
        draw_wrapped_text(str(e), 10, 90, YELLOW, font8)
        text("B: Back", 10, 210, WHITE, font8)
        while True:
            if joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
                sound_back()
                return
            time.sleep_ms(16)

# === КЛАВИАТУРА ===
def keyboard_input(title="Enter text", default=""):
    layouts_lower = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
    layouts_upper = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
    layouts_numbers = "1234567890"
    layouts_symbols = "/._-:;!?()[]"
    special_keys = ["SPACE", "BACK", "SHIFT", "OK", "CANCEL"]
    
    text_result = default
    row, col, special_idx, mode = 0, 0, 0, 0
    shift_active, cursor_pos = False, 0
    
    def get_current_layouts():
        if mode == 0: return layouts_lower
        elif mode == 1: return layouts_upper
        return None

    needs_redraw = True
    while True:
        if needs_redraw:
            clear()
            draw_status_bar(title)
            display.fill_rect(10, 35, 220, 30, MEDIUM_BLUE)
            display.rect(10, 35, 220, 30, CYAN)
            
            display_text = text_result
            if len(display_text) > 18:
                if cursor_pos < 9: display_text = display_text[:18]
                elif cursor_pos > len(display_text) - 9: display_text = display_text[-18:]
                else: display_text = display_text[cursor_pos-9:cursor_pos+9]
            text(display_text, 15, 42, WHITE, font16)
            
            mode_names = ["abc", "ABC", "123", "#+=", "KEYS"]
            text(mode_names[mode] if mode < 4 else "", 180, 5, YELLOW, font8)
            if shift_active: text("SHIFT", 200, 5, GREEN, font8)
            
            current_layouts = get_current_layouts()
            if current_layouts:
                key_y = 72
                for r in range(3):
                    layout = current_layouts[r]
                    key_x = 5
                    for c, char in enumerate(layout):
                        w, h = 22, 20
                        if r == row and c == col:
                            display.fill_rect(key_x, key_y, w, h, CYAN)
                            text(char, key_x + 6, key_y + 3, BLACK, font8)
                        else:
                            display.fill_rect(key_x, key_y, w, h, DARK_BLUE)
                            text(char, key_x + 6, key_y + 3, WHITE, font8)
                        display.rect(key_x, key_y, w, h, CYAN)
                        key_x += w + 2
                    key_y += 22
            else:
                layout = layouts_numbers if mode == 2 else layouts_symbols
                key_y, key_x = 72, 5
                for c, char in enumerate(layout):
                    w, h = 22, 20
                    if c == col:
                        display.fill_rect(key_x, key_y, w, h, CYAN)
                        text(char, key_x + 6, key_y + 3, BLACK, font8)
                    else:
                        display.fill_rect(key_x, key_y, w, h, DARK_BLUE)
                        text(char, key_x + 6, key_y + 3, WHITE, font8)
                    display.rect(key_x, key_y, w, h, CYAN)
                    key_x += w + 2
            
            key_y, key_x = 175, 5
            for i, key in enumerate(special_keys):
                w, h = 44, 20
                if mode == 4 and i == special_idx:
                    display.fill_rect(key_x, key_y, w, h, CYAN)
                    text(key, key_x + 3, key_y + 3, BLACK, font8)
                else:
                    display.fill_rect(key_x, key_y, w, h, DARK_BLUE)
                    text(key, key_x + 3, key_y + 3, WHITE, font8)
                display.rect(key_x, key_y, w, h, CYAN)
                key_x += w + 2
            
            draw_hints()
            needs_redraw = False

        direction = joy1.read()
        if direction == 'up':
            if mode == 4: mode, col = 3, 0
            elif mode == 3: mode, col = 2, 0
            elif mode == 2: mode, col = (1 if shift_active else 0), min(col, 9)
            elif mode == 1 and row > 0: row -= 1; col = min(col, len(layouts_upper[row]) - 1)
            elif mode == 0 and row > 0: row -= 1; col = min(col, len(layouts_lower[row]) - 1)
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif direction == 'down':
            if mode == 0 and row < 2: row += 1; col = min(col, len(layouts_lower[row]) - 1)
            elif mode == 1 and row < 2: row += 1; col = min(col, len(layouts_upper[row]) - 1)
            elif mode in (0, 1) and row == 2: mode, col = 2, 0
            elif mode == 2: mode, col = 3, 0
            elif mode == 3: mode, special_idx = 4, 0
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif direction == 'left':
            if mode < 2:
                if col > 0: col -= 1
            elif mode in (2, 3):
                if col > 0: col -= 1
            elif mode == 4:
                if special_idx > 0: special_idx -= 1
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif direction == 'right':
            if mode == 0:
                if col < len(layouts_lower[row]) - 1: col += 1
            elif mode == 1:
                if col < len(layouts_upper[row]) - 1: col += 1
            elif mode == 2:
                if col < len(layouts_numbers) - 1: col += 1
            elif mode == 3:
                if col < len(layouts_symbols) - 1: col += 1
            elif mode == 4:
                if special_idx < len(special_keys) - 1: special_idx += 1
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif joy1.btn_pressed() or (HAS_BUTTONS and control.btn_a()):
            if mode == 4:
                key = special_keys[special_idx]
                if key == "SPACE": text_result += " "; cursor_pos = len(text_result)
                elif key == "BACK": text_result = text_result[:-1]; cursor_pos = max(0, cursor_pos - 1)
                elif key == "SHIFT": shift_active = not shift_active; mode = 1 if shift_active else 0; row = 0
                elif key == "OK": sound_select(); return text_result
                elif key == "CANCEL": sound_back(); return default
                sound_select()
            else:
                if mode == 0: char = layouts_lower[row][col]
                elif mode == 1: char = layouts_upper[row][col]
                elif mode == 2: char = layouts_numbers[col]
                elif mode == 3: char = layouts_symbols[col]
                text_result += char
                cursor_pos = len(text_result)
                sound_select()
                if shift_active and mode == 1: shift_active = False; mode = 0
            needs_redraw = True
        elif joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
            sound_back(); return default
        time.sleep_ms(10)

# === FIREBASE ===
FIREBASE_URL = "https://mafep1-saves-default-rtdb.europe-west1.firebasedatabase.app"
FIREBASE_USER_FILE = '/sd/system/firebase_user.txt'
SAVES_DIR = '/sd/saves'

def get_firebase_user():
    try:
        mount_sd()
        with open(FIREBASE_USER_FILE, 'r') as f:
            lines = f.read().strip().split('\n')
            if len(lines) >= 2: return lines[0].strip(), lines[1].strip()
    except: pass
    return None, None

def save_firebase_user(user_id, password):
    try:
        mount_sd()
        try: os.mkdir('/sd/system')
        except OSError: pass
        with open(FIREBASE_USER_FILE, 'w') as f: f.write(user_id + '\n' + password)
        return True
    except: return False

def setup_firebase_account():
    clear()
    draw_status_bar("Firebase Account")
    text("User ID:", 10, 60, WHITE, font16)
    user_id = keyboard_input("User ID")
    if not user_id: return
    
    clear()
    draw_status_bar("Firebase Account")
    text("User: " + user_id[:15], 10, 60, CYAN, font16)
    text("Password:", 10, 100, WHITE, font16)
    password = keyboard_input("Password")
    if not password: return
    
    if len(password) < 4:
        clear(); draw_status_bar("Error")
        text("Too short!", 10, 100, RED, font16)
        time.sleep_ms(2000); return
    
    if save_firebase_user(user_id, password):
        sound_select(); clear(); draw_status_bar("Success!")
        text("Created!", 10, 100, GREEN, font16)
        time.sleep_ms(2000)
    else:
        sound_error(); clear(); draw_status_bar("Error")
        text("Failed!", 10, 100, RED, font16)
        time.sleep_ms(2000)

def get_save_games():
    try:
        mount_sd()
        items = os.listdir(SAVES_DIR)
        games = [item for item in items if os.listdir(SAVES_DIR + '/' + item)]
        games.sort()
        return games
    except: return []

def get_save_slots(game_name):
    try:
        game_dir = SAVES_DIR + '/' + game_name
        files = [f for f in os.listdir(game_dir) if f.endswith('.dat') or f.endswith('.txt')]
        files.sort()
        return files
    except: return []

def connect_wifi():
    ssid, password = load_wifi_config()
    if not ssid: ssid, password = "MaximusFed2WiFi", "57256062"
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    for i in range(20):
        if wlan.isconnected(): break
        time.sleep_ms(500)
    return wlan

def firebase_upload_save(game_name, slot_name):
    user_id, password = get_firebase_user()
    if not user_id or not password:
        clear(); draw_status_bar("Error"); text("No account!", 10, 80, RED, font16); time.sleep_ms(2000); return
    
    wlan = connect_wifi()
    clear(); draw_status_bar("Uploading...")
    if not wlan.isconnected():
        sound_error(); text("WiFi failed!", 10, 100, RED, font16); time.sleep_ms(2000); wlan.active(False); return
    
    filepath = SAVES_DIR + '/' + game_name + '/' + slot_name
    try:
        with open(filepath, 'rb') as f: save_data = f.read()
    except:
        sound_error(); text("File not found!", 10, 100, RED, font16); time.sleep_ms(2000); wlan.active(False); return
    
    try:
        import urequests
        url = FIREBASE_URL + "/saves/" + user_id + "/" + game_name + "/" + slot_name + ".json"
        response = urequests.get(url)
        
        if response.status_code == 200:
            existing = response.json()
            if existing and 'password' in existing and existing['password'] != password:
                sound_error(); clear(); draw_status_bar("Access Denied!")
                text("User ID taken!", 10, 100, RED, font16); time.sleep_ms(2000)
                response.close(); wlan.disconnect(); wlan.active(False); return
        response.close()
        
        encoded = ubinascii.b2a_base64(save_data).decode('utf-8').strip()
        data = '{"password":"' + password + '","data":"' + encoded + '","ts":' + str(time.time()) + '}'
        response = urequests.put(url, data=data)
        
        sound_select() if response.status_code == 200 else sound_error()
        clear(); draw_status_bar("Result")
        text("Uploaded!" if response.status_code == 200 else "Error!", 10, 100, GREEN if response.status_code == 200 else RED, font16)
        time.sleep_ms(2000)
        response.close()
    except Exception as e:
        sound_error(); clear(); draw_status_bar("Error"); draw_wrapped_text(str(e), 10, 100, RED, font8); time.sleep_ms(2000)
    wlan.disconnect(); wlan.active(False)

def firebase_download_save(game_name, slot_name):
    user_id, password = get_firebase_user()
    if not user_id or not password:
        clear(); draw_status_bar("Error"); text("No account!", 10, 80, RED, font16); time.sleep_ms(2000); return
    
    wlan = connect_wifi()
    clear(); draw_status_bar("Downloading...")
    if not wlan.isconnected():
        sound_error(); text("WiFi failed!", 10, 100, RED, font16); time.sleep_ms(2000); wlan.active(False); return
    
    try:
        import urequests
        url = FIREBASE_URL + "/saves/" + user_id + "/" + game_name + "/" + slot_name + ".json"
        response = urequests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            if data and 'password' in data and data['password'] != password:
                sound_error(); clear(); draw_status_bar("Access Denied!")
                text("Wrong pass!", 10, 100, RED, font16); time.sleep_ms(2000)
                response.close(); wlan.disconnect(); wlan.active(False); return
            
            if data and 'data' in data:
                save_data = ubinascii.a2b_base64(data['data'])
                try: os.mkdir(SAVES_DIR + '/' + game_name)
                except: pass
                with open(SAVES_DIR + '/' + game_name + '/' + slot_name, 'wb') as f: f.write(save_data)
                sound_select(); clear(); draw_status_bar("Success!")
                text("Downloaded!", 10, 100, GREEN, font16); time.sleep_ms(2000)
            else:
                sound_error(); clear(); draw_status_bar("No Save"); text("Not found", 10, 100, YELLOW, font16); time.sleep_ms(2000)
        else:
            sound_error(); clear(); draw_status_bar("Error"); text("HTTP " + str(response.status_code), 10, 100, RED, font16); time.sleep_ms(2000)
        response.close()
    except Exception as e:
        sound_error(); clear(); draw_status_bar("Error"); draw_wrapped_text(str(e), 10, 100, RED, font8); time.sleep_ms(2000)
    wlan.disconnect(); wlan.active(False)

def firebase_select_slot(game_name, action):
    slots = get_save_slots(game_name)
    if not slots:
        clear(); draw_status_bar("No Saves"); text("No slots for", 10, 80, YELLOW, font16); text(game_name[:15], 10, 100, WHITE, font8); time.sleep_ms(2000); return
    
    selected, scroll_offset, visible, needs_redraw = 0, 0, 5, True
    
    while True:
        if needs_redraw:
            clear(); draw_status_bar("Select Slot"); text(game_name[:15], 10, 35, CYAN, font16)
            start_idx, end_idx = scroll_offset, min(len(slots), scroll_offset + visible)
            for i in range(start_idx, end_idx):
                y = 60 + (i - start_idx) * 30
                name_color = CYAN if i == selected else WHITE
                if i == selected: display.fill_rect(5, y-5, 230, 26, MEDIUM_BLUE); display.rect(5, y-5, 230, 26, CYAN)
                text(slots[i][:18], 10, y+5, name_color, font16)
            draw_hints(); needs_redraw = False

        direction = joy1.read()
        if direction == 'up' and selected > 0:
            selected -= 1
            if selected < scroll_offset: scroll_offset = selected
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif direction == 'down' and selected < len(slots) - 1:
            selected += 1
            if selected >= scroll_offset + visible: scroll_offset = selected - visible + 1
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif joy1.btn_pressed() or (HAS_BUTTONS and control.btn_a()):
            sound_select()
            if action == 'upload': firebase_upload_save(game_name, slots[selected])
            elif action == 'download': firebase_download_save(game_name, slots[selected])
            return
        elif joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
            sound_back(); return
        time.sleep_ms(10)

def firebase_select_game(action):
    games = get_save_games()
    if not games:
        clear(); draw_status_bar("No Games"); text("No saves in", 10, 80, YELLOW, font16); text("/sd/saves/", 10, 100, WHITE, font8); time.sleep_ms(2000); return
    
    selected, scroll_offset, visible, needs_redraw = 0, 0, 5, True
    
    while True:
        if needs_redraw:
            clear(); draw_status_bar("Select Game")
            start_idx, end_idx = scroll_offset, min(len(games), scroll_offset + visible)
            for i in range(start_idx, end_idx):
                y = 50 + (i - start_idx) * 30
                name_color = CYAN if i == selected else WHITE
                if i == selected: display.fill_rect(5, y-5, 230, 26, MEDIUM_BLUE); display.rect(5, y-5, 230, 26, CYAN)
                text(games[i][:18], 10, y+5, name_color, font16)
            draw_hints(); needs_redraw = False

        direction = joy1.read()
        if direction == 'up' and selected > 0:
            selected -= 1
            if selected < scroll_offset: scroll_offset = selected
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif direction == 'down' and selected < len(games) - 1:
            selected += 1
            if selected >= scroll_offset + visible: scroll_offset = selected - visible + 1
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif joy1.btn_pressed() or (HAS_BUTTONS and control.btn_a()):
            sound_select(); firebase_select_slot(games[selected], action)
        elif joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
            sound_back(); return
        time.sleep_ms(10)

def firebase_account_info():
    user_id, password = get_firebase_user()
    clear(); draw_status_bar("Account Info")
    if user_id:
        text("User ID:", 10, 60, WHITE, font16); text(user_id[:20], 10, 90, CYAN, font16)
        text("Password:", 10, 125, WHITE, font16); text("*" * len(password), 10, 155, GREEN, font16)
    else: text("No account", 10, 100, RED, font16)
    text("B: Back", 10, 210, WHITE, font8)
    while True:
        if joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
            sound_back(); return
        time.sleep_ms(16)

def firebase_menu():
    menu_items = [("Upload Save", GREEN), ("Download Save", CYAN), ("Account Info", YELLOW), ("Change Account", WHITE)]
    selected, needs_redraw = 0, True
    
    while True:
        if needs_redraw:
            clear(); draw_status_bar("Firebase Sync")
            user_id, _ = get_firebase_user()
            text("User: " + (user_id[:12] if user_id else "None"), 10, 40, GREEN if user_id else RED, font8)
            for i, (name, color) in enumerate(menu_items):
                y = 60 + i * 30
                if i == selected: display.fill_rect(5, y-5, 230, 28, MEDIUM_BLUE); display.rect(5, y-5, 230, 28, color); text(name, 10, y+5, color, font16)
                else: text(name, 10, y+5, WHITE, font16)
            draw_hints(); needs_redraw = False

        direction = joy1.read()
        if direction == 'up' and selected > 0: selected -= 1; sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif direction == 'down' and selected < len(menu_items) - 1: selected += 1; sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif joy1.btn_pressed() or (HAS_BUTTONS and control.btn_a()):
            sound_select()
            if selected == 0: firebase_select_game('upload')
            elif selected == 1: firebase_select_game('download')
            elif selected == 2: firebase_account_info()
            elif selected == 3:
                clear(); draw_status_bar("Change?"); text("Erase current", 10, 80, YELLOW, font16); text("account?", 10, 100, YELLOW, font16)
                text("A: Yes", 10, 140, GREEN, font8); text("B: No", 10, 160, RED, font8)
                confirm = False
                while True:
                    if joy1.btn_pressed() or (HAS_BUTTONS and control.btn_a()):
                        confirm = True; sound_select(); break
                    elif joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
                        sound_back(); break
                    time.sleep_ms(16)
                if confirm: setup_firebase_account()
            needs_redraw = True
        elif joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
            sound_back(); return
        time.sleep_ms(10)

# === GITHUB CATALOG ===
CATALOG_URL = "https://cdn.jsdelivr.net/gh/MaximusFed2/mafep1-os@main/catalog.txt"

def load_catalog():
    ssid, password = load_wifi_config()
    if not ssid: ssid, password = "MaximusFed2WiFi", "57256062"
    wlan = network.WLAN(network.STA_IF); wlan.active(True); wlan.connect(ssid, password)
    clear(); draw_status_bar("Loading Catalog"); text("Connecting...", 10, 80, YELLOW, font16)
    for i in range(20):
        if wlan.isconnected(): break
        time.sleep_ms(500)
    if not wlan.isconnected():
        sound_error(); text("WiFi failed!", 10, 120, RED, font16); time.sleep_ms(2000); wlan.active(False); return None
    try:
        import urequests
        text("Downloading...", 10, 150, CYAN, font16)
        response = urequests.get(CATALOG_URL)
        if response.status_code == 200:
            catalog_text = response.text; response.close(); wlan.disconnect(); wlan.active(False)
            games = []
            for line in catalog_text.split('\n'):
                line = line.strip()
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 2: games.append((parts[0].strip(), parts[1].strip(), parts[2].strip() if len(parts) > 2 else "1.0"))
            return games
        else:
            response.close(); wlan.disconnect(); wlan.active(False); sound_error(); return None
    except Exception as e:
        try: wlan.disconnect(); wlan.active(False)
        except: pass
        sound_error(); return None

def download_game(name, url):
    ssid, password = load_wifi_config()
    if not ssid: ssid, password = "MaximusFed2WiFi", "57256062"
    wlan = network.WLAN(network.STA_IF); wlan.active(True); wlan.connect(ssid, password)
    clear(); draw_status_bar("Downloading")
    if not wlan.isconnected():
        sound_error(); text("WiFi failed!", 10, 100, RED, font16); time.sleep_ms(2000); wlan.active(False); return False
    try:
        import urequests
        text(name[:18], 10, 80, WHITE, font16)
        response = urequests.get(url)
        if response.status_code == 200:
            filepath = "/sd/downloads/" + name + ".py"
            try: os.mkdir("/sd/downloads")
            except: pass
            with open(filepath, 'wb') as f: f.write(response.content)
            response.close(); wlan.disconnect(); wlan.active(False)
            sound_select(); clear(); draw_status_bar("Success!"); text("Downloaded!", 10, 100, GREEN, font16); time.sleep_ms(2000); return True
        else:
            response.close(); wlan.disconnect(); wlan.active(False)
            sound_error(); clear(); draw_status_bar("Error"); text("HTTP " + str(response.status_code), 10, 100, RED, font16); time.sleep_ms(2000); return False
    except Exception as e:
        try: wlan.disconnect(); wlan.active(False)
        except: pass
        sound_error(); clear(); draw_status_bar("Error"); draw_wrapped_text(str(e), 10, 100, RED, font8); time.sleep_ms(2000); return False

def github_catalog():
    clear(); draw_status_bar("GitHub Catalog"); text("Loading...", 10, 100, YELLOW, font16)
    games = load_catalog()
    if games is None or not games:
        sound_error(); text("Failed/Empty", 10, 100, RED, font16); text("B: Back", 10, 160, WHITE, font8)
        while True:
            if joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
                sound_back(); return
            time.sleep_ms(16)
        return
    
    selected, scroll_offset, visible, needs_redraw = 0, 0, 5, True
    
    while True:
        if needs_redraw:
            clear(); draw_status_bar("GitHub Catalog")
            start_idx, end_idx = scroll_offset, min(len(games), scroll_offset + visible)
            for i in range(start_idx, end_idx):
                y = 40 + (i - start_idx) * 35
                name, url, version = games[i]
                name_color = CYAN if i == selected else WHITE
                if i == selected: display.fill_rect(5, y-5, 230, 30, MEDIUM_BLUE); display.rect(5, y-5, 230, 30, CYAN)
                text(name[:16], 10, y+5, name_color, font16); text("v" + version, 180, y+10, GREEN, font8)
            draw_hints(); needs_redraw = False

        direction = joy1.read()
        if direction == 'up' and selected > 0:
            selected -= 1
            if selected < scroll_offset: scroll_offset = selected
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif direction == 'down' and selected < len(games) - 1:
            selected += 1
            if selected >= scroll_offset + visible: scroll_offset = selected - visible + 1
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif joy1.btn_pressed() or (HAS_BUTTONS and control.btn_a()):
            name, url, version = games[selected]
            sound_select()
            clear(); draw_status_bar("Download?"); text(name[:18], 10, 80, CYAN, font16); text("v" + version, 10, 110, GREEN, font8)
            text("A: Yes", 10, 160, GREEN, font8); text("B: No", 10, 180, RED, font8)
            confirm = False
            while True:
                if joy1.btn_pressed() or (HAS_BUTTONS and control.btn_a()):
                    confirm = True; sound_select(); break
                elif joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
                    sound_back(); break
                time.sleep_ms(16)
            if confirm: download_game(name, url)
            needs_redraw = True
        elif joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
            sound_back(); return
        time.sleep_ms(10)

# === WIFI SETTINGS ===
def load_wifi_config():
    try:
        mount_sd()
        with open('/sd/system/wifi_config.txt', 'r') as f:
            lines = f.read().split('\n')
            if len(lines) >= 2: return lines[0].strip(), lines[1].strip()
    except: pass
    return None, None

def save_wifi_config(ssid, password):
    try:
        mount_sd()
        try: os.mkdir('/sd/system')
        except OSError: pass
        with open('/sd/system/wifi_config.txt', 'w') as f: f.write(ssid + '\n' + password)
        return True
    except: return False

def wifi_scanner():
    clear(); draw_status_bar("WiFi Scanner"); text("Scanning...", 10, 100, YELLOW, font16)
    wlan = network.WLAN(network.STA_IF); wlan.active(True); time.sleep_ms(1000)
    networks = wlan.scan()
    if not networks:
        sound_error(); text("No networks!", 10, 100, RED, font16); time.sleep_ms(2000); wlan.active(False); return None, None
    networks.sort(key=lambda x: x[3], reverse=True)
    
    selected, scroll_offset, visible, needs_redraw = 0, 0, 5, True
    
    while True:
        if needs_redraw:
            clear(); draw_status_bar("Select WiFi")
            start_idx, end_idx = scroll_offset, min(len(networks), scroll_offset + visible)
            for i in range(start_idx, end_idx):
                y = 40 + (i - start_idx) * 35
                ssid = networks[i][0].decode('utf-8', 'ignore')
                rssi, auth = networks[i][3], networks[i][4]
                name_color = CYAN if i == selected else WHITE
                if i == selected: display.rect(5, y-3, 230, 26, CYAN)
                text(ssid[:14], 10, y+2, name_color, font16); text(("*" if auth > 0 else " ") + str(rssi), 180, y+5, GREEN, font8)
            draw_hints(); needs_redraw = False

        direction = joy1.read()
        if direction == 'up' and selected > 0:
            selected -= 1
            if selected < scroll_offset: scroll_offset = selected
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif direction == 'down' and selected < len(networks) - 1:
            selected += 1
            if selected >= scroll_offset + visible: scroll_offset = selected - visible + 1
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif joy1.btn_pressed() or (HAS_BUTTONS and control.btn_a()):
            ssid = networks[selected][0].decode('utf-8', 'ignore')
            auth = networks[selected][4]
            sound_select(); wlan.active(False)
            if auth > 0:
                password = keyboard_input("Pass: " + ssid[:10])
                return ssid, password
            else: return ssid, ""
        elif joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
            sound_back(); wlan.active(False); return None, None
        time.sleep_ms(10)

def wifi_settings():
    menu_items = [("Scan & Connect", GREEN), ("Saved Networks", CYAN), ("WebREPL Info", YELLOW), ("FTP Info", BLUE), ("Disconnect", RED)]
    selected, needs_redraw = 0, True
    
    while True:
        if needs_redraw:
            clear(); draw_status_bar("WiFi Settings")
            for i, (name, color) in enumerate(menu_items):
                y = 50 + i * 30
                if i == selected: display.fill_rect(5, y-5, 230, 28, MEDIUM_BLUE); display.rect(5, y-5, 230, 28, color); text(name, 10, y+5, color, font16)
                else: text(name, 10, y+5, WHITE, font16)
            draw_hints(); needs_redraw = False

        direction = joy1.read()
        if direction == 'up' and selected > 0: selected -= 1; sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif direction == 'down' and selected < len(menu_items) - 1: selected += 1; sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif joy1.btn_pressed() or (HAS_BUTTONS and control.btn_a()):
            sound_select()
            if selected == 0:
                ssid, password = wifi_scanner()
                if ssid:
                    clear(); draw_status_bar("Connecting..."); text("To: " + ssid[:16], 10, 80, WHITE, font16)
                    wlan = network.WLAN(network.STA_IF); wlan.active(True); wlan.connect(ssid, password)
                    for i in range(20):
                        if wlan.isconnected(): break
                        text(".", 10 + i*10, 120, GREEN, font8); time.sleep_ms(500)
                    if wlan.isconnected():
                        sound_select(); text("Connected!", 10, 150, GREEN, font16); text("IP: " + wlan.ifconfig()[0], 10, 180, WHITE, font8)
                        save_wifi_config(ssid, password); time.sleep_ms(2500)
                    else:
                        sound_error(); text("Failed!", 10, 150, RED, font16); time.sleep_ms(2000)
                    wlan.active(False); needs_redraw = True
            elif selected == 1:
                clear(); draw_status_bar("Saved Networks")
                ssid, password = load_wifi_config()
                if ssid: text("Saved:", 10, 80, GREEN, font16); text(ssid[:18], 10, 110, WHITE, font16); text("Pass: " + ("*" * len(password)), 10, 140, YELLOW, font8)
                else: text("No saved", 10, 100, YELLOW, font16)
                text("B: Back", 10, 180, WHITE, font8)
                while True:
                    if joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
                        sound_back(); break
                    time.sleep_ms(16)
            elif selected == 2:
                clear(); draw_status_bar("WebREPL")
                text("1. webrepl_setup", 10, 60, YELLOW, font8); text("2. micropython.org", 10, 80, CYAN, font8)
                text("/webrepl", 10, 95, CYAN, font8)
                ip = "192.168.4.1"
                try:
                    wlan = network.WLAN(network.STA_IF)
                    if wlan.isconnected(): ip = wlan.ifconfig()[0]
                except: pass
                text("ws://" + ip + ":8266/", 10, 125, GREEN, font8); text("B: Back", 10, 200, WHITE, font8)
                while True:
                    if joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
                        sound_back(); break
                    time.sleep_ms(16)
            elif selected == 3:
                clear(); draw_status_bar("FTP Info")
                text("Use standalone:", 10, 80, YELLOW, font8)
                text("/sd/apps/ftp_server.py", 10, 100, WHITE, font8)
                text("It creates its own", 10, 130, YELLOW, font8)
                text("WiFi AP for PC/Phone", 10, 145, YELLOW, font8)
                text("B: Back", 10, 200, WHITE, font8)
                while True:
                    if joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
                        sound_back(); break
                    time.sleep_ms(16)
            elif selected == 4:
                wlan = network.WLAN(network.STA_IF); wlan.disconnect(); wlan.active(False)
                sound_select(); clear(); draw_status_bar("Disconnected"); text("WiFi disabled", 10, 100, YELLOW, font16); time.sleep_ms(1500)
                needs_redraw = True
        elif joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
            sound_back(); return
        time.sleep_ms(10)

# === APPS MENU ===
def apps_menu():
    mount_sd()
    games = get_files('/sd/games')
    apps = get_files('/sd/apps')
    downloads = get_files('/sd/downloads')
    items = []
    for g in games: items.append(('game', g.replace('.py', ''), '/sd/games/' + g))
    for a in apps: items.append(('app', a.replace('.py', ''), '/sd/apps/' + a))
    for d in downloads: items.append(('down', d.replace('.py', ''), '/sd/downloads/' + d))
    
    if not items:
        clear(); draw_status_bar("Apps"); text("No apps found!", 10, 80, YELLOW, font16)
        text("/sd/games/", 10, 110, GREEN, font8); text("/sd/apps/", 10, 130, CYAN, font8)
        text("B: Back", 10, 190, WHITE, font8)
        while True:
            if joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
                sound_back(); return
            time.sleep_ms(16)
        return
    
    selected, scroll_offset, visible, needs_redraw = 0, 0, 5, True
    
    while True:
        if needs_redraw:
            clear(); draw_status_bar("Apps Menu")
            start_idx, end_idx = scroll_offset, min(len(items), scroll_offset + visible)
            for i in range(start_idx, end_idx):
                y = 40 + (i - start_idx) * 35
                item_type, name, path = items[i]
                if item_type == 'game': icon, icon_color = "G", GREEN
                elif item_type == 'app': icon, icon_color = "A", CYAN
                else: icon, icon_color = "D", BLUE
                display.fill_rect(5, y, 20, 20, icon_color); text(icon, 9, y+2, WHITE, font8)
                name_color = CYAN if i == selected else WHITE
                if i == selected: display.rect(5, y-3, 230, 26, CYAN)
                text(name[:16], 30, y+2, name_color, font16)
            draw_hints(); needs_redraw = False

        direction = joy1.read()
        if direction == 'up' and selected > 0:
            selected -= 1
            if selected < scroll_offset: scroll_offset = selected
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif direction == 'down' and selected < len(items) - 1:
            selected += 1
            if selected >= scroll_offset + visible: scroll_offset = selected - visible + 1
            sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif joy1.btn_pressed() or (HAS_BUTTONS and control.btn_a()):
            _, _, path = items[selected]
            sound_select(); launch_file(path); mount_sd(); needs_redraw = True
        elif joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
            sound_back(); return
        time.sleep_ms(10)

# === WIFI UPDATE ===
def get_version(code):
    first_line = code.split('\n')[0].strip()
    if 'MaFe' not in first_line: return (0, 0, 0, 0)
    v_pos = first_line.find('v')
    if v_pos == -1: return (0, 0, 0, 0)
    ver_text = first_line[v_pos + 1:].strip()
    for end_char in [' ', '"', "'", '#']:
        end_pos = ver_text.find(end_char)
        if end_pos != -1: ver_text = ver_text[:end_pos]
    ver_text = ver_text.strip()
    try:
        parts = ver_text.split('.')
        while len(parts) < 4: parts.append('0')
        return (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
    except: return (0, 0, 0, 0)

def get_version_file(filepath):
    try:
        with open(filepath, 'r') as f: return get_version(f.read())
    except: return (0, 0, 0, 0)

def wifi_update():
    clear(); draw_status_bar("WiFi Update"); text("Checking...", 10, 80, WHITE, font16)
    WIFI_SSID, WIFI_PASS = load_wifi_config()
    if not WIFI_SSID: WIFI_SSID, WIFI_PASS = "MaximusFed2WiFi", "57256062"
    
    GITHUB_URL = "https://cdn.jsdelivr.net/gh/MaximusFed2/mafep1-os@main/system/mafep1_os.py"
    
    try:
        wlan = network.WLAN(network.STA_IF); wlan.active(True); wlan.connect(WIFI_SSID, WIFI_PASS)
        text("Connecting...", 10, 110, YELLOW, font16)
        for i in range(30):
            if wlan.isconnected(): break
            text("." * (i+1), 10, 130, GREEN, font8); time.sleep_ms(500)
        if not wlan.isconnected():
            sound_error(); text("No internet!", 10, 160, RED, font16); text("B: Back", 10, 200, WHITE, font8)
            wlan.active(False)
            while True:
                if joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
                    sound_back(); return
                time.sleep_ms(16)
            return
        
        sound_select(); text("Connected!", 10, 160, GREEN, font16); time.sleep_ms(1000)
        text("Downloading...", 10, 50, CYAN, font16)
        import urequests
        response = urequests.get(GITHUB_URL)
        if response.status_code == 200:
            github_code = response.text; response.close()
            github_ver = get_version(github_code)
            local_ver = get_version_file('/sd/system/mafep1_os.py')
            
            def format_ver(v):
                while len(v) > 1 and v[-1] == 0: v = v[:-1]
                return '.'.join(str(x) for x in v)
            
            text("Local: v" + format_ver(local_ver), 10, 80, WHITE, font8)
            text("GitHub: v" + format_ver(github_ver), 10, 100, CYAN, font8); time.sleep_ms(1500)
            
            if github_ver > local_ver:
                text("New version!", 10, 130, GREEN, font16); text("Updating...", 10, 150, YELLOW, font16); time.sleep_ms(1000)
                with open('/sd/system/mafep1_os_new.py', 'w') as f: f.write(github_code)
                try: os.remove('/sd/system/mafep1_os.py')
                except: pass
                os.rename('/sd/system/mafep1_os_new.py', '/sd/system/mafep1_os.py')
                text("Success!", 10, 180, GREEN, font16); text("Rebooting...", 10, 200, YELLOW, font16)
                beep(1500, 200); time.sleep_ms(1000)
                wlan.disconnect(); wlan.active(False); machine.reset()
            else:
                text("Already latest", 10, 130, YELLOW, font16); text("B: Back", 10, 160, WHITE, font8)
                wlan.disconnect(); wlan.active(False)
                while True:
                    if joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
                        sound_back(); return
                    time.sleep_ms(16)
        else:
            sound_error(); text("Download failed", 10, 130, RED, font16); response.close(); time.sleep(2)
    except Exception as e:
        sound_error(); draw_wrapped_text(str(e), 10, 130, RED, font8); text("B: Back", 10, 200, WHITE, font8)
        while True:
            if joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
                sound_back(); return
            time.sleep_ms(16)

# === ABOUT ===
def about_screen():
    clear(); draw_status_bar("About")
    text("MaFe P1 OS", 10, 50, CYAN, font16); text("Version 2.1", 10, 80, WHITE, font16)
    text("Features:", 10, 110, YELLOW, font16)
    text("- 11 button support", 10, 130, WHITE, font8)
    text("- Fixed button logic", 10, 145, WHITE, font8)
    text("- Game menu system", 10, 160, WHITE, font8)
    text("B to exit", 10, 210, YELLOW, font8)
    while True:
        if joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
            sound_back(); return
        time.sleep_ms(16)

# === GRAPHICAL MENU LAUNCHER ===
def launch_graphical_menu():
    try:
        exec(open('/sd/system/mafep1_os_menu.py').read())
    except Exception as e:
        clear(); draw_status_bar("Error")
        text("Menu error!", 10, 80, RED, font16)
        draw_wrapped_text(str(e), 10, 110, YELLOW, font8)
        text("B: Back", 10, 200, WHITE, font8)
        while True:
            if joy2.btn_pressed() or (HAS_BUTTONS and control.btn_b()):
                sound_back(); return
            time.sleep_ms(16)

# === MAIN MENU ===
def main_menu():
    mount_sd()
    
    # Импортируем кнопки напрямую
    try:
        import mafep1_control as ctrl
        HAS_BUTTONS = True
        print("✅ Кнопки загружены")
    except Exception as e:
        HAS_BUTTONS = False
        print("❌ Ошибка загрузки кнопок:", e)
    
    menu_items = [
        ("Games & Apps", apps_menu, GREEN),
        ("Graphical Menu", launch_graphical_menu, CYAN),
        ("GitHub Catalog", github_catalog, BLUE),
        ("Firebase Sync", firebase_menu, YELLOW),
        ("WiFi Update", wifi_update, RED),
        ("Settings", wifi_settings, WHITE),
    ]
    selected, needs_redraw = 0, True
    
    beep(800, 50, 192); time.sleep_ms(50); beep(1200, 80, 256)
    
    while True:
        if needs_redraw:
            clear()
            draw_status_bar("MaFe P1 OS v2.1")
            text("MaFe P1", 10, 40, CYAN, font16)
            
            start_idx = max(0, selected - 2)
            end_idx = min(len(menu_items), start_idx + 5)
            
            for i in range(start_idx, end_idx):
                y = 65 + (i - start_idx) * 32
                name, _, color = menu_items[i]
                if i == selected:
                    display.fill_rect(5, y-5, 230, 30, MEDIUM_BLUE)
                    display.rect(5, y-5, 230, 30, color)
                    text(name, 10, y+5, color, font16)
                else:
                    text(name, 10, y+5, WHITE, font16)
            draw_hints()
            needs_redraw = False
        
        # === НАВИГАЦИЯ ДЖОЙСТИКОМ ===
        direction = joy1.read()
        if direction == 'up' and selected > 0:
            selected -= 1; sound_nav(); needs_redraw = True; time.sleep_ms(150)
        elif direction == 'down' and selected < len(menu_items) - 1:
            selected += 1; sound_nav(); needs_redraw = True; time.sleep_ms(150)
        
        # === НАВИГАЦИЯ КНОПКАМИ D-PAD ===
        if HAS_BUTTONS:
            if ctrl.btn_up() and selected > 0:
                selected -= 1; sound_nav(); needs_redraw = True; time.sleep_ms(150)
            elif ctrl.btn_down() and selected < len(menu_items) - 1:
                selected += 1; sound_nav(); needs_redraw = True; time.sleep_ms(150)
        
        # === ВЫБОР (Joy1BTN или кнопка A) ===
        if joy1.btn_pressed() or (HAS_BUTTONS and ctrl.btn_a()):
            _, func, _ = menu_items[selected]
            if func:
                sound_select()
                func()
                mount_sd()
                needs_redraw = True
        
        # === НАЗАД (кнопка B) ===
        if HAS_BUTTONS and ctrl.btn_b():
            sound_back()
            clear()
            text("Exit OS?", 60, 100, YELLOW, font16)
            text("A:Yes  B:No", 60, 130, WHITE, font8)
            
            while True:
                if ctrl.btn_a():
                    machine.reset()
                elif ctrl.btn_b():
                    break
                time.sleep_ms(16)
            
            needs_redraw = True
        
        time.sleep_ms(10)

if __name__ == '__main__':
    print("MaFe P1 OS v2.1 starting...")
    main_menu()
