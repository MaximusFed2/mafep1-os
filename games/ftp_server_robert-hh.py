# uftpd.py - Modified for MaFe P1 OS
# Small FTP server for ESP32 with display and joystick support
# Based on robert-hh's work

import socket
import network
import uos
import gc
import sys
import errno
from time import sleep_ms, localtime
from micropython import alloc_emergency_exception_buf
import machine

# === ДИСПЛЕЙ И КНОПКИ (для MaFe P1) ===
try:
    import st7789, vga1_16x16 as font16, vga1_8x8 as font8
    
    # Инициализация дисплея
    spi = machine.SPI(2, baudrate=40000000, polarity=1, phase=1,
                      sck=machine.Pin(12), mosi=machine.Pin(11), miso=machine.Pin(13))
    display = st7789.ST7789(spi, 240, 240,
                            dc=machine.Pin(4, machine.Pin.OUT),
                            reset=machine.Pin(5, machine.Pin.OUT), cs=None)
    
    # Кнопка выхода (Joy2BTN)
    joy2_btn = machine.Pin(15, machine.Pin.IN, machine.Pin.PULL_UP)
    
    HAS_DISPLAY = True
except:
    HAS_DISPLAY = False

# === ЦВЕТА ===
BLACK = 0x0000
WHITE = 0xFFFF
CYAN = 0x07FF
GREEN = 0x07E0
YELLOW = 0xFFE0
RED = 0xF800
DARK_GRAY = 0x3333

def clear():
    if HAS_DISPLAY:
        display.fill(BLACK)

def text(msg, x, y, color=WHITE, font=font16):
    if HAS_DISPLAY:
        display.text(font, msg, x, y, color)

def draw_status_bar(title):
    if HAS_DISPLAY:
        display.fill_rect(0, 0, 240, 25, DARK_GRAY)
        text(title, 5, 5, WHITE, font8)

# === КОНСТАНТЫ ===
_CHUNK_SIZE = const(1024)
_SO_REGISTER_HANDLER = const(20)
_COMMAND_TIMEOUT = const(300)
_DATA_TIMEOUT = const(100)
_DATA_PORT = const(13333)

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
ftpsockets = []
datasocket = None
client_list = []
verbose_l = 0
client_busy = False
server_running = False

_month_name = (" ", "Jan ", "Feb ", "Mar ", "Apr ", "May ", "Jun ",
               "Jul ", "Aug ", "Sep ", "Oct ", "Nov ", "Dec ")

class FTP_client:
    def __init__(self, ftpsocket, local_addr):
        self.command_client, self.remote_addr = ftpsocket.accept()
        self.remote_addr = self.remote_addr[0]
        self.command_client.settimeout(_COMMAND_TIMEOUT)
        log_msg(1, "FTP Command connection from:", self.remote_addr)
        self.command_client.setsockopt(socket.SOL_SOCKET,
                                       _SO_REGISTER_HANDLER,
                                       self.exec_ftp_command)
        self.command_client.sendall("220 Hello, MaFe P1 FTP Server\r\n")
        self.cwd = '/'
        self.fromname = None
        self.logged_in = False
        self.act_data_addr = self.remote_addr
        self.DATA_PORT = 20
        self.active = True
        self.pasv_data_addr = local_addr

    def send_list_data(self, path, data_client, full):
        try:
            for fname in uos.listdir(path):
                data_client.sendall(self.make_description(path, fname, full))
        except Exception as e:
            path, pattern = self.split_path(path)
            try:
                for fname in uos.listdir(path):
                    if self.fncmp(fname, pattern):
                        data_client.sendall(
                            self.make_description(path, fname, full))
            except:
                pass

    def make_description(self, path, fname, full):
        global _month_name
        if full:
            stat = uos.stat(self.get_absolute_path(path, fname))
            file_permissions = ("drwxr-xr-x"
                                if (stat[0] & 0o170000 == 0o040000)
                                else "-rw-r--r--")
            file_size = stat[6]
            tm = stat[7] & 0xffffffff
            tm = localtime(tm if tm < 0x80000000 else tm - 0x100000000)
            if tm[0] != localtime()[0]:
                description = "{} 1 owner group {:>10} {} {:2} {:>5} {}\r\n".\
                    format(file_permissions, file_size,
                        _month_name[tm[1]], tm[2], tm[0], fname)
            else:
                description = "{} 1 owner group {:>10} {} {:2} {:02}:{:02} {}\r\n".\
                    format(file_permissions, file_size,
                        _month_name[tm[1]], tm[2], tm[3], tm[4], fname)
        else:
            description = fname + "\r\n"
        return description

    def send_file_data(self, path, data_client):
        buffer = bytearray(_CHUNK_SIZE)
        mv = memoryview(buffer)
        with open(path, "rb") as file:
            bytes_read = file.readinto(buffer)
            while bytes_read > 0:
                data_client.write(mv[0:bytes_read])
                bytes_read = file.readinto(buffer)
            data_client.close()

    def save_file_data(self, path, data_client, mode):
        buffer = bytearray(_CHUNK_SIZE)
        mv = memoryview(buffer)
        with open(path, mode) as file:
            bytes_read = data_client.readinto(buffer)
            while bytes_read > 0:
                file.write(mv[0:bytes_read])
                bytes_read = data_client.readinto(buffer)
            data_client.close()

    def get_absolute_path(self, cwd, payload):
        if payload.startswith('/'):
            cwd = "/"
        for token in payload.split("/"):
            if token == '..':
                cwd = self.split_path(cwd)[0]
            elif token != '.' and token != '':
                if cwd == '/':
                    cwd += token
                else:
                    cwd = cwd + '/' + token
        return cwd

    def split_path(self, path):
        tail = path.split('/')[-1]
        head = path[:-(len(tail) + 1)]
        return ('/' if head == '' else head, tail)

    def fncmp(self, fname, pattern):
        pi = 0
        si = 0
        while pi < len(pattern) and si < len(fname):
            if (fname[si] == pattern[pi]) or (pattern[pi] == '?'):
                si += 1
                pi += 1
            else:
                if pattern[pi] == '*':
                    if pi == len(pattern.rstrip("*?")):
                        return True
                    while si < len(fname):
                        if self.fncmp(fname[si:], pattern[pi + 1:]):
                            return True
                        else:
                            si += 1
                    return False
                else:
                    return False
        if pi == len(pattern.rstrip("*")) and si == len(fname):
            return True
        else:
            return False

    def open_dataclient(self):
        if self.active:
            data_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            data_client.settimeout(_DATA_TIMEOUT)
            data_client.connect((self.act_data_addr, self.DATA_PORT))
            log_msg(1, "FTP Data connection with:", self.act_data_addr)
        else:
            data_client, data_addr = datasocket.accept()
            log_msg(1, "FTP Data connection with:", data_addr[0])
        return data_client

    def exec_ftp_command(self, cl):
        global datasocket
        global client_busy
        global my_ip_addr
        try:
            gc.collect()
            try:
                data = cl.readline().decode("utf-8").rstrip("\r\n")
            except OSError:
                data = ""
            if len(data) <= 0:
                log_msg(1, "*** No data, assume QUIT")
                close_client(cl)
                return
            if client_busy:
                cl.sendall("400 Device busy.\r\n")
                return
            client_busy = True
            command = data.split()[0].upper()
            payload = data[len(command):].lstrip()
            path = self.get_absolute_path(self.cwd, payload)
            log_msg(1, "Command={}, Payload={}".format(command, payload))
            
            if command == "USER":
                cl.sendall("230 Logged in.\r\n")
            elif command == "PASS":
                cl.sendall("230 Logged in.\r\n")
            elif command == "SYST":
                cl.sendall("215 UNIX Type: L8\r\n")
            elif command in ("TYPE", "NOOP", "ABOR"):
                cl.sendall('200 OK\r\n')
            elif command == "QUIT":
                cl.sendall('221 Bye.\r\n')
                close_client(cl)
            elif command == "PWD" or command == "XPWD":
                cl.sendall('257 "{}"\r\n'.format(self.cwd))
            elif command == "CWD" or command == "XCWD":
                try:
                    if (uos.stat(path)[0] & 0o170000) == 0o040000:
                        self.cwd = path
                        cl.sendall('250 OK\r\n')
                    else:
                        cl.sendall('550 Fail\r\n')
                except:
                    cl.sendall('550 Fail\r\n')
            elif command == "PASV":
                cl.sendall('227 Entering Passive Mode ({},{},{}).\r\n'.format(
                    self.pasv_data_addr.replace('.', ','),
                    _DATA_PORT >> 8, _DATA_PORT % 256))
                self.active = False
            elif command == "PORT":
                items = payload.split(",")
                if len(items) >= 6:
                    self.act_data_addr = '.'.join(items[:4])
                    if self.act_data_addr == "127.0.1.1":
                        self.act_data_addr = self.remote_addr
                    self.DATA_PORT = int(items[4]) * 256 + int(items[5])
                    cl.sendall('200 OK\r\n')
                    self.active = True
                else:
                    cl.sendall('504 Fail\r\n')
            elif command == "LIST" or command == "NLST":
                if payload.startswith("-"):
                    option = payload.split()[0].lower()
                    path = self.get_absolute_path(
                            self.cwd, payload[len(option):].lstrip())
                else:
                    option = ""
                try:
                    data_client = self.open_dataclient()
                    cl.sendall("150 Directory listing:\r\n")
                    self.send_list_data(path, data_client,
                                        command == "LIST" or 'l' in option)
                    cl.sendall("226 Done.\r\n")
                    data_client.close()
                except:
                    cl.sendall('550 Fail\r\n')
                    if data_client is not None:
                        data_client.close()
            elif command == "RETR":
                try:
                    data_client = self.open_dataclient()
                    cl.sendall("150 Opened data connection.\r\n")
                    self.send_file_data(path, data_client)
                    data_client = None
                    cl.sendall("226 Done.\r\n")
                except:
                    cl.sendall('550 Fail\r\n')
                    if data_client is not None:
                        data_client.close()
            elif command == "STOR" or command == "APPE":
                try:
                    data_client = self.open_dataclient()
                    cl.sendall("150 Opened data connection.\r\n")
                    self.save_file_data(path, data_client,
                                        "wb" if command == "STOR" else "ab")
                    data_client = None
                    cl.sendall("226 Done.\r\n")
                except:
                    cl.sendall('550 Fail\r\n')
                    if data_client is not None:
                        data_client.close()
            elif command == "SIZE":
                try:
                    cl.sendall('213 {}\r\n'.format(uos.stat(path)[6]))
                except:
                    cl.sendall('550 Fail\r\n')
            elif command == "MDTM":
                try:
                    tm=localtime(uos.stat(path)[8])
                    cl.sendall('213 {:04d}{:02d}{:02d}{:02d}{:02d}{:02d}\r\n'.format(*tm[0:6]))
                except:
                    cl.sendall('550 Fail\r\n')
            elif command == "STAT":
                if payload == "":
                    cl.sendall("211-Connected to ({})\r\n"
                               "    Data address ({})\r\n"
                               "    TYPE: Binary STRU: File MODE: Stream\r\n"
                               "    Session timeout {}\r\n"
                               "211 Client count is {}\r\n".format(
                                self.remote_addr, self.pasv_data_addr,
                                _COMMAND_TIMEOUT, len(client_list)))
                else:
                    cl.sendall("213-Directory listing:\r\n")
                    self.send_list_data(path, cl, True)
                    cl.sendall("213 Done.\r\n")
            elif command == "DELE":
                try:
                    uos.remove(path)
                    cl.sendall('250 OK\r\n')
                except:
                    cl.sendall('550 Fail\r\n')
            elif command == "RNFR":
                try:
                    uos.stat(path)
                    self.fromname = path
                    cl.sendall("350 Rename from\r\n")
                except:
                    cl.sendall('550 Fail\r\n')
            elif command == "RNTO":
                    try:
                        uos.rename(self.fromname, path)
                        cl.sendall('250 OK\r\n')
                    except:
                        cl.sendall('550 Fail\r\n')
                    self.fromname = None
            elif command == "CDUP" or command == "XCUP":
                self.cwd = self.get_absolute_path(self.cwd, "..")
                cl.sendall('250 OK\r\n')
            elif command == "RMD" or command == "XRMD":
                try:
                    uos.rmdir(path)
                    cl.sendall('250 OK\r\n')
                except:
                    cl.sendall('550 Fail\r\n')
            elif command == "MKD" or command == "XMKD":
                try:
                    uos.mkdir(path)
                    cl.sendall('250 OK\r\n')
                except:
                    cl.sendall('550 Fail\r\n')
            elif command == "SITE":
                try:
                    exec(payload.replace('\0','\n'))
                    cl.sendall('250 OK\r\n')
                except:
                    cl.sendall('550 Fail\r\n')
            else:
                cl.sendall("502 Unsupported command.\r\n")
        except OSError as err:
            if verbose_l > 0:
                log_msg(1, "Exception in exec_ftp_command:")
                sys.print_exception(err)
            if err.errno in (errno.ECONNABORTED, errno.ENOTCONN):
                close_client(cl)
        except Exception as err:
            log_msg(1, "Exception in exec_ftp_command: {}".format(err))
        client_busy = False

def log_msg(level, *args):
    global verbose_l
    if verbose_l >= level:
        print(*args)

def close_client(cl):
    cl.setsockopt(socket.SOL_SOCKET, _SO_REGISTER_HANDLER, None)
    cl.close()
    for i, client in enumerate(client_list):
        if client.command_client == cl:
            del client_list[i]
            break

def accept_ftp_connect(ftpsocket, local_addr):
    try:
        client_list.append(FTP_client(ftpsocket, local_addr))
    except:
        log_msg(1, "Attempt to connect failed")
        try:
            temp_client, temp_addr = ftpsocket.accept()
            temp_client.close()
        except:
            pass

def num_ip(ip):
    items = ip.split(".")
    return (int(items[0]) << 24 | int(items[1]) << 16 |
            int(items[2]) << 8 | int(items[3]))

def stop():
    global ftpsockets, datasocket
    global client_list
    global client_busy
    global server_running
    
    for client in client_list:
        client.command_client.setsockopt(socket.SOL_SOCKET,
                                         _SO_REGISTER_HANDLER, None)
        client.command_client.close()
    del client_list
    client_list = []
    client_busy = False
    for sock in ftpsockets:
        sock.setsockopt(socket.SOL_SOCKET, _SO_REGISTER_HANDLER, None)
        sock.close()
    ftpsockets = []
    if datasocket is not None:
        datasocket.close()
        datasocket = None
    server_running = False

def start(port=21, verbose=0, splash=True):
    global ftpsockets, datasocket
    global verbose_l
    global client_list
    global client_busy
    global server_running
    
    alloc_emergency_exception_buf(100)
    verbose_l = verbose
    client_list = []
    client_busy = False
    server_running = True
    
    # Показываем интерфейс на экране
    if HAS_DISPLAY:
        clear()
        draw_status_bar("FTP Server")
    
    for interface in [network.AP_IF, network.STA_IF]:
        wlan = network.WLAN(interface)
        if not wlan.active():
            continue
        ifconfig = wlan.ifconfig()
        addr = socket.getaddrinfo(ifconfig[0], port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(addr[0][4])
        sock.listen(1)
        sock.setsockopt(socket.SOL_SOCKET,
                        _SO_REGISTER_HANDLER,
                        lambda s : accept_ftp_connect(s, ifconfig[0]))
        ftpsockets.append(sock)
        if splash:
            print("FTP server started on {}:{}".format(ifconfig[0], port))
            # Показываем IP на экране
            if HAS_DISPLAY:
                text("IP: " + ifconfig[0], 10, 50, GREEN, font16)
                text("Port: " + str(port), 10, 70, WHITE, font8)
    
    datasocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    datasocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    datasocket.bind(('0.0.0.0', _DATA_PORT))
    datasocket.listen(1)
    datasocket.settimeout(10)
    
    if HAS_DISPLAY:
        text("Joy2BTN: Stop", 10, 100, YELLOW, font8)
        text("Waiting...", 10, 120, CYAN, font8)

def restart(port=21, verbose=0, splash=True):
    stop()
    sleep_ms(200)
    start(port, verbose, splash)

# === ЗАПУСК СЕРВЕРА С ИНТЕРФЕЙСОМ ===
def run_ftp_server():
    """Запускает FTP сервер с проверкой кнопки выхода"""
    print("Starting FTP server for MaFe P1...")
    start(port=21, verbose=0, splash=True)
    
    # Главный цикл с проверкой кнопки
    while server_running:
        sleep_ms(100)
        
        # Проверяем кнопку Joy2BTN
        if HAS_DISPLAY and joy2_btn.value() == 0:
            print("Stopping FTP server (button pressed)...")
            stop()
            break

# Автозапуск при импорте
if __name__ == '__main__':
    run_ftp_server()
