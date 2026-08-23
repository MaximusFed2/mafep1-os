# ftp_server.py - FTP Server for ESP32 MicroPython
# Compatible with MicroPython (no socket.timeout attribute)
# Supports: PASV mode, LIST, RETR, STOR, DELE, MKD, RMD, PWD, CWD

import machine, time, os, network, socket, gc

# === НАСТРОЙКИ ===
FTP_PORT = 21
PASV_PORT_START = 50000
PASV_PORT_END = 50100
BUFFER_SIZE = 1024

# === ДИСПЛЕЙ (если доступен) ===
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
    except Exception as e:
        print("SD mount error:", e)
        return False

# === ПОЛУЧИТЬ IP ===
def get_ip():
    try:
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            return wlan.ifconfig()[0]
    except:
        pass
    try:
        ap = network.WLAN(network.AP_IF)
        if ap.active():
            return ap.ifconfig()[0]
    except:
        pass
    return "192.168.4.1"

# === ПОЛУЧИТЬ СВОБОДНЫЙ ПОРТ ДЛЯ PASV ===
def get_pasv_port():
    for port in range(PASV_PORT_START, PASV_PORT_END):
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            test_sock.bind(('0.0.0.0', port))
            test_sock.close()
            return port
        except OSError:
            continue
    return PASV_PORT_START

# === FTP КЛИЕНТ ===
class FTPClient:
    def __init__(self, client_sock, addr, server_ip):
        self.client = client_sock
        self.addr = addr
        self.server_ip = server_ip
        self.current_dir = '/sd'
        self.data_sock = None
        self.pasv_port = None
        self.username = None
        self.password = None
        self.binary_mode = True
        self.logged_in = False
        
        # Приветствие
        self.send_response(220, "MaFeP1 FTP Server ready")
    
    def send_response(self, code, msg):
        try:
            response = str(code) + ' ' + msg + '\r\n'
            self.client.send(response.encode('utf-8'))
        except Exception as e:
            print("Send error:", e)
    
    def send_data(self, data):
        """Отправляет данные через data socket"""
        if self.data_sock is None:
            return False
        try:
            if isinstance(data, str):
                data = data.encode('utf-8')
            sent = 0
            total = len(data)
            while sent < total:
                n = self.data_sock.send(data[sent:])
                if n == 0:
                    break
                sent += n
            return True
        except Exception as e:
            print("Data send error:", e)
            return False
    
    def open_data_connection(self):
        """Открывает соединение для передачи данных (PASV режим)"""
        try:
            if self.data_sock:
                try: self.data_sock.close()
                except: pass
            
            self.data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.data_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.data_sock.bind(('0.0.0.0', self.pasv_port))
            self.data_sock.listen(1)
            self.data_sock.settimeout(30)
            
            conn, _ = self.data_sock.accept()
            self.data_sock.close()
            self.data_sock = conn
            return True
        except Exception as e:
            print("Data connection error:", e)
            return False
    
    def close_data_connection(self):
        if self.data_sock:
            try: self.data_sock.close()
            except: pass
            self.data_sock = None
    
    def get_full_path(self, path):
        """Возвращает полный путь"""
        if path.startswith('/'):
            return path
        return self.current_dir + '/' + path
    
    def handle_command(self, line):
        """Обрабатывает FTP команду"""
        parts = line.split(' ', 1)
        cmd = parts[0].upper()
        arg = parts[1].strip() if len(parts) > 1 else ''
        
        print("CMD:", cmd, "ARG:", arg)
        
        # === АУТЕНТИФИКАЦИЯ ===
        if cmd == 'USER':
            self.username = arg
            self.send_response(331, "Password required")
        
        elif cmd == 'PASS':
            self.password = arg
            self.logged_in = True
            self.send_response(230, "User logged in")
        
        # === СИСТЕМНАЯ ИНФОРМАЦИЯ ===
        elif cmd == 'SYST':
            self.send_response(215, "UNIX Type: L8")
        
        elif cmd == 'TYPE':
            if arg.upper() == 'I':
                self.binary_mode = True
                self.send_response(200, "Type set to I (Binary)")
            elif arg.upper() == 'A':
                self.binary_mode = False
                self.send_response(200, "Type set to A (ASCII)")
            else:
                self.send_response(504, "Type not implemented")
        
        # === НАВИГАЦИЯ ===
        elif cmd == 'PWD':
            self.send_response(257, '"' + self.current_dir + '"')
        
        elif cmd == 'CWD':
            new_dir = self.get_full_path(arg)
            try:
                os.listdir(new_dir)
                self.current_dir = new_dir
                self.send_response(250, "Directory changed")
            except:
                self.send_response(550, "Directory not found")
        
        elif cmd == 'CDUP':
            if self.current_dir != '/sd':
                parts = self.current_dir.rsplit('/', 1)
                self.current_dir = parts[0] if parts[0] else '/sd'
            self.send_response(250, "Directory changed")
        
        # === СПИСКИ ===
        elif cmd == 'LIST' or cmd == 'NLST':
            self.send_response(150, "Opening data connection")
            if self.open_data_connection():
                try:
                    items = os.listdir(self.current_dir)
                    file_list = ''
                    for item in items:
                        full_path = self.current_dir + '/' + item
                        try:
                            os.listdir(full_path)
                            file_list += 'd ' + item + '\r\n'
                        except:
                            file_list += '- ' + item + '\r\n'
                    
                    self.send_data(file_list)
                    self.send_response(226, "Transfer complete")
                except Exception as e:
                    self.send_response(425, "Error: " + str(e))
                finally:
                    self.close_data_connection()
            else:
                self.send_response(425, "Can't open data connection")
        
        # === ПЕРЕДАЧА ФАЙЛОВ ===
        elif cmd == 'RETR':
            filepath = self.get_full_path(arg)
            self.send_response(150, "Opening data connection")
            if self.open_data_connection():
                try:
                    with open(filepath, 'rb') as f:
                        while True:
                            chunk = f.read(BUFFER_SIZE)
                            if not chunk:
                                break
                            self.send_data(chunk)
                    self.send_response(226, "Transfer complete")
                except Exception as e:
                    self.send_response(550, "File error: " + str(e))
                finally:
                    self.close_data_connection()
            else:
                self.send_response(425, "Can't open data connection")
        
        elif cmd == 'STOR':
            filepath = self.get_full_path(arg)
            self.send_response(150, "Opening data connection")
            if self.open_data_connection():
                try:
                    with open(filepath, 'wb') as f:
                        while True:
                            try:
                                chunk = self.data_sock.recv(BUFFER_SIZE)
                                if not chunk:
                                    break
                                f.write(chunk)
                            except OSError as e:
                                err_code = e.args[0] if e.args else None
                                if err_code not in (110, 11, 'ETIMEDOUT', 'EAGAIN'):
                                    raise
                                break
                    self.send_response(226, "Transfer complete")
                except Exception as e:
                    self.send_response(425, "Error: " + str(e))
                finally:
                    self.close_data_connection()
            else:
                self.send_response(425, "Can't open data connection")
        
        # === УПРАВЛЕНИЕ ФАЙЛАМИ ===
        elif cmd == 'DELE':
            filepath = self.get_full_path(arg)
            try:
                os.remove(filepath)
                self.send_response(250, "File deleted")
            except:
                self.send_response(550, "File not found")
        
        elif cmd == 'MKD':
            dirpath = self.get_full_path(arg)
            try:
                os.mkdir(dirpath)
                self.send_response(257, '"' + dirpath + '" created')
            except:
                self.send_response(550, "Can't create directory")
        
        elif cmd == 'RMD':
            dirpath = self.get_full_path(arg)
            try:
                os.rmdir(dirpath)
                self.send_response(250, "Directory deleted")
            except:
                self.send_response(550, "Can't delete directory")
        
        elif cmd == 'SIZE':
            filepath = self.get_full_path(arg)
            try:
                size = os.stat(filepath)[6]
                self.send_response(213, str(size))
            except:
                self.send_response(550, "File not found")
        
        # === PASV РЕЖИМ ===
        elif cmd == 'PASV':
            self.pasv_port = get_pasv_port()
            # Формат: (h1,h2,h3,h4,p1,p2)
            ip_parts = self.server_ip.split('.')
            p1 = self.pasv_port // 256
            p2 = self.pasv_port % 256
            pasv_response = '({},{},{},{},{},{})'.format(
                int(ip_parts[0]), int(ip_parts[1]), 
                int(ip_parts[2]), int(ip_parts[3]), p1, p2
            )
            self.send_response(227, "Entering Passive Mode " + pasv_response)
        
        # === PORT РЕЖИМ (упрощенно) ===
        elif cmd == 'PORT':
            self.send_response(200, "PORT mode not supported, use PASV")
        
        # === ЗАВЕРШЕНИЕ ===
        elif cmd == 'QUIT':
            self.send_response(221, "Goodbye")
            return False
        
        # === НЕИЗВЕСТНАЯ КОМАНДА ===
        else:
            self.send_response(502, "Command not implemented")
        
        return True
    
    def run(self):
        """Главный цикл обработки клиента"""
        print("Client connected:", self.addr)
        self.client.settimeout(120)
        
        try:
            while True:
                try:
                    data = b''
                    while True:
                        try:
                            chunk = self.client.recv(1)
                            if not chunk:
                                return
                            data += chunk
                            if chunk == b'\n':
                                break
                        except OSError as e:
                            err_code = e.args[0] if e.args else None
                            if err_code in (110, 11, 'ETIMEDOUT', 'EAGAIN'):
                                continue
                            raise
                    
                    if not data:
                        return
                    
                    line = data.decode('utf-8', 'ignore').strip()
                    if not line:
                        continue
                    
                    # Убираем \r если есть
                    if line.endswith('\r'):
                        line = line[:-1]
                    
                    if not self.handle_command(line):
                        break
                
                except OSError as e:
                    err_code = e.args[0] if e.args else None
                    if err_code in (110, 11, 'ETIMEDOUT', 'EAGAIN'):
                        continue
                    print("Client error:", e)
                    break
                except Exception as e:
                    print("Client error:", e)
                    break
        
        finally:
            self.close_data_connection()
            try: self.client.close()
            except: pass
            print("Client disconnected:", self.addr)

# === FTP СЕРВЕР ===
class FTPServer:
    def __init__(self):
        self.server_sock = None
        self.running = False
    
    def start(self):
        """Запускает FTP сервер"""
        mount_sd()
        ip = get_ip()
        
        print("FTP Server starting on", ip + ":" + str(FTP_PORT))
        
        if HAS_DISPLAY:
            clear()
            draw_status_bar("FTP Server")
            text("Running...", 10, 50, GREEN)
            text("IP: " + ip, 10, 80, WHITE)
            text("Port: " + str(FTP_PORT), 10, 100, WHITE)
            text("", 0, 120, WHITE)
            text("Use AndFTP or", 10, 130, YELLOW)
            text("CX File Explorer", 10, 145, YELLOW)
            text("", 0, 165, WHITE)
            text("Joy2BTN: Stop", 10, 180, WHITE)
        
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(('0.0.0.0', FTP_PORT))
        self.server_sock.listen(5)
        self.server_sock.settimeout(2)
        
        self.running = True
        
        while self.running:
            # Проверяем кнопку выхода
            if joy2_btn and joy2_btn.value() == 0:
                time.sleep_ms(300)
                if joy2_btn.value() == 0:
                    print("Stopping FTP server...")
                    break
            
            try:
                client_sock, addr = self.server_sock.accept()
                print("New connection from:", addr)
                
                # Обрабатываем клиента
                client = FTPClient(client_sock, addr, ip)
                client.run()
                
                gc.collect()
            
            except OSError as e:
                err_code = e.args[0] if e.args else None
                if err_code not in (110, 11, 'ETIMEDOUT', 'EAGAIN'):
                    print("Accept error:", e)
            except Exception as e:
                print("Server error:", e)
        
        self.stop()
    
    def stop(self):
        """Останавливает сервер"""
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except:
                pass
        print("FTP server stopped")
        
        if HAS_DISPLAY:
            clear()
            draw_status_bar("FTP Stopped")
            text("Server stopped", 10, 100, YELLOW)
            time.sleep_ms(1500)

# === ЗАПУСК ===
print("MaFeP1 FTP Server v1.0")
print("Starting...")

server = FTPServer()
server.start()
