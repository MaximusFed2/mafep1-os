# ftp_server.py - Полноценный FTP сервер для ESP32
# Поддерживает: SYST, FEAT, USER, PASS, PWD, CWD, CDUP, LIST, NLST, RETR, STOR, DELE, SIZE, PASV, TYPE, QUIT

import machine, time, os, network, socket, gc

# === НАСТРОЙКИ ===
FTP_PORT = 21
PASV_PORT = 50000  # Фиксированный порт для пассивного режима
BUFFER_SIZE = 1024

# Точка доступа
AP_SSID = "MaFeP1-FTP"
AP_PASSWORD = None  # Открытая сеть

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
        print("SD error:", e)
        return False

# === СОЗДАНИЕ AP ===
def start_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    if AP_PASSWORD:
        ap.config(essid=AP_SSID, password=AP_PASSWORD, authmode=network.AUTH_WPA2_PSK)
    else:
        ap.config(essid=AP_SSID, authmode=network.AUTH_OPEN)
    time.sleep_ms(1000)
    ip = ap.ifconfig()[0]
    print("AP:", AP_SSID, "IP:", ip)
    return ip

# === УТИЛИТЫ ===
def send_cmd(sock, msg):
    try:
        sock.send((msg + '\r\n').encode('utf-8'))
    except:
        pass

def recv_line(sock):
    data = b''
    try:
        sock.settimeout(30)
        while True:
            chunk = sock.recv(1)
            if not chunk:
                return None
            data += chunk
            if chunk == b'\n':
                break
    except OSError as e:
        err = e.args[0] if e.args else None
        if err in (110, 11, 116, 'ETIMEDOUT', 'EAGAIN'):
            return None
        raise
    line = data.decode('utf-8', 'ignore').strip()
    if line.endswith('\r'):
        line = line[:-1]
    return line

def open_pasv_connection(server_ip):
    """Открывает соединение для передачи данных в пассивном режиме"""
    data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    data_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        data_sock.bind(('0.0.0.0', PASV_PORT))
        data_sock.listen(1)
        data_sock.settimeout(10)
        conn, _ = data_sock.accept()
        data_sock.close()
        return conn
    except Exception as e:
        print("PASV error:", e)
        try: data_sock.close()
        except: pass
        return None

def get_full_path(current_dir, path):
    if path.startswith('/'):
        return path
    if path == '..':
        if current_dir == '/sd':
            return '/sd'
        parts = current_dir.rsplit('/', 1)
        return parts[0] if parts[0] else '/sd'
    if path == '.':
        return current_dir
    return current_dir + '/' + path

# === ОБРАБОТКА КЛИЕНТА ===
# Глобальная переменная для PASV сокета
pasv_data_sock = None

def handle_client(client_sock, addr, server_ip):
    global pasv_data_sock
    print("Client:", addr)
    current_dir = '/sd'
    pasv_data_sock = None
    
    send_cmd(client_sock, '220 MaFeP1 FTP Server ready')
    
    while True:
        line = recv_line(client_sock)
        if line is None:
            break
        
        print("CMD:", line)
        parts = line.split(' ', 1)
        cmd = parts[0].upper()
        arg = parts[1].strip() if len(parts) > 1 else ''
        
        if cmd == 'SYST':
            send_cmd(client_sock, '215 UNIX Type: L8')
        
        elif cmd == 'FEAT':
            send_cmd(client_sock, '211-Features:')
            send_cmd(client_sock, ' UTF8')
            send_cmd(client_sock, '211 End')
        
        elif cmd == 'USER':
            send_cmd(client_sock, '331 Password required')
        
        elif cmd == 'PASS':
            send_cmd(client_sock, '230 User logged in')
        
        elif cmd == 'TYPE':
            send_cmd(client_sock, '200 Type set')
        
        elif cmd == 'PWD':
            send_cmd(client_sock, '257 "' + current_dir + '"')
        
        elif cmd == 'CWD':
            new_dir = get_full_path(current_dir, arg)
            try:
                os.listdir(new_dir)
                current_dir = new_dir
                send_cmd(client_sock, '250 OK')
            except:
                send_cmd(client_sock, '550 Directory not found')
        
        elif cmd == 'CDUP':
            current_dir = get_full_path(current_dir, '..')
            send_cmd(client_sock, '250 OK')
        
        # === ИСПРАВЛЕННЫЙ PASV ===
        elif cmd == 'PASV':
            # Закрываем старый сокет если есть
            if pasv_data_sock:
                try: pasv_data_sock.close()
                except: pass
            
            # Создаём новый сокет для данных
            pasv_data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            pasv_data_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            pasv_data_sock.bind(('0.0.0.0', PASV_PORT))
            pasv_data_sock.listen(1)
            pasv_data_sock.settimeout(10)
            
            # Отправляем ответ клиенту
            ip_parts = server_ip.split('.')
            p1 = PASV_PORT // 256
            p2 = PASV_PORT % 256
            response = '227 Entering Passive Mode ({},{},{},{},{},{})'.format(
                int(ip_parts[0]), int(ip_parts[1]), 
                int(ip_parts[2]), int(ip_parts[3]), p1, p2
            )
            send_cmd(client_sock, response)
            print("PASV: Listening on port", PASV_PORT)
        
        # === ИСПРАВЛЕННЫЕ КОМАНДЫ ПЕРЕДАЧИ ===
        elif cmd == 'LIST' or cmd == 'NLST':
            send_cmd(client_sock, '150 Opening data connection')
            
            # Ждём подключения клиента к PASV сокету
            if pasv_data_sock:
                try:
                    data_conn, _ = pasv_data_sock.accept()
                    print("PASV: Client connected for data")
                    
                    items = os.listdir(current_dir)
                    if cmd == 'LIST':
                        for item in items:
                            full = current_dir + '/' + item
                            try:
                                os.listdir(full)
                                data_conn.send(('-rw-r--r-- 1 root root 0 ' + item + '\r\n').encode())
                            except:
                                size = os.stat(full)[6]
                                data_conn.send(('-rw-r--r-- 1 root root ' + str(size) + ' ' + item + '\r\n').encode())
                    else:
                        for item in items:
                            data_conn.send((item + '\r\n').encode())
                    
                    data_conn.close()
                    send_cmd(client_sock, '226 Transfer complete')
                except Exception as e:
                    print("LIST error:", e)
                    send_cmd(client_sock, '425 Error')
            else:
                send_cmd(client_sock, '425 No PASV connection')
        
        elif cmd == 'RETR':
            filepath = get_full_path(current_dir, arg)
            print("RETR:", filepath)
            send_cmd(client_sock, '150 Opening data connection')
            
            if pasv_data_sock:
                try:
                    data_conn, _ = pasv_data_sock.accept()
                    print("PASV: Client connected for data")
                    
                    with open(filepath, 'rb') as f:
                        while True:
                            chunk = f.read(BUFFER_SIZE)
                            if not chunk:
                                break
                            data_conn.send(chunk)
                    
                    data_conn.close()
                    send_cmd(client_sock, '226 Transfer complete')
                except Exception as e:
                    print("RETR error:", e)
                    send_cmd(client_sock, '550 File error')
            else:
                send_cmd(client_sock, '425 No PASV connection')
        
        elif cmd == 'STOR':
            filepath = get_full_path(current_dir, arg)
            print("STOR:", filepath)
            send_cmd(client_sock, '150 Opening data connection')
            
            if pasv_data_sock:
                try:
                    data_conn, _ = pasv_data_sock.accept()
                    print("PASV: Client connected for data")
                    
                    with open(filepath, 'wb') as f:
                        while True:
                            try:
                                chunk = data_conn.recv(BUFFER_SIZE)
                                if not chunk:
                                    break
                                f.write(chunk)
                            except OSError as e:
                                err = e.args[0] if e.args else None
                                if err not in (110, 11, 116, 'ETIMEDOUT', 'EAGAIN'):
                                    raise
                                break
                    
                    data_conn.close()
                    send_cmd(client_sock, '226 Transfer complete')
                except Exception as e:
                    print("STOR error:", e)
                    send_cmd(client_sock, '425 Error')
            else:
                send_cmd(client_sock, '425 No PASV connection')
        
        elif cmd == 'DELE':
            filepath = get_full_path(current_dir, arg)
            try:
                os.remove(filepath)
                send_cmd(client_sock, '250 Deleted')
            except:
                send_cmd(client_sock, '550 Not found')
        
        elif cmd == 'MKD':
            dirpath = get_full_path(current_dir, arg)
            try:
                os.mkdir(dirpath)
                send_cmd(client_sock, '257 Created')
            except:
                send_cmd(client_sock, '550 Error')
        
        elif cmd == 'RMD':
            dirpath = get_full_path(current_dir, arg)
            try:
                os.rmdir(dirpath)
                send_cmd(client_sock, '250 Deleted')
            except:
                send_cmd(client_sock, '550 Error')
        
        elif cmd == 'SIZE':
            filepath = get_full_path(current_dir, arg)
            try:
                size = os.stat(filepath)[6]
                send_cmd(client_sock, '213 ' + str(size))
            except:
                send_cmd(client_sock, '550 Not found')
        
        elif cmd == 'PORT':
            send_cmd(client_sock, '502 Use PASV mode')
        
        elif cmd == 'QUIT':
            send_cmd(client_sock, '221 Goodbye')
            break
        
        else:
            send_cmd(client_sock, '502 Command not implemented')
    
    # Очистка
    if pasv_data_sock:
        try: pasv_data_sock.close()
        except: pass
    try: client_sock.close()
    except: pass
    print("Client closed")
        
        # === ПЕРЕДАЧА ФАЙЛОВ ===
        
        elif cmd == 'RETR':
            filepath = get_full_path(current_dir, arg)
            print("RETR:", filepath)
            send_cmd(client_sock, '150 Opening data connection')
            data_sock = open_pasv_connection(server_ip)
            if data_sock:
                try:
                    with open(filepath, 'rb') as f:
                        while True:
                            chunk = f.read(BUFFER_SIZE)
                            if not chunk:
                                break
                            data_sock.send(chunk)
                    send_cmd(client_sock, '226 Transfer complete')
                except Exception as e:
                    print("RETR error:", e)
                    send_cmd(client_sock, '550 File error: ' + str(e)[:30])
                finally:
                    try: data_sock.close()
                    except: pass
            else:
                send_cmd(client_sock, '425 Can\'t open data connection')
        
        elif cmd == 'STOR':
            filepath = get_full_path(current_dir, arg)
            print("STOR:", filepath)
            send_cmd(client_sock, '150 Opening data connection')
            data_sock = open_pasv_connection(server_ip)
            if data_sock:
                try:
                    with open(filepath, 'wb') as f:
                        while True:
                            try:
                                chunk = data_sock.recv(BUFFER_SIZE)
                                if not chunk:
                                    break
                                f.write(chunk)
                            except OSError as e:
                                err = e.args[0] if e.args else None
                                if err not in (110, 11, 116, 'ETIMEDOUT', 'EAGAIN'):
                                    raise
                                break
                    send_cmd(client_sock, '226 Transfer complete')
                except Exception as e:
                    print("STOR error:", e)
                    send_cmd(client_sock, '425 Error: ' + str(e)[:30])
                finally:
                    try: data_sock.close()
                    except: pass
            else:
                send_cmd(client_sock, '425 Can\'t open data connection')
        
        # === УПРАВЛЕНИЕ ФАЙЛАМИ ===
        
        elif cmd == 'DELE':
            filepath = get_full_path(current_dir, arg)
            try:
                os.remove(filepath)
                send_cmd(client_sock, '250 Deleted')
            except:
                send_cmd(client_sock, '550 Not found')
        
        elif cmd == 'MKD':
            dirpath = get_full_path(current_dir, arg)
            try:
                os.mkdir(dirpath)
                send_cmd(client_sock, '257 Created')
            except:
                send_cmd(client_sock, '550 Error')
        
        elif cmd == 'RMD':
            dirpath = get_full_path(current_dir, arg)
            try:
                os.rmdir(dirpath)
                send_cmd(client_sock, '250 Deleted')
            except:
                send_cmd(client_sock, '550 Error')
        
        elif cmd == 'SIZE':
            filepath = get_full_path(current_dir, arg)
            try:
                size = os.stat(filepath)[6]
                send_cmd(client_sock, '213 ' + str(size))
            except:
                send_cmd(client_sock, '550 Not found')
        
        # === ПАСИВНЫЙ РЕЖИМ ===
        
        elif cmd == 'PASV':
            # Формат: 227 Entering Passive Mode (h1,h2,h3,h4,p1,p2)
            ip_parts = server_ip.split('.')
            p1 = PASV_PORT // 256
            p2 = PASV_PORT % 256
            response = '227 Entering Passive Mode ({},{},{},{},{},{})'.format(
                int(ip_parts[0]), int(ip_parts[1]), 
                int(ip_parts[2]), int(ip_parts[3]), p1, p2
            )
            send_cmd(client_sock, response)
        
        elif cmd == 'PORT':
            send_cmd(client_sock, '502 Use PASV mode')
        
        # === ЗАВЕРШЕНИЕ ===
        
        elif cmd == 'QUIT':
            send_cmd(client_sock, '221 Goodbye')
            break
        
        else:
            send_cmd(client_sock, '502 Command not implemented')
    
    try: client_sock.close()
    except: pass
    print("Client closed")

# === ГЛАВНЫЙ ЦИКЛ ===
def main():
    print("MaFeP1 FTP Server v1.3")
    mount_sd()
    ap_ip = start_ap()
    
    if HAS_DISPLAY:
        clear()
        draw_status_bar("FTP Server")
        text("WiFi: " + AP_SSID, 10, 40, CYAN)
        text("(OPEN)", 10, 60, YELLOW)
        text("IP: " + ap_ip, 10, 85, GREEN)
        text("Port: 21", 10, 105, WHITE)
        text("Connect:", 10, 130, YELLOW)
        text(ap_ip + ":21", 10, 145, GREEN)
        text("Joy2BTN: Stop", 10, 180, WHITE)
    
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(('0.0.0.0', FTP_PORT))
    server_sock.listen(1)
    server_sock.settimeout(2)
    
    print("FTP ready on", ap_ip + ":21")
    client_count = 0
    
    while True:
        if joy2_btn and joy2_btn.value() == 0:
            time.sleep_ms(300)
            if joy2_btn.value() == 0:
                print("Stopping...")
                break
        
        try:
            client_sock, addr = server_sock.accept()
            client_count += 1
            print("\n=== Client #" + str(client_count) + " ===")
            handle_client(client_sock, addr, ap_ip)
            gc.collect()
        
        except OSError as e:
            err = e.args[0] if e.args else None
            if err not in (110, 11, 116, 'ETIMEDOUT', 'EAGAIN'):
                print("Accept error:", e)
        except Exception as e:
            print("Error:", e)
    
    server_sock.close()
    network.WLAN(network.AP_IF).active(False)
    print("Stopped")
    
    if HAS_DISPLAY:
        clear()
        draw_status_bar("Stopped")
        text("FTP stopped", 10, 100, YELLOW)
        time.sleep_ms(2000)

main()
