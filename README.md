# Page Pulse ⚡

## Live Demo
▶️ https://page-pulse-0c4o.onrender.com/

## Quick start
1. Open the URL.
2. Paste any website URL into the input box and click **Audit**.
3. Review the report (status, response time, SEO, accessibility, etc.).


A lightweight web-page auditing tool that instantly analyses any URL and returns actionable insights on HTTP performance, SEO, and accessibility.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

| Metric                  | Description                                               |
|-------------------------|-----------------------------------------------------------|
| **HTTP Status**         | The status code returned by the target server              |
| **Response Time**       | Round-trip latency in milliseconds                         |
| **Page Title**          | Content of the `<title>` tag                               |
| **Meta Description**    | Content of `<meta name="description">`                     |
| **H1 Count**            | Number of `<h1>` elements (SEO best-practice: exactly 1)   |
| **Images Missing Alt**  | `<img>` tags without a meaningful `alt` attribute          |
| **Word Count**          | Approximate visible-text word count (excludes script/style) |

---

## 🚀 Setup

### Prerequisites

- Python 3.10+ (3.12 recommended)
- pip

### Install & Run

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/page-pulse.git
cd page-pulse

# 2. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\Scripts\activate      # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the dev server
uvicorn backend.main:app --reload --port 8000
```

Open **http://localhost:8000** in your browser.

### Run with Docker

```bash
docker build -t page-pulse .
docker run -p 8000:10000 page-pulse
```

---

## 📡 API Contract

### `POST /api/audit`

Audit a single URL.

#### Request

```json
{
  "url": "https://example.com"
}
```

| Field | Type   | Required | Notes                                       |
|-------|--------|----------|---------------------------------------------|
| `url` | string | ✅       | Scheme optional — defaults to `https://`     |

#### Success Response — `200 OK`

```json
{
  "url": "https://example.com",
  "http_status": 200,
  "response_time_ms": 342.17,
  "page_title": "Example Domain",
  "meta_description": "This domain is for use in illustrative examples.",
  "h1_count": 1,
  "images_missing_alt": ["/hero.jpg"],
  "images_missing_alt_count": 1,
  "word_count": 58,
  "is_html": true
}
```

#### Error Responses

| Status | `error` field      | When                                    |
|--------|--------------------|-----------------------------------------|
| 400    | `invalid_url`      | URL is empty, malformed, or bad scheme  |
| 415    | `not_html`         | Response Content-Type is not `text/html`|
| 502    | `connection_error` | DNS failure or refused connection        |
| 504    | `timeout`          | No response within 15 seconds            |

Error body:

```json
{
  "error": "invalid_url",
  "detail": "URL must not be empty.",
  "url": null
}
```

### `GET /api/health`

Health check endpoint.

```json
{ "status": "ok" }
```

---

## 🧪 Running Tests

```bash
pytest tests/ -v
```

The test suite covers:

- **Happy path**: mocked HTML page → correct report fields.
- **Invalid URL**: empty / bogus input → `invalid_url` error.
- **Timeout**: simulated read timeout → `timeout` error.
- **Non-HTML**: image content type → `not_html` error.
- **Connection error**: DNS failure → `connection_error` error.
- **Individual helpers**: title extraction, meta description, H1 count, images missing alt, word count.

---

## 🏗️ Design Decisions

### 1. Separation of parsing logic from the web framework

The `auditor.py` module contains all URL validation and HTML parsing logic and is completely independent of FastAPI. `main.py` is a thin routing layer that delegates to `auditor.py`.

**Why**: This makes the core logic trivially testable with plain `pytest` — no need to boot an ASGI server in tests. It also means the parsing engine could be reused in a CLI tool, a queue worker, or any other context without change.

### 2. Async HTTP client (httpx) with explicit timeouts

We use `httpx.AsyncClient` with a 15-second timeout rather than the synchronous `requests` library.

**Why**: FastAPI runs on an async event loop. Using a synchronous HTTP client would block the entire loop while waiting for a response, meaning a single slow target site could stall every other request. `httpx` with `async/await` lets the server handle many concurrent audits without thread-pool exhaustion. The explicit timeout prevents runaway requests from hanging indefinitely.

### 3. Returning structured error objects instead of raising HTTP exceptions

When an audit fails (bad URL, timeout, non-HTML), we return an `AuditError` dataclass from the business layer. The route handler maps the error type to the appropriate HTTP status code.

**Why**: Raising `HTTPException` inside business logic would couple it to FastAPI. By returning a result-or-error union, the logic stays framework-agnostic, the test suite can assert on plain Python objects, and the API contract is explicit — every possible outcome is documented in the response schema.

---

## 📁 Project Structure

```
page-pulse/
├── backend/
│   ├── __init__.py
│   ├── main.py          # FastAPI routes, CORS, static serving
│   └── auditor.py       # URL validation, HTML parsing, audit logic
├── static/
│   └── index.html       # Frontend (Tailwind CSS)
├── tests/
│   ├── __init__.py
│   └── test_auditor.py  # pytest suite
├── .github/
│   └── workflows/
│       └── ci.yml       # GitHub Actions CI
├── Dockerfile
├── render.yaml          # Render deployment config
├── requirements.txt
└── README.md
```

---

## 🌐 Live Demo

🔗 ▶️ https://page-pulse-0c4o.onrender.com/

---

## 📜 License

MIT

---

<p align="center">
  <a href="https://digitalheroesco.com" target="_blank">Built for Digital Heroes Training Task</a>
</p>
