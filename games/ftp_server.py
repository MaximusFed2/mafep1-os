# ftp_server.py - Рабочий FTP сервер для ESP32
import machine, time, os, network, socket

# Настройки
FTP_PORT = 21

def get_ip():
    try:
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected(): return wlan.ifconfig()[0]
    except: pass
    try:
        ap = network.WLAN(network.AP_IF)
        if ap.active(): return ap.ifconfig()[0]
    except: pass
    return "192.168.4.1"

def start_ftp():
    ip = get_ip()
    print("Starting FTP on", ip)
    
    # Создаем сокет ПРАВИЛЬНО
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(('0.0.0.0', FTP_PORT))
    server_sock.listen(1)
    server_sock.settimeout(2)
    
    print("FTP Ready. Connect to", ip)
    
    while True:
        try:
            client, addr = server_sock.accept()
            print("Client connected:", addr)
            client.send(b'220 MaFeP1 FTP Ready\r\n')
            
            current_dir = '/sd'
            
            while True:
                try:
                    data = client.recv(256).decode('utf-8').strip()
                    if not data: break
                    
                    parts = data.split(' ', 1)
                    cmd = parts[0].upper()
                    arg = parts[1] if len(parts) > 1 else ''
                    
                    if cmd == 'USER' or cmd == 'PASS':
                        client.send(b'230 OK\r\n')
                    elif cmd == 'PWD':
                        client.send(('257 "' + current_dir + '"\r\n').encode())
                    elif cmd == 'LIST':
                        client.send(b'150 Opening\r\n')
                        items = '\r\n'.join(os.listdir(current_dir)) + '\r\n'
                        client.send(items.encode())
                        client.send(b'226 Done\r\n')
                    elif cmd == 'QUIT':
                        client.send(b'221 Bye\r\n')
                        break
                    else:
                        client.send(b'502 Not implemented\r\n')
                        
                except Exception as e:
                    print("Client error:", e)
                    break
            
            client.close()
            print("Client disconnected")
            
        except socket.timeout:
            pass
        except Exception as e:
            print("Server error:", e)

print("FTP Server starting...")
start_ftp()
