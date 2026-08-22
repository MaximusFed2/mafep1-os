# MaFe P1 OS v0.4
# Enhanced Version with Dual Fonts & Better WiFi

import machine
import time
import os
import network
import gc

# === ДИСПЛЕЙ ===
import st7789
import vga1_16x16 as font16
import vga1_8x8 as font8

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
buzzer = machine.PWM(machine.Pin(9), freq=1000, duty=0)

def beep(freq, duration=50, volume=256):
    buzzer.freq(freq)
    buzzer.duty(volume)
    time.sleep_ms(duration)
    buzzer.duty(0)

def sound_nav():
    beep(800, 30, 128)

def sound_select():
    beep(1200, 80, 256)
    time.sleep_ms(30)
    beep(1600, 80, 256)

def sound_back():
    beep(600, 50, 192)

def sound_error():
    beep(400, 150, 256)
    time.sleep_ms(50)
    beep(300, 150, 256)

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

# === WI-FI ОБНОВЛЕНИЕ ===
def wifi_update():
    clear()
    draw_status_bar("WiFi Update")
    text("Checking...", 60, 80, WHITE, font16)
    
    # ТВОИ ДАННЫЕ WI-FI
    WIFI_SSID = "MaximusFed2WiFi"
    WIFI_PASS = "57256062"
    
    GITHUB_URL = "https://raw.githubusercontent.com/MaximusFed2/mafep1-os/refs/heads/main/system/mafep1_os.py"
    
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        wlan.connect(WIFI_SSID, WIFI_PASS)
        
        text("Connecting...", 55, 110, YELLOW, font16)
        text(f"WiFi: {WIFI_SSID}", 40, 130, WHITE, font8)
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
        text(f"IP: {ip}", 70, 190, WHITE, font8)
        time.sleep_ms(1000)
        
        text("Downloading...", 50, 50, CYAN, font16)
        import urequests
        response = urequests.get(GITHUB_URL)
        
        if response.status_code == 200:
            github_code = response.text
            response.close()
            
            github_ver = get_version(github_code)
            local_ver = get_version_file('/sd/system/mafep1_os.py')
            
            text(f"Local: v{local_ver[0]}.{local_ver[1]}", 40, 80, WHITE, font8)
            text(f"GitHub: v{github_ver[0]}.{github_ver[1]}", 40, 100, CYAN, font8)
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
        text(f"Error: {str(e)[:20]}", 40, 130, RED, font16)
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
    text("Version 0.4", 65, 80, WHITE, font16)  # ИZMENENO!
    text("", 0, 100, WHITE, font8)
    text("Features:", 60, 120, YELLOW, font16)
    text("- App menu", 50, 140, WHITE, font8)
    text("- Game loader", 50, 155, WHITE, font8)
    text("- WiFi updates", 50, 170, WHITE, font8)
    text("- Dual fonts", 50, 185, WHITE, font8)  # NEW!
    text("- Better UX", 50, 200, WHITE, font8)  # NEW!
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
        ("About", about_screen, YELLOW),
    ]
    
    selected = 0
    
    beep(800, 50, 192)
    time.sleep_ms(50)
    beep(1200, 80, 256)
    
    while True:
        clear()
        draw_status_bar("MaFe P1 OS v0.4")  # IZMENENO!
        
        text("MaFe P1", 70, 40, CYAN, font16)
        
        for i, (name, _, color) in enumerate(menu_items):
            y = 80 + i * 40
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
print("MaFe P1 OS v0.4 starting...")  # IZMENENO!
print("Controls: Joy1=Nav, Joy1BTN=OK, Joy2BTN=Back")
print("New: Dual fonts, improved WiFi")  # NEW!
main_menu()
