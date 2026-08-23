# MaFe P1 OS - Graphical Menu v1.0
# Графическое меню с иконками приложений

import machine, time, os, gc
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

# === ЦВЕТА ===
BLACK = 0x0000
WHITE = 0xFFFF
CYAN = 0x07FF
GREEN = 0x07E0
YELLOW = 0xFFE0
RED = 0xF800
BLUE = 0x001F
DARK_GRAY = 0x3333
LIGHT_GRAY = 0x8888

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
        if y < 2048 - self.threshold: return 'up'
        elif y > 2048 + self.threshold: return 'down'
        elif x < 2048 - self.threshold: return 'left'
        elif x > 2048 + self.threshold: return 'right'
        return 'center'
    
    def btn_pressed(self, debounce_ms=200):
        now = time.ticks_ms()
        if self.btn.value() == 0 and time.ticks_diff(now, self.last_time) > debounce_ms:
            self.last_time = now
            return True
        return False

joy1 = Joystick(joy1_x, joy1_y, joy1_btn)
joy2 = Joystick(joy2_x, joy2_y, joy2_btn)

# === УТИЛИТЫ ===
def clear():
    display.fill(BLACK)

def text(msg, x, y, color=WHITE, font=font16):
    display.text(font, msg, x, y, color)

# === ЗАГРУЗКА ИКОНКИ ===
def load_icon(filepath):
    """Загружает PNG иконку 16x16"""
    try:
        with open(filepath, 'rb') as f:
            # Простой парсинг PNG (для 16x16 иконок)
            # В реальном коде нужно использовать библиотеку для PNG
            # Здесь заглушка - рисуем круг
            return True
    except:
        return False

def draw_circle_icon(x, y, color):
    """Рисует иконку в круге"""
    # Рисуем круг
    for i in range(-20, 21):
        for j in range(-20, 21):
            if i*i + j*j <= 400:  # радиус 20
                display.pixel(x + i, y + j, color)

def draw_app_icon(x, y, icon_path, name):
    """Рисует иконку приложения с подписью"""
    # Круг для иконки
    display.fill_circle(x + 23, y + 23, 23, DARK_GRAY)
    display.circle(x + 23, y + 23, 23, WHITE)
    
    # Загрузка иконки (если есть)
    if load_icon(icon_path):
        # Здесь должна быть отрисовка PNG
        # Пока рисуем цветной круг
        display.fill_circle(x + 23, y + 23, 18, CYAN)
    
    # Имя приложения (мелким текстом)
    if name:
        short_name = name[:10] if len(name) > 10 else name
        text(short_name, x - 5, y + 52, WHITE, font8)

# === МОНТИРОВАНИЕ SD ===
def mount_sd():
    try:
        if 'sd' in os.listdir('/'):
            return True
        import sdcard
        sd_spi = machine.SoftSPI(baudrate=1000000, polarity=0, phase=0,
                                 sck=machine.Pin(14), mosi=machine.Pin(17), miso=machine.Pin(18))
        sd = sdcard.SDCard(sd_spi, machine.Pin(16))
        os.mount(sd, '/sd')
        return True
    except:
        return False

# === ПОЛУЧЕНИЕ ПРИЛОЖЕНИЙ ===
def get_apps():
    """Сканирует папки /sd/games и /sd/apps"""
    apps = []
    
    for folder in ['/sd/games', '/sd/apps']:
        try:
            items = os.listdir(folder)
            for item in items:
                item_path = folder + '/' + item
                try:
                    # Проверяем что это папка
                    os.listdir(item_path)
                    
                    # Ищем .py файл
                    py_file = None
                    png_file = None
                    
                    files = os.listdir(item_path)
                    for f in files:
                        if f.endswith('.py'):
                            py_file = item_path + '/' + f
                        elif f.endswith('.png'):
                            png_file = item_path + '/' + f
                    
                    if py_file:
                        apps.append({
                            'name': item,
                            'py': py_file,
                            'icon': png_file,
                            'type': 'game' if 'games' in folder else 'app'
                        })
                except:
                    pass
        except:
            pass
    
    apps.sort(key=lambda x: x['name'])
    return apps

# === ЗАПУСК ПРИЛОЖЕНИЯ ===
def launch_app(app):
    """Запускает приложение"""
    clear()
    text("Loading...", 60, 100, CYAN, font16)
    text(app['name'], 50, 130, WHITE, font16)
    time.sleep_ms(500)
    
    try:
        with open(app['py'], 'r') as f:
            code = f.read()
        gc.collect()
        exec(code, {'__name__': '__main__'})
    except Exception as e:
        clear()
        text("Error!", 80, 100, RED, font16)
        text(str(e)[:20], 40, 130, YELLOW, font8)
        time.sleep_ms(2000)

# === ГРАФИЧЕСКОЕ МЕНЮ ===
def graphical_menu():
    """Основное графическое меню"""
    mount_sd()
    apps = get_apps()
    
    # Настройки сетки
    cols = 5
    rows = 4
    icon_width = 48
    icon_height = 70
    start_x = 10
    start_y = 40
    
    selected = 0
    page = 0
    apps_per_page = cols * rows
    total_pages = max(1, (len(apps) + apps_per_page - 1) // apps_per_page)
    
    while True:
        clear()
        
        # Заголовок
        text("MaFe P1 OS", 60, 5, CYAN, font16)
        text("Page " + str(page + 1) + "/" + str(total_pages), 170, 5, YELLOW, font8)
        
        # Рисуем иконки на текущей странице
        start_idx = page * apps_per_page
        end_idx = min(start_idx + apps_per_page, len(apps))
        
        for i in range(start_idx, end_idx):
            app = apps[i]
            pos = i - start_idx
            row = pos // cols
            col = pos % cols
            
            x = start_x + col * icon_width
            y = start_y + row * icon_height
            
            # Подсветка выбранного
            if i == selected:
                display.fill_rect(x - 3, y - 3, 52, 52, DARK_GRAY)
                draw_app_icon(x, y, app['icon'], app['name'])
            else:
                draw_app_icon(x, y, app['icon'], app['name'])
        
        # Нижняя панель с кнопками
        display.fill_rect(0, 215, 240, 25, DARK_GRAY)
        
        # Кнопки (иконки)
        btn_positions = [
            (10, "Settings"),
            (55, "Web"),
            (100, "Apps"),
            (145, "Text Menu"),
            (190, "Update")
        ]
        
        for i, (x, label) in enumerate(btn_positions):
            display.fill_circle(x + 18, 228, 18, LIGHT_GRAY)
            display.circle(x + 18, 228, 18, WHITE)
            # text(label, x - 5, 220, WHITE, font8)
        
        # Индикатор выбранной кнопки
        display.fill_circle(145 + 18, 228, 18, CYAN)
        text("T", 158, 223, BLACK, font8)
        
        # Навигация
        direction = joy1.read()
        
        if direction == 'left':
            if selected % cols > 0:
                selected -= 1
            elif page > 0:
                page -= 1
                selected = min(selected + cols, len(apps) - 1)
            time.sleep_ms(150)
        
        elif direction == 'right':
            if selected % cols < cols - 1 and selected < len(apps) - 1:
                selected += 1
            elif page < total_pages - 1:
                page += 1
                selected = max(selected - cols, 0)
            time.sleep_ms(150)
        
        elif direction == 'up':
            if selected >= cols:
                selected -= cols
            time.sleep_ms(150)
        
        elif direction == 'down':
            if selected < len(apps) - cols:
                selected += cols
            time.sleep_ms(150)
        
        elif joy1.btn_pressed():
            # Запуск приложения
            if selected < len(apps):
                launch_app(apps[selected])
                mount_sd()
                apps = get_apps()  # Обновить список после возврата
                apps_per_page = cols * rows
                total_pages = max(1, (len(apps) + apps_per_page - 1) // apps_per_page)
                page = 0
                selected = 0
        
        elif joy2.btn_pressed():
            # Переключение в текстовое меню
            try:
                import mafep1_os
                mafep1_os.main_menu()
            except:
                exec(open('/sd/system/mafep1_os.py').read())
        
        time.sleep_ms(16)

# === ОБНОВЛЕНИЕ МЕНЮ ===
def update_menu():
    """Обновляет графическое меню с GitHub"""
    clear()
    text("Updating...", 60, 100, CYAN, font16)
    
    try:
        import network, urequests
        
        # Подключаемся к WiFi
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        # Загружаем конфиг WiFi
        try:
            with open('/sd/system/wifi_config.txt', 'r') as f:
                lines = f.read().split('\n')
                ssid, password = lines[0], lines[1]
            wlan.connect(ssid, password)
        except:
            text("No WiFi config", 50, 130, YELLOW, font8)
            time.sleep_ms(2000)
            return
        
        # Ждём подключения
        for i in range(20):
            if wlan.isconnected():
                break
            time.sleep_ms(500)
        
        if not wlan.isconnected():
            text("WiFi failed", 60, 160, RED, font16)
            time.sleep_ms(2000)
            return
        
        # Скачиваем файл
        url = "https://raw.githubusercontent.com/MaximusFed2/mafep1-os/refs/heads/main/system/mafep1_os_menu.py"
        response = urequests.get(url)
        
        if response.status_code == 200:
            with open('/sd/system/mafep1_os_menu_new.py', 'w') as f:
                f.write(response.text)
            
            try:
                os.remove('/sd/system/mafep1_os_menu.py')
            except:
                pass
            
            os.rename('/sd/system/mafep1_os_menu_new.py', '/sd/system/mafep1_os_menu.py')
            
            text("Success!", 70, 160, GREEN, font16)
            text("Rebooting...", 60, 180, YELLOW, font8)
            time.sleep_ms(2000)
            machine.reset()
        else:
            text("Download failed", 40, 160, RED, font16)
            time.sleep_ms(2000)
        
        response.close()
        wlan.disconnect()
        wlan.active(False)
    
    except Exception as e:
        text("Error: " + str(e)[:20], 30, 160, RED, font8)
        time.sleep_ms(2000)

# === ЗАПУСК ===
if __name__ == '__main__':
    graphical_menu()
