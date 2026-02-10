from flask import Flask, request, make_response
import time
from datetime import datetime




app = Flask(__name__)
PORT = 3000

# ============================================
# "MIDDLEWARE" 1: Logger Middleware (GLOBAL)
# Runs for EVERY request that comes in
# ============================================
@app.before_request
def logger_middleware():
    timestamp = datetime.utcnow().isoformat()
    print(f"[{timestamp}] {request.method} request to {request.path}")


# ============================================
# "MIDDLEWARE" 2: Request Time Middleware (GLOBAL)
# Stores request start time so routes can compute processing time
# ============================================
@app.before_request
def request_time_middleware():
    # Store start time for this request (seconds since epoch, float)
    request.request_time = time.time()
    print("Request time recorded:", request.request_time)


# ============================================
# "MIDDLEWARE" 3: Auth Check Middleware (ROUTE-SPECIFIC)
# Implemented as a decorator in Flask
# ============================================
def auth_check_middleware(view_func):
    def wrapper(*args, **kwargs):
        secret_key = request.args.get("key")

        if secret_key == "abc123":
            print("User is authorized!")
            # Flask doesn't have req.isAuthorized, but we can attach it
            request.is_authorized = True
            return view_func(*args, **kwargs)

        print("User is NOT authorized!")
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Access Denied</title>
            <style>
                body { font-family: Arial; text-align: center; padding: 50px; background: #ffebee; }
                h1 { color: #c62828; }
                p { color: #555; }
            </style>
        </head>
        <body>
            <h1>🚫 Access Denied</h1>
            <p>You need the correct key to enter this page.</p>
            <p>Try adding <code>?key=abc123</code> to the URL</p>
        </body>
        </html>
        """
        resp = make_response(html, 401)
        return resp

    # Keep the original function name (nice for debugging)
    wrapper.__name__ = view_func.__name__
    return wrapper


# ============================================
# ROUTES
# ============================================

@app.get("/")
def home():
    # processing time in ms
    processing_time_ms = int((time.time() - request.request_time) * 1000)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Middleware Demo</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background: #e3f2fd;
            }}
            h1 {{ color: #1565c0; }}
            .card {{
                background: white;
                padding: 20px;
                margin: 15px 0;
                border-radius: 8px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
            code {{
                background: #f5f5f5;
                padding: 2px 8px;
                border-radius: 4px;
            }}
            a {{ color: #1565c0; }}
        </style>
    </head>
    <body>
        <h1>🚀 Welcome to Middleware Demo</h1>

        <div class="card">
            <h2>What is Middleware?</h2>
            <p>Middleware is code that runs BETWEEN the request and response.</p>
            <p>Think of it like security checkpoints at an airport!</p>
        </div>

        <div class="card">
            <h2>Middlewares Used on This Page:</h2>
            <ol>
                <li><strong>Logger Middleware</strong> - Records every request</li>
                <li><strong>Request Time Middleware</strong> - Tracks when request started</li>
            </ol>
            <p>Processing time: <code>{processing_time_ms}ms</code></p>
        </div>

        <div class="card">
            <h2>Try These Links:</h2>
            <ul>
                <li><a href="/about">About Page</a> - Uses global middleware</li>
                <li><a href="/admin">Admin Page (No Key)</a> - Will be blocked!</li>
                <li><a href="/admin?key=abc123">Admin Page (With Key)</a> - Will work!</li>
            </ul>
        </div>
    </body>
    </html>
    """


@app.get("/about")
def about():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>About Page</title>
        <style>
            body {
                font-family: Arial;
                text-align: center;
                padding: 50px;
                background: #e8f5e9;
            }
            h1 { color: #2e7d32; }
        </style>
    </head>
    <body>
        <h1>📖 About Page</h1>
        <p>This page used 2 middlewares before showing.</p>
        <p>Check your console to see the logs!</p>
        <p><a href="/">Go Back Home</a></p>
    </body>
    </html>
    """


@app.get("/admin")
@auth_check_middleware
def admin():
    # This value gets set by the middleware when authorized
    is_authorized = getattr(request, "is_authorized", False)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel</title>
        <style>
            body {{
                font-family: Arial;
                text-align: center;
                padding: 50px;
                background: #fff3e0;
            }}
            h1 {{ color: #e65100; }}
            .success {{
                background: #c8e6c9;
                padding: 20px;
                border-radius: 8px;
                display: inline-block;
            }}
        </style>
    </head>
    <body>
        <h1>🔐 Admin Panel</h1>
        <div class="success">
            <p>✅ You passed the auth middleware!</p>
            <p>Authorization Status: {is_authorized}</p>
        </div>
        <p><a href="/">Go Back Home</a></p>
    </body>
    </html>
    """


# ============================================
# START SERVER
# ============================================
if __name__ == "__main__":
    print("=" * 50)
    print("Middleware Demo Server is Running!")
    print(f"Open browser: http://localhost:{PORT}")
    print("=" * 50)
    app.run(host="127.0.0.1", port=PORT, debug=True)