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
