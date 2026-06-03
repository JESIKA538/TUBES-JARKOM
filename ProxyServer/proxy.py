import socket
import threading
import os
import datetime

# KONFIGURASI
PROXY_HOST = '0.0.0.0'
PROXY_PORT = 8080

# Alamat Web Server - GANTI sesuai IP Laptop A
WEB_SERVER_HOST = '127.0.0.1'
WEB_SERVER_TCP_PORT = 8000

BUFFER_SIZE = 4096
TIMEOUT = 5  # detik

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')

# Lock untuk mencegah race condition saat akses cache
cache_lock = threading.Lock()

# FUNGSI LOGGING
def log(message):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

# FUNGSI CACHE
def get_cache_path(url_path):
    """Konversi URL path ke nama file cache."""
    # Bersihkan karakter yang tidak valid untuk nama file
    safe_name = url_path.replace('/', '_').replace('\\', '_')
    if safe_name.startswith('_'):
        safe_name = safe_name[1:]
    if safe_name == '':
        safe_name = 'index.html'
    return os.path.join(CACHE_DIR, safe_name)

def is_cached(url_path):
    """Cek apakah URL sudah ada di cache."""
    cache_path = get_cache_path(url_path)
    return os.path.isfile(cache_path)

def read_cache(url_path):
    """Baca response dari cache."""
    cache_path = get_cache_path(url_path)
    with open(cache_path, 'rb') as f:
        return f.read()

def write_cache(url_path, data):
    """Tulis response ke cache (thread-safe)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = get_cache_path(url_path)
    with cache_lock:
        with open(cache_path, 'wb') as f:
            f.write(data)

# FUNGSI FORWARD KE WEB SERVER
def forward_to_server(request_data):
    """Teruskan request ke Web Server dan ambil response-nya."""
    try:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.settimeout(TIMEOUT)
        server_sock.connect((WEB_SERVER_HOST, WEB_SERVER_TCP_PORT))
        server_sock.sendall(request_data)

        # Terima response lengkap
        response = b""
        while True:
            chunk = server_sock.recv(BUFFER_SIZE)
            if not chunk:
                break
            response += chunk

        server_sock.close()
        return response, None

    except socket.timeout:
        return None, 504
    except ConnectionRefusedError:
        return None, 502
    except Exception as e:
        log(f"[FORWARD] Error: {e}")
        return None, 502

# FUNGSI BUAT ERROR RESPONSE
def build_error_response(status_code, status_text):
    # Mengambil jalur folder status yang ada di direktori proxy server
    proxy_root = os.path.dirname(os.path.abspath(__file__))
    error_path = os.path.join(proxy_root, 'status', f'{status_code}.html')
    
    if os.path.isfile(error_path):
        # Membaca file eror secara dinamis (bisa 502.html atau 504.html tergantung error_code)
        with open(error_path, 'rb') as f:
            body = f.read()
    else:
        # Cadangan teks biasa jika file html dari dosen tidak ditemukan
        body = f"<h1>{status_code} {status_text}</h1>".encode('utf-8')
        
    response  = f"HTTP/1.1 {status_code} {status_text}\r\n"
    response += f"Content-Type: text/html; charset=utf-8\r\n"
    response += f"Content-Length: {len(body)}\r\n"
    response += "Connection: close\r\n"
    response += "\r\n" # Double CRLF pembatas standar HTTP
    
    return response.encode('utf-8') + body

# HANDLER: SATU CLIENT
def handle_client(conn, addr):
    start_time = datetime.datetime.now()
    log(f"[PROXY] Koneksi masuk dari {addr[0]}:{addr[1]}")

    try:
        # Terima request dari client
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

        # Parse request line
        request_text = request_data.decode('utf-8', errors='ignore')
        lines = request_text.split('\r\n')
        request_line = lines[0]
        parts = request_line.split(' ')

        if len(parts) < 2:
            conn.sendall(build_error_response(400, "Bad Request"))
            conn.close()
            return

        method = parts[0]
        url_path = parts[1]

        # Kalau path '/', arahkan ke index.html untuk keperluan cache key
        cache_key = url_path if url_path != '/' else '/index.html'

        log(f"[PROXY] {method} {url_path} dari {addr[0]}")

        # ─── CEK CACHE ───
        if is_cached(cache_key):
            # CACHE HIT
            cached_response = read_cache(cache_key)
            conn.sendall(cached_response)
            elapsed = (datetime.datetime.now() - start_time).total_seconds() * 1000
            log(f"[PROXY] CACHE HIT  | {addr[0]} | {url_path} | {elapsed:.2f}ms")

        else:
            # CACHE MISS — forward ke web server
            response, error_code = forward_to_server(request_data)

            if error_code == 504:
                conn.sendall(build_error_response(504, "Gateway Timeout"))
                log(f"[PROXY] 504 Gateway Timeout | {addr[0]} | {url_path}")

            elif error_code == 502 or response is None:
                conn.sendall(build_error_response(502, "Bad Gateway"))
                log(f"[PROXY] 502 Bad Gateway | {addr[0]} | {url_path}")

            else:
                # Simpan ke cache hanya jika response 200 OK
                if response.startswith(b"HTTP/1.1 200") or response.startswith(b"HTTP/1.0 200"):
                    write_cache(cache_key, response)

                conn.sendall(response)
                elapsed = (datetime.datetime.now() - start_time).total_seconds() * 1000
                log(f"[PROXY] CACHE MISS | {addr[0]} | {url_path} | {elapsed:.2f}ms")

    except Exception as e:
        log(f"[PROXY] Error menangani {addr}: {e}")
        try:
            conn.sendall(build_error_response(500, "Internal Server Error"))
        except:
            pass
    finally:
        conn.close()

# MAIN PROXY SERVER
def start_proxy():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((PROXY_HOST, PROXY_PORT))
    server.listen(10)
    log("=" * 50)
    log("  PROXY SERVER - Jaringan Komputer Tubes")
    log("=" * 50)
    log(f"  Proxy Port     : {PROXY_PORT}")
    log(f"  Web Server     : {WEB_SERVER_HOST}:{WEB_SERVER_TCP_PORT}")
    log(f"  Cache Dir      : {CACHE_DIR}")
    log("=" * 50)
    log(f"Proxy listening on port {PROXY_PORT}")
    log("Tekan Ctrl+C untuk menghentikan proxy.")

    while True:
        try:
            conn, addr = server.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thread.start()
            log(f"[PROXY] Thread baru untuk {addr[0]}:{addr[1]} | Thread aktif: {threading.active_count()-1}")
        except KeyboardInterrupt:
            log("Proxy dihentikan.")
            break
        except Exception as e:
            log(f"[PROXY] Error accept: {e}")

if __name__ == '__main__':
    start_proxy()