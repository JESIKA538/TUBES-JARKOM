import socket
import time
import datetime
import argparse
import statistics

# KONFIGURASI
# Alamat Proxy - GANTI sesuai IP Laptop B
PROXY_HOST = '127.0.0.1'
PROXY_PORT = 8080

# Alamat Web Server (untuk UDP) - GANTI sesuai IP Laptop A
UDP_SERVER_HOST = '127.0.0.1'
UDP_SERVER_PORT = 9000

BUFFER_SIZE = 4096
UDP_TIMEOUT  = 1      # detik timeout per paket UDP
UDP_COUNT    = 10     # jumlah paket UDP yang dikirim

# LOGGING
def log(message):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")


# MODE TCP — HTTP CLIENT
def http_request(path='/'):
    """Kirim HTTP GET request ke Proxy dan tampilkan response."""
    print("\n" + "=" * 55)
    print(f"  HTTP REQUEST: GET {path}")
    print(f"  Proxy: {PROXY_HOST}:{PROXY_PORT}")
    print("=" * 55)

    try:
        # Buat koneksi TCP ke Proxy
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.settimeout(10)
        client_sock.connect((PROXY_HOST, PROXY_PORT))

        # Buat HTTP GET request
        request  = f"GET {path} HTTP/1.1\r\n"
        request += f"Host: {PROXY_HOST}\r\n"
        request += "Connection: close\r\n"
        request += "\r\n"

        start_time = time.time()
        client_sock.sendall(request.encode('utf-8'))
        log(f"Request terkirim: GET {path}")

        # Terima response
        response = b""
        while True:
            chunk = client_sock.recv(BUFFER_SIZE)
            if not chunk:
                break
            response += chunk

        elapsed = (time.time() - start_time) * 1000
        client_sock.close()

        # Pisahkan header dan body
        if b"\r\n\r\n" in response:
            header_part, body_part = response.split(b"\r\n\r\n", 1)
            headers = header_part.decode('utf-8', errors='ignore')
            status_line = headers.split('\r\n')[0]
        else:
            headers = response.decode('utf-8', errors='ignore')
            body_part = b""
            status_line = "Unknown"

        print(f"\n--- RESPONSE ---")
        print(f"Status  : {status_line}")
        print(f"Waktu   : {elapsed:.2f} ms")
        print(f"Ukuran  : {len(response)} bytes")
        print(f"\n--- HEADERS ---")
        print(headers)
        print(f"\n--- BODY (200 karakter pertama) ---")
        print(body_part.decode('utf-8', errors='ignore')[:200])
        print("=" * 55)

    except socket.timeout:
        log(f"[TCP] Timeout - Proxy tidak merespons dalam 10 detik")
    except ConnectionRefusedError:
        log(f"[TCP] Koneksi ditolak - Pastikan Proxy berjalan di {PROXY_HOST}:{PROXY_PORT}")
    except Exception as e:
        log(f"[TCP] Error: {e}")


# MODE TCP — MULTIPLE REQUESTS
def http_multi_request(paths):
    """Kirim beberapa HTTP GET request sekaligus."""
    print("\n" + "=" * 55)
    print(f"  MULTI HTTP REQUEST ({len(paths)} request)")
    print("=" * 55)
    for path in paths:
        http_request(path)

# MODE UDP — QoS PINGER
def udp_ping(count=UDP_COUNT, target_host=UDP_SERVER_HOST, target_port=UDP_SERVER_PORT):
    """Kirim paket UDP dan ukur RTT, packet loss, jitter."""
    print("\n" + "=" * 55)
    print(f"  UDP QoS PING")
    print(f"  Target : {target_host}:{target_port}")
    print(f"  Jumlah : {count} paket")
    print(f"  Timeout: {UDP_TIMEOUT} detik/paket")
    print("=" * 55)

    rtt_list     = []
    lost         = 0
    total_bytes  = 0
    start_session = time.time()

    client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_sock.settimeout(UDP_TIMEOUT)

    for seq in range(1, count + 1):
        timestamp = time.time()
        payload   = f"Ping {seq} {timestamp}"
        data      = payload.encode('utf-8')

        try:
            send_time = time.time()
            client_sock.sendto(data, (target_host, target_port))

            echo_data, _ = client_sock.recvfrom(BUFFER_SIZE)
            recv_time = time.time()

            rtt = (recv_time - send_time) * 1000  # ms
            rtt_list.append(rtt)
            total_bytes += len(echo_data)

            print(f"  Paket {seq:>3}: RTT = {rtt:.3f} ms | {echo_data.decode('utf-8', errors='ignore')}")

        except socket.timeout:
            lost += 1
            print(f"  Paket {seq:>3}: Request timed out")

        # Jeda kecil antar paket
        time.sleep(0.1)

    client_sock.close()
    session_duration = time.time() - start_session

    # ─── HITUNG STATISTIK ───
    print("\n" + "=" * 55)
    print("  STATISTIK QoS")
    print("=" * 55)

    if rtt_list:
        rtt_min = min(rtt_list)
        rtt_avg = statistics.mean(rtt_list)
        rtt_max = max(rtt_list)

        # Jitter = deviasi standar selisih RTT berturut-turut
        if len(rtt_list) >= 2:
            rtt_diffs = [abs(rtt_list[i] - rtt_list[i-1]) for i in range(1, len(rtt_list))]
            jitter = statistics.stdev(rtt_diffs) if len(rtt_diffs) > 1 else 0.0
        else:
            jitter = 0.0

        packet_loss = (lost / count) * 100
        throughput  = (total_bytes * 8) / (session_duration * 1000) if session_duration > 0 else 0  # kbps

        print(f"  Paket dikirim    : {count}")
        print(f"  Paket diterima   : {count - lost}")
        print(f"  Paket hilang     : {lost} ({packet_loss:.1f}%)")
        print(f"  RTT Min          : {rtt_min:.3f} ms")
        print(f"  RTT Avg          : {rtt_avg:.3f} ms")
        print(f"  RTT Max          : {rtt_max:.3f} ms")
        print(f"  Jitter           : {jitter:.3f} ms")
        print(f"  Throughput       : {throughput:.2f} kbps")
        print(f"  Durasi sesi      : {session_duration:.2f} detik")
    else:
        print("  Semua paket hilang! Cek koneksi ke server.")
        packet_loss = 100.0
        print(f"  Packet Loss      : {packet_loss:.1f}%")

    print("=" * 55)

# MENU INTERAKTIF
def interactive_menu():
    print("\n" + "=" * 55)
    print("  CLIENT - Jaringan Komputer Tubes")
    print(f"  Proxy  : {PROXY_HOST}:{PROXY_PORT}")
    print(f"  Server : {UDP_SERVER_HOST}:{UDP_SERVER_PORT} (UDP)")
    print("=" * 55)
    print("  [1] HTTP Request ke Proxy (TCP)")
    print("  [2] UDP QoS Ping ke Server")
    print("  [3] Multi HTTP Request (beberapa path)")
    print("  [0] Keluar")
    print("=" * 55)

    while True:
        pilihan = input("\nPilih mode [0-3]: ").strip()

        if pilihan == '1':
            path = input("Masukkan path (contoh: /index.html): ").strip()
            if not path:
                path = '/'
            http_request(path)

        elif pilihan == '2':
            try:
                count = input(f"Jumlah paket UDP (default {UDP_COUNT}): ").strip()
                count = int(count) if count else UDP_COUNT
            except ValueError:
                count = UDP_COUNT
            udp_ping(count=count)

        elif pilihan == '3':
            print("Masukkan path satu per satu, ketik 'done' jika selesai:")
            paths = []
            while True:
                p = input("  Path: ").strip()
                if p.lower() == 'done':
                    break
                if p:
                    paths.append(p)
            if paths:
                http_multi_request(paths)
            else:
                print("Tidak ada path yang dimasukkan.")

        elif pilihan == '0':
            print("Client dihentikan.")
            break
        else:
            print("Pilihan tidak valid.")


# ARGUMENT PARSER (untuk mode CLI langsung)
def parse_args():
    parser = argparse.ArgumentParser(description='Client Jarkom Tubes')
    parser.add_argument('--mode', choices=['tcp', 'udp', 'menu'], default='menu',
                        help='Mode: tcp, udp, atau menu (default: menu)')
    parser.add_argument('--path', default='/', help='Path HTTP untuk mode tcp (default: /)')
    parser.add_argument('--count', type=int, default=UDP_COUNT,
                        help=f'Jumlah paket UDP (default: {UDP_COUNT})')
    return parser.parse_args()

# MAIN
if __name__ == '__main__':
    args = parse_args()

    if args.mode == 'tcp':
        http_request(args.path)
    elif args.mode == 'udp':
        udp_ping(count=args.count)
    else:
        interactive_menu()