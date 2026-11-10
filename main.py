from datetime import datetime
import json
import logging
import mimetypes
from multiprocessing import Process
import os
from pathlib import Path
import socket
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pymongo import MongoClient

HTTP_PORT = 3000
SOCKET_PORT = 5000
SOCKET_HOST = '127.0.0.1'
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://mongodb:27017')
MONGO_DB = 'messages_db'
MONGO_COLLECTION = 'messages'

BASE_DIR = Path(__file__).resolve().parent / 'front'


class HTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        pr_path = urllib.parse.urlparse(self.path).path
        if pr_path in ['/', '/index.html']:
            self.render_template('index.html')
        elif pr_path in ['/message', '/message.html']:
            self.render_template('message.html')
        else:
            file_path = BASE_DIR / pr_path.lstrip('/')
            if file_path.exists() and file_path.is_file():
                self.send_static(file_path)
            else:
                self.render_template('error.html', status=404)

    def do_POST(self):
        pr_path = urllib.parse.urlparse(self.path).path
        if pr_path in ['/message', '/message.html']:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')

            send_data_to_socket(post_data)

            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
        else:
            self.render_template('error.html', status=404)

    def render_template(self, filename, status=200):
        file_path = BASE_DIR / filename
        if file_path.exists():
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            with open(file_path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'File Not Found')

    def send_static(self, file_path):
        self.send_response(200)
        mt, _ = mimetypes.guess_type(file_path)
        if mt:
            self.send_header('Content-Type', mt)
        else:
            self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        with open(file_path, 'rb') as f:
            self.wfile.write(f.read())


def send_data_to_socket(data):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(data.encode('utf-8'), (SOCKET_HOST, SOCKET_PORT))
    sock.close()


def run_socket_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', SOCKET_PORT))
    logging.info(f"Socket server listening on port {SOCKET_PORT}")

    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]

    try:
        while True:
            data, _ = sock.recvfrom(1024)
            decoded_data = data.decode('utf-8')
            data_dict = dict(urllib.parse.parse_qsl(decoded_data))
            data_dict['date'] = str(datetime.now())
            collection.insert_one(data_dict)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


def run_http_server():
    server_address = ('0.0.0.0', HTTP_PORT)
    httpd = HTTPServer(server_address, HTTPHandler)
    logging.info(f"HTTP server running on port {HTTP_PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    socket_process = Process(target=run_socket_server)
    http_process = Process(target=run_http_server)

    socket_process.start()
    http_process.start()

    socket_process.join()
    http_process.join()