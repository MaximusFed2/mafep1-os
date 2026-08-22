# ftp_server.py - FTP сервер для ESP32
import machine, time, os, network, socket

# === НАСТРОЙКИ ===
FTP_PORT = 21
DATA_PORT = 20
BUFFER_SIZE = 1024

# === ЦВЕТА ДЛЯ ЭКРАНА ===
import st7789, vga1_16x16 as font16, vga1_8x8 as font8

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

def clear():
    display.fill(BLACK)

def text(msg, x, y, color=WHITE, font=font16):
    display.text(font, msg, x, y, color)

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
        os.chdir('/sd')
        return True
    except:
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

# === FTP СЕРВЕР ===
class FTPServer:
    def __init__(self):
        self.current_dir = '/sd'
        self.data_sock = None
    
    def send_response(self, client, code, msg):
        response = str(code) + ' ' + msg + '\r\n'
        client.send(response.encode('utf-8'))
    
    def handle_client(self, client, addr):
        print("FTP client connected:", addr)
        self.send_response(client, 220, "MaFeP1 FTP Server ready")
        
        client.settimeout(60)
        
        while True:
            try:
                data = client.recv(BUFFER_SIZE).decode('utf-8', 'ignore').strip()
                if not data:
                    break
                
                parts = data.split(' ', 1)
                cmd = parts[0].upper()
                arg = parts[1] if len(parts) > 1 else ''
                
                print("CMD:", cmd, "ARG:", arg)
                
                if cmd == 'USER':
                    self.send_response(client, 230, "User logged in")
                
                elif cmd == 'PASS':
                    self.send_response(client, 230, "Password ok")
                
                elif cmd == 'SYST':
                    self.send_response(client, 215, "UNIX Type: L8")
                
                elif cmd == 'PWD':
                    self.send_response(client, 257, '"' + self.current_dir + '"')
                
                elif cmd == 'CWD':
                    new_dir = self.current_dir + '/' + arg if arg else '/sd'
                    try:
                        os.listdir(new_dir)
                        self.current_dir = new_dir
                        self.send_response(client, 250, "Directory changed")
                    except:
                        self.send_response(client, 550, "Directory not found")
                
                elif cmd == 'LIST' or cmd == 'NLST':
                    self.send_response(client, 150, "Opening data connection")
                    try:
                        items = os.listdir(self.current_dir)
                        file_list = ''
                        for item in items:
                            file_list += item + '\r\n'
                        
                        data_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        data_client.connect((addr[0], 20))
                        data_client.send(file_list.encode('utf-8'))
                        data_client.close()
                        
                        self.send_response(client, 226, "Transfer complete")
                    except Exception as e:
                        self.send_response(client, 425, "Data connection failed: " + str(e))
                
                elif cmd == 'RETR':
                    filepath = self.current_dir + '/' + arg
                    self.send_response(client, 150, "Opening data connection")
                    try:
                        with open(filepath, 'rb') as f:
                            data = f.read()
                        
                        data_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        data_client.connect((addr[0], 20))
                        data_client.send(data)
                        data_client.close()
                        
                        self.send_response(client, 226, "Transfer complete")
                    except Exception as e:
                        self.send_response(client, 550, "File not found: " + str(e))
                
                elif cmd == 'STOR':
                    filepath = self.current_dir + '/' + arg
                    self.send_response(client, 150, "Opening data connection")
                    try:
                        data_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        data_client.settimeout(10)
                        data_client.bind(('0.0.0.0', 20))
                        data_client.listen(1)
                        
                        conn, _ = data_client.accept()
                        file_data = b''
                        while True:
                            chunk = conn.recv(BUFFER_SIZE)
                            if not chunk:
                                break
                            file_data += chunk
                        
                        conn.close()
                        data_client.close()
                        
                        with open(filepath, 'wb') as f:
                            f.write(file_data)
                        
                        self.send_response(client, 226, "Transfer complete")
                    except Exception as e:
                        self.send_response(client, 425, "Data connection failed: " + str(e))
                
                elif cmd == 'DELE':
                    filepath = self.current_dir + '/' + arg
                    try:
                        os.remove(filepath)
                        self.send_response(client, 250, "File deleted")
                    except:
                        self.send_response(client, 550, "File not found")
                
                elif cmd == 'QUIT':
                    self.send_response(client, 221, "Goodbye")
                    break
                
                else:
                    self.send_response(client, 502, "Command not implemented")
            
            except socket.timeout:
                self.send_response(client, 421, "Timeout")
                break
            except Exception as e:
                print("Error:", e)
                break
        
        client.close()
        print("FTP client disconnected")

# === ЗАПУСК СЕРВЕРА ===
def start_ftp_server():
    mount_sd()
    
    ip = get_ip()
    
    clear()
    text("FTP Server", 60, 50, CYAN)
    text("Running...", 60, 90, GREEN)
    text("IP: " + ip, 50, 120, WHITE)
    text("Port: 21", 75, 140, WHITE)
    text("", 0, 160, WHITE)
    text("Use AndFTP or", 45, 170, YELLOW)
    text("CX File Explorer", 40, 185, YELLOW)
    text("", 0, 200, WHITE)
    text("Joy2BTN: Stop", 50, 210, WHITE)
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', FTP_PORT))
    server.listen(5)
    server.settimeout(1)
    
    print("FTP server started on port", FTP_PORT)
    
    ftp = FTPServer()
    
    while True:
        if joy2_btn.value() == 0:
            time.sleep_ms(300)
            if joy2_btn.value() == 0:
                break
        
        try:
            client, addr = server.accept()
            ftp.handle_client(client, addr)
        except socket.timeout:
            pass
        except Exception as e:
            print("Accept error:", e)
    
    server.close()
    print("FTP server stopped")

# === ЗАПУСК ===
print("FTP Server starting...")
start_ftp_server()
