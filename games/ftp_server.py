# ftp_server.py - FTP Server with Open AP Mode (No Password)
import machine, time, os, network, socket, gc

# === НАСТРОЙКИ ===
FTP_PORT = 21
BUFFER_SIZE = 1024

# Настройки точки доступа (БЕЗ ПАРОЛЯ)
AP_SSID = "MaFeP1-FTP"
AP_PASSWORD = None  # None = открытая сеть

# === ДИСПЛЕЙ ===
try:
    import st7789, vga1_16x16 as font16, vga1_8x8 as font8
    HAS_DISPLAY = True
except:
    HAS_DISPLAY = False

if HAS_DISPLAY:
    spi = machine.SPI(2, baudrate=40000000, polarity=1, phase=1,
                      sck=machine.Pin(12), mosi=machine.Pin(11), miso=machine.Pin(13))
    display = st7789.ST7789(spi, 240, 240,
                            dc=machine.Pin(4, machine.Pin.OUT),
                            reset=machine.Pin(5, machine.Pin.OUT), cs=None)
    joy2_btn = machine.Pin(15, machine.Pin.IN, machine.Pin.PULL_UP)
    
    BLACK = 0x0000
    CYAN = 0x07FF
    GREEN = 0x07E0
    WHITE = 0xFFFF
    YELLOW = 0xFFE0
    RED = 0xF800
    MEDIUM_BLUE = 0x0022
    
    def clear(): display.fill(BLACK)
    def text(msg, x, y, color=WHITE, font=font16): display.text(font, msg, x, y, color)
    def draw_status_bar(title):
        display.fill_rect(0, 0, 240, 25, MEDIUM_BLUE)
        text(title, 5, 5, WHITE, font8)
else:
    joy2_btn = None
    def clear(): pass
    def text(*args): pass
    def draw_status_bar(*args): pass

# === МОНТИРОВАНИЕ SD ===
def mount_sd():
    try:
        if 'sd' in os.listdir('/'):
            os.chdir('/sd')
            return True
        import sdcard
        sd_spi = machine.SoftSPI(baudrate=1000000, polarity=0, phase=0,
                                 sck=machine.Pin(14), mosi=machine.Pin(17), miso=machine.Pin(18))
        sd = sdcard.SDCard(sd_spi, machine.Pin(16))
        os.mount(sd, '/sd')
        os.chdir('/sd')
        return True
    except OSError as e:
        if "EPERM" in str(e):
            os.chdir('/sd')
            return True
        print("SD mount error:", e)
        return False

# === СОЗДАНИЕ ОТКРЫТОЙ ТОЧКИ ДОСТУПА ===
def start_ap():
    """Создаёт открытую WiFi точку доступа"""
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    
    # Конфигурация без пароля
    if AP_PASSWORD:
        ap.config(essid=AP_SSID, password=AP_PASSWORD, authmode=network.AUTH_WPA2_PSK)
    else:
        ap.config(essid=AP_SSID, authmode=network.AUTH_OPEN)
    
    time.sleep_ms(1000)
    
    ip = ap.ifconfig()[0]
    print("AP created:", AP_SSID)
    print("AP IP:", ip)
    print("AP Password:", AP_PASSWORD if AP_PASSWORD else "OPEN (no password)")
    
    return ip

# === FTP СЕРВЕР (УПРОЩЁННЫЙ) ===
def start_ftp_server(ap_ip):
    """Запускает FTP сервер"""
    print("Starting FTP server on", ap_ip + ":" + str(FTP_PORT))
    
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(('0.0.0.0', FTP_PORT))
    server_sock.listen(1)
    server_sock.settimeout(5)
    
    print("FTP server ready!")
    print("Waiting for connections...")
    
    client_num = 0
    
    while True:
        # Проверка кнопки выхода
        if joy2_btn and joy2_btn.value() == 0:
            time.sleep_ms(300)
            if joy2_btn.value() == 0:
                print("Stopping...")
                break
        
        try:
            client_sock, addr = server_sock.accept()
            client_num += 1
            print("\n=== Client #" + str(client_num) + " ===")
            print("Connected from:", addr)
            
            # Отправляем приветствие
            client_sock.send(b'220 MaFeP1 FTP Server ready\r\n')
            print("Sent welcome message")
            
            current_dir = '/sd'
            
            # Обрабатываем команды
            while True:
                try:
                    # Читаем команду
                    data = b''
                    while True:
                        chunk = client_sock.recv(1)
                        if not chunk:
                            break
                        data += chunk
                        if chunk == b'\n':
                            break
                    
                    if not data:
                        print("Client disconnected")
                        break
                    
                    line = data.decode('utf-8', 'ignore').strip()
                    if line.endswith('\r'):
                        line = line[:-1]
                    
                    print("CMD:", line)
                    
                    parts = line.split(' ', 1)
                    cmd = parts[0].upper()
                    arg = parts[1] if len(parts) > 1 else ''
                    
                    # USER
                    if cmd == 'USER':
                        client_sock.send(b'331 Password required\r\n')
                    
                    # PASS
                    elif cmd == 'PASS':
                        client_sock.send(b'230 User logged in\r\n')
                    
                    # PWD
                    elif cmd == 'PWD':
                        response = '257 "' + current_dir + '"\r\n'
                        client_sock.send(response.encode())
                    
                    # LIST
                    elif cmd == 'LIST':
                        client_sock.send(b'150 Opening data connection\r\n')
                        items = os.listdir(current_dir)
                        file_list = ''
                        for item in items:
                            file_list += item + '\r\n'
                        client_sock.send(file_list.encode())
                        client_sock.send(b'226 Transfer complete\r\n')
                    
                    # QUIT
                    elif cmd == 'QUIT':
                        client_sock.send(b'221 Goodbye\r\n')
                        break
                    
                    # Неизвестная команда
                    else:
                        client_sock.send(b'502 Command not implemented\r\n')
                
                except OSError as e:
                    print("Client error:", e)
                    break
                except Exception as e:
                    print("Error:", e)
                    break
            
            client_sock.close()
            print("Client disconnected\n")
            gc.collect()
        
        except OSError as e:
            err_code = e.args[0] if e.args else None
            if err_code not in (110, 11, 116, 'ETIMEDOUT', 'EAGAIN'):
                print("Accept error:", e)
        except Exception as e:
            print("Server error:", e)
    
    server_sock.close()
    print("FTP server stopped")

# === ЗАПУСК ===
print("MaFeP1 FTP Server v1.2")
print("Starting...")

mount_sd()
ap_ip = start_ap()

if HAS_DISPLAY:
    clear()
    draw_status_bar("FTP Server")
    text("WiFi: " + AP_SSID, 10, 40, CYAN)
    text("(OPEN - no pass)", 10, 60, YELLOW)
    text("", 0, 75, WHITE)
    text("IP: " + ap_ip, 10, 85, GREEN)
    text("Port: 21", 10, 105, WHITE)
    text("", 0, 120, WHITE)
    text("Connect:", 10, 130, YELLOW)
    text(ap_ip + ":21", 10, 145, GREEN)
    text("", 0, 160, WHITE)
    text("Joy2BTN: Stop", 10, 180, WHITE)

start_ftp_server(ap_ip)

# Отключаем AP при выходе
ap = network.WLAN(network.AP_IF)
ap.active(False)
print("AP disabled")

if HAS_DISPLAY:
    clear()
    draw_status_bar("Stopped")
    text("FTP stopped", 10, 100, YELLOW)
    time.sleep_ms(2000)
