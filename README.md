# PyMicroHTTP

PyMicroHTTP is a lightweight, flexible HTTP framework built from scratch in Python. It provides a simple way to create HTTP services without heavy external dependencies, making it ideal for learning purposes or small projects.

## Features
for the original docs, see [here](https://github.com/hasssanezzz/pymicrohttp/blob/main/docs/README.md)

## Added Features

- HTTP request handling with routing
- WebSocket support
- SQLite database integration
- Static file serving
- Simple template engine
- Environment-based configuration
- CORS support
- Rate limiting
- Logging
- Graceful shutdown


## Requirements

- Python 3.7+
- Required packages: `websockets`, `python-dotenv`

## Installation

1. Clone this repository:
`git clone https://github.com/Ebrahim-Ramadan/simple-python-server.git`
`cd simple-python-server`

2. Install the required packages:
`pip install websockets python-dotenv`

3. Create a `.env` file in the project root and set your configuration:
```
DEBUG=True
HOST=localhost
PORT=9090
DB_NAME=example.db
LOG_FILE=server.log
STATIC_DIR=static
```

## Usage

1. Start the server:
   `python server.py`
2. The server will start on the specified host and port (default: localhost:9090).

3. Access the server:
- HTTP: `http://localhost:9090`
- WebSocket: `ws://localhost:9091`

## Adding Routes

Add new routes to the server by using the `@server.register` decorator:

`@server.register('GET /hello')
def hello(request):
return "Hello, World!"`
## Middleware
Apply middleware to your routes using decorators:
`
@server.register('GET /api/data')
@cors_middleware
@rate_limit_middleware
def get_data(request):
    return {"message": "This is some API data"}
    `
Static Files
Place your static files in the static directory. They will be served at /static/<filename>.

## Database Usage
Use the db object to interact with the SQLite database:

`
@server.register('GET /users')
def get_users(request):
    users = db.query("SELECT * FROM users")
    return {"users": users}
    `
## WebSocket
WebSocket functionality is available on a separate port (default: 9091). Implement your WebSocket logic in the WebSocketServer class.
Configuration
Modify the Config class or use environment variables to configure the server.
## Contributing
Contributions are welcome! Please feel free to submit a (Pull Request)[https://github.com/hasssanezzz/PyMicroHTTP/compare/main...Ebrahim-Ramadan:PyMicroHTTP-CORS-websocket-and-db-supported-and-more:main].
