import socket
import threading
import os
import datetime

# KONFIGURASI
TCP_HOST = '0.0.0.0'
TCP_PORT = 8000
UDP_HOST = '0.0.0.0'
UDP_PORT = 9000
BUFFER_SIZE = 4096
WEB_ROOT = os.path.dirname(os.path.abspath(__file__))  # direktori yang sama dengan webserver.py

# FUNGSI LOGGING
def log(message):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

# FUNGSI HELPER: MIME TYPE
def get_mime_type(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    mime_types = {
        '.html': 'text/html; charset=utf-8',
        '.css':  'text/css',
        '.js':   'application/javascript',
        '.png':  'image/png',
        '.jpg':  'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.ico':  'image/x-icon',
    }
    return mime_types.get(ext, 'application/octet-stream')

# FUNGSI HELPER: BUAT HTTP RESPONSE
def build_response(status_code, status_text, content_type, body):
    if isinstance(body, str):
        body = body.encode('utf-8')
    response  = f"HTTP/1.1 {status_code} {status_text}\r\n"
    response += f"Content-Type: {content_type}\r\n"
    response += f"Content-Length: {len(body)}\r\n"
    response += "Connection: close\r\n"
    response += "\r\n"
    return response.encode('utf-8') + body

# HANDLER: SATU CLIENT TCP
def handle_tcp_client(conn, addr):
    log(f"[TCP] Koneksi masuk dari {addr[0]}:{addr[1]}")
    try:
        request_data = b""
        while True:
            chunk = conn.recv(BUFFER_SIZE)
            if not chunk:
                break
            request_data += chunk
            if b"\r\n\r\n" in request_data:
                break

        if not request_data:
            conn.close()
            return

        # Parse HTTP request
        request_text = request_data.decode('utf-8', errors='ignore')
        lines = request_text.split('\r\n')
        request_line = lines[0]
        parts = request_line.split(' ')

        if len(parts) < 2:
            response = build_response(400, "Bad Request", "text/plain", "400 Bad Request")
            conn.sendall(response)
            conn.close()
            return

        method = parts[0]
        path   = parts[1]

        # Hanya handle GET
        if method != 'GET':
            response = build_response(405, "Method Not Allowed", "text/plain", "405 Method Not Allowed")
            conn.sendall(response)
            log(f"[TCP] {addr[0]} | {path} | 405 Method Not Allowed")
            conn.close()
            return

        # Kalau path '/', arahkan ke index.html
        if path == '/':
            path = '/index.html'

        # Cegah path traversal
        filepath = os.path.normpath(os.path.join(WEB_ROOT, path.lstrip('/')))
        if not filepath.startswith(WEB_ROOT):
            response = build_response(403, "Forbidden", "text/plain", "403 Forbidden")
            conn.sendall(response)
            log(f"[TCP] {addr[0]} | {path} | 403 Forbidden")
            conn.close()
            return

        # Cek apakah file ada
        if not os.path.isfile(filepath):
            body = f"<h1>404 Not Found</h1><p>File '{path}' tidak ditemukan.</p>"
            response = build_response(404, "Not Found", "text/html; charset=utf-8", body)
            conn.sendall(response)
            log(f"[TCP] {addr[0]} | {path} | 404 Not Found")
            conn.close()
            return

        # Baca file dan kirim
        try:
            with open(filepath, 'rb') as f:
                file_content = f.read()
            mime = get_mime_type(filepath)
            response = build_response(200, "OK", mime, file_content)
            conn.sendall(response)
            log(f"[TCP] {addr[0]} | {path} | 200 OK | {len(file_content)} bytes")
        except Exception as e:
            body = f"<h1>500 Internal Server Error</h1><p>{str(e)}</p>"
            response = build_response(500, "Internal Server Error", "text/html; charset=utf-8", body)
            conn.sendall(response)
            log(f"[TCP] {addr[0]} | {path} | 500 Internal Server Error | {e}")

    except Exception as e:
        log(f"[TCP] Error menangani {addr}: {e}")
    finally:
        conn.close()

# SERVER TCP (HTTP)
def start_tcp_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((TCP_HOST, TCP_PORT))
    server.listen(10)
    log(f"[TCP] HTTP Server berjalan di port {TCP_PORT}")

    while True:
        try:
            conn, addr = server.accept()
            thread = threading.Thread(target=handle_tcp_client, args=(conn, addr), daemon=True)
            thread.start()
            log(f"[TCP] Thread baru dibuat untuk {addr[0]}:{addr[1]} | Thread aktif: {threading.active_count()-1}")
        except Exception as e:
            log(f"[TCP] Error accept: {e}")

# SERVER UDP (QoS ECHO)
def start_udp_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((UDP_HOST, UDP_PORT))
    log(f"[UDP] Echo Server berjalan di port {UDP_PORT}")

    while True:
        try:
            data, addr = server.recvfrom(BUFFER_SIZE)
            # Echo balik payload tanpa diubah
            server.sendto(data, addr)
            log(f"[UDP] Echo ke {addr[0]}:{addr[1]} | Payload: {data.decode('utf-8', errors='ignore')}")
        except Exception as e:
            log(f"[UDP] Error: {e}")

# MAIN
if __name__ == '__main__':
    log("=" * 50)
    log("  WEB SERVER - Jaringan Komputer Tubes")
    log("=" * 50)
    log(f"  Web Root : {WEB_ROOT}")
    log(f"  TCP Port : {TCP_PORT}")
    log(f"  UDP Port : {UDP_PORT}")
    log("=" * 50)

    # Jalankan TCP dan UDP di thread terpisah
    tcp_thread = threading.Thread(target=start_tcp_server, daemon=True)
    udp_thread = threading.Thread(target=start_udp_server, daemon=True)

    tcp_thread.start()
    udp_thread.start()

    log("Server running on port 8000/9000")
    log("Tekan Ctrl+C untuk menghentikan server.")

    try:
        tcp_thread.join()
        udp_thread.join()
    except KeyboardInterrupt:
        log("Server dihentikan.")