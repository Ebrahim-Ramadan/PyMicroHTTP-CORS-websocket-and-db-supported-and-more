import re
import socket
import threading
import json
import logging
import os
import mimetypes
import sqlite3
import time
import signal
import asyncio
import websockets
from http.client import responses
from functools import wraps
from collections import defaultdict
from string import Template
from dotenv import load_dotenv
from urllib.parse import parse_qsl

# Load environment variables
load_dotenv()

# Configuration
class Config:
    DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')
    HOST = os.getenv('HOST', 'localhost')
    PORT = int(os.getenv('PORT', 9090))
    DB_NAME = os.getenv('DB_NAME', 'example.db')
    LOG_FILE = os.getenv('LOG_FILE', 'server.log')
    STATIC_DIR = os.getenv('STATIC_DIR', 'static')

config = Config()

# Set up logging
logging.basicConfig(filename=config.LOG_FILE, level=logging.INFO)

# Database
class Database:
    def __init__(self, db_name):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()

    def query(self, sql, params=()):
        self.cursor.execute(sql, params)
        return self.cursor.fetchall()

    def execute(self, sql, params=()):
        self.cursor.execute(sql, params)
        self.conn.commit()

    def close(self):
        self.conn.close()

db = Database(config.DB_NAME)

# Simple Template Engine
class SimpleTemplate:
    def __init__(self, template):
        self.template = Template(template)

    def render(self, **kwargs):
        return self.template.substitute(kwargs)

# Rate Limiter
class RateLimiter:
    def __init__(self, limit=100, window=60):
        self.limit = limit
        self.window = window
        self.requests = defaultdict(list)

    def is_allowed(self, client_ip):
        now = time.time()
        self.requests[client_ip] = [t for t in self.requests[client_ip] if now - t < self.window]
        if len(self.requests[client_ip]) < self.limit:
            self.requests[client_ip].append(now)
            return True
        return False

rate_limiter = RateLimiter()

# WebSocket Server
class WebSocketServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port

    async def handler(self, websocket, path):
        try:
            async for message in websocket:
                await websocket.send(f"Echo: {message}")
        except websockets.exceptions.ConnectionClosed:
            pass

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        start_server = websockets.serve(self.handler, self.host, self.port)
        loop.run_until_complete(start_server)
        loop.run_forever()

# Main Server Class
class Server:
    routes = {}
    beforeAllMiddlewares = []

    def __init__(self, host=config.HOST, port=config.PORT):
        self.host = host
        self.port = port

    def start_server(self):
        ws_server = WebSocketServer(self.host, self.port + 1)
        threading.Thread(target=ws_server.run, daemon=True).start()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.bind((self.host, self.port))
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.listen()
            print(f'Server listening on {self.host}:{self.port}')
            while True:
                try:
                    conn, addr = server_socket.accept()
                    print(f'Connected by {addr}')
                    threading.Thread(target=self.__handleConnection, args=(conn, addr)).start()
                except GracefulExit:
                    print("\nShutting down gracefully...")
                    break

    def registerHandler(self, path: str, handler):
        if not self.__isPathValid(path):
            raise ValueError('invalid provided path:', path)
        self.routes[path] = handler

    def register(self, path, middleware=None):
        if not self.__isPathValid(path):
            raise ValueError('invalid provided path:', path)  
                  
        def decorator(func):
            @wraps(func)
            def wrapper(request):
                try:
                    return func(request)
                except Exception as e:
                    logging.error(f"Error in {func.__name__}: {str(e)}")
                    return f"Internal Server Error: {str(e)}", 500

            if middleware:
                if isinstance(middleware, list):
                    self.routes[path] = self.__chainMiddlewares(middleware, wrapper)
                else:
                    self.routes[path] = middleware(wrapper)
            else:
                self.routes[path] = wrapper
                
        return decorator
    
    def beforeAll(self):
        def decorator(func):
            self.beforeAllMiddlewares.append(func)
        return decorator

    def static(self, url_path, file_path):
        @self.register(f'GET {url_path}')
        def static_handler(request):
            return serve_static(file_path)

    def __handleConnection(self, conn: socket.socket, addr):
        with conn:
            while True:
                data = conn.recv(1024 * 2)
                if not data:
                    break

                reqstr = data.rstrip(b'\x00').decode()
                parsed = self.__parseRequest(reqstr)
                parsed['client_ip'] = addr[0]
                parsed['parsed_body'] = parse_body(parsed)
                pathkey = f'{parsed["verb"]} {parsed["path"]}'

                if pathkey in self.routes:
                    handler = self.routes[pathkey]
                    
                    if self.beforeAllMiddlewares:
                        chainedHandler = self.__chainMiddlewares(self.beforeAllMiddlewares, handler)
                        result = chainedHandler(parsed)
                    else:
                        result = handler(parsed)
                    
                    if not isinstance(result, tuple):
                        return conn.sendall(self.__writeReponse(self.__checkIfResultIsDict(result)))
                    resultLen = len(result)
                    if resultLen == 3:
                        response, code, headers = result
                        return conn.sendall(self.__writeReponse(self.__checkIfResultIsDict(response), code, headers))
                    if resultLen == 2:
                        response, code = result
                        return conn.sendall(self.__writeReponse(self.__checkIfResultIsDict(response), code))
                    conn.sendall(self.__writeReponse('', 500))
                    raise ValueError('internal server error: handler returned bad number of values:', resultLen)
                return conn.sendall(self.__writeReponse('', 404))

    def __checkIfResultIsDict(self, result):
        if isinstance(result, dict):
            return json.dumps(result)
        return result

    def __writeReponse(self, resp, code=200, headers={}, contentType='application/json'):
        resp = str(resp)
        codeMessage = responses.get(code, 'Unknown')
        httpResp = (
            f'HTTP/1.1 {code} {codeMessage}\r\n'
            f'Content-Type: {contentType}\r\n'
            f'Content-Length: {len(resp)}\r\n'
        )

        for header, value in headers.items():
            header, value = str(header), str(value)
            httpResp += f'{header}: {value}\r\n'

        return (httpResp + (
            '\r\n'
            f'{resp}'
        )).encode()

    def __parseRequest(self, reqstr: str):
        sep = '\r\n'
        head, body = reqstr.split(sep + sep)
        headlines = head.split(sep)
        head = headlines[0]
        headlines = headlines[1:]
        verb, path, _ = head.split(' ')
        headers = {}
        for line in headlines:
            idx = line.index(':')
            header, value = line[:idx], line[idx+2:]
            headers[header] = value

        return {
            'verb': verb,
            'path': path,
            'headers': headers,
            'body': body
        }

    def __isPathValid(self, path: str) -> bool:
        pattern = r'^(GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH) /[^\s]*$'
        return bool(re.match(pattern, path))

    def __chainMiddlewares(self, middlewares, func):
        for middleware in reversed(middlewares):
            func = middleware(func)
        return func

# Helper functions
def serve_static(path):
    full_path = os.path.join(config.STATIC_DIR, path)
    if os.path.exists(full_path):
        with open(full_path, 'rb') as file:
            content = file.read()
        content_type, _ = mimetypes.guess_type(full_path)
        return content, 200, {'Content-Type': content_type or 'application/octet-stream'}
    return 'File not found', 404

def parse_body(request):
    content_type = request['headers'].get('Content-Type', '')
    if 'application/json' in content_type:
        return json.loads(request['body'])
    elif 'application/x-www-form-urlencoded' in content_type:
        return dict(parse_qsl(request['body']))
    return request['body']

# Middleware
def cors_middleware(f):
    @wraps(f)
    def wrapper(request):
        response = f(request)
        headers = response[2] if len(response) == 3 else {}
        headers.update({
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
        })
        return response[0], response[1], headers
    return wrapper

def rate_limit_middleware(f):
    @wraps(f)
    def wrapper(request):
        client_ip = request['client_ip']
        if rate_limiter.is_allowed(client_ip):
            return f(request)
        return "Rate limit exceeded", 429
    return wrapper

# Graceful exit handling
class GracefulExit(Exception):
    pass

def signal_handler(signum, frame):
    raise GracefulExit()

signal.signal(signal.SIGINT, signal_handler)

# Server instance
server = Server()

# Example routes
# @server.register('GET /')
# def home(request):
#     return "Welcome to the server!"

# @server.register('GET /api/data')
# @cors_middleware
# @rate_limit_middleware
# def get_data(request):
#     return {"message": "This is some API data"}

# # Static file serving
# @server.register('GET /static/<path:path>')
# def serve_static_file(request):
#     path = request['path'].split('/static/')[1]
#     return serve_static(path)

if __name__ == "__main__":
    server.start_server()