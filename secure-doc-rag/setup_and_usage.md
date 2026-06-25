# Setup and Usage Guide: Secure Document Query System

This guide walk you through setting up, configuring, running, and interacting with the Secure Document Query System (Secure Doc RAG).

---

## 1. Prerequisites
Before beginning, ensure you have the following installed on your machine:
- **Python 3.9** or higher
- **pip** (Python package installer)
- A **Google Gemini API Key** (Obtain one from [Google AI Studio](https://aistudio.google.com/))
- **cURL** (optional, for command-line API testing)

---

## 2. Setup Guide

### Step 2.1: Clone/Navigate to the Project Directory
Ensure you are in the project root directory:
```bash
cd secure-doc-rag
```

### Step 2.2: Create and Activate a Virtual Environment
It is highly recommended to isolate dependencies inside a virtual environment.

**On Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows (Command Prompt):**
```cmd
python -m venv venv
venv\Scripts\activate
```

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 2.3: Install Dependencies
Install all the required Python libraries listed in `requirements.txt`:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2.4: Environment Setup
Create a `.env` file in the root directory by copying the template from `.env.example`:
```bash
cp .env.exp .env
```

Open the newly created `.env` file and replace the placeholder API key with your actual Gemini API key:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

*Note: The remaining parameters can be left as default for local development.*

---

## 3. Running the Server

Start the FastAPI backend server using Uvicorn:
```bash
uvicorn main:app --reload
```

Once successfully started, you should see output similar to this:
```text
INFO:     Started server process [28452]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

You can verify that the server is active by navigating to `http://127.0.0.1:8000/health` in your browser. You should receive:
```json
{
  "status": "healthy"
}
```

---

## 4. API Usage Guide (Step-by-Step Testing)

Below are the commands to test the complete lifecycle of document uploading, querying, listing, and deletion using `curl`. 

Ensure you have a sample test document ready (e.g., `sample_policy.txt`, `info.pdf`). For testing PII masking, include fake sensitive information like:
> *"Our support team email is support@acme-corp.com and you can reach the lead architect at +1-555-019-2834. The database admin credentials are admin/super_secret_pwd_99."*

### Step 4.1: Upload and Index a Document
Upload a document for a specific customer (`customer_001`). This will mask the PII, partition the text, generate embeddings, and insert them into ChromaDB.

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/documents/upload" \
  -F "customer_id=customer_001" \
  -F "file=@/path/to/your/sample_policy.txt"
```

**Example Response:**
```json
{
  "customer_id": "customer_001",
  "filename": "sample_policy.txt",
  "chunks_stored": 2,
  "message": "Successfully indexed 2 chunks from 'sample_policy.txt'."
}
```

---

### Step 4.2: Query Documents (Semantic Search & Generation)
Ask a question about the document context for the specific customer. 

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "customer_001",
    "query": "How can I contact support and what is the database password?"
  }'
```

**Example Response:**
```json
{
  "customer_id": "customer_001",
  "query": "How can I contact support and what is the database password?",
  "answer": "You can contact support via email at [EMAIL] or by calling [PHONE]. The database password is [PASSWORD].",
  "sources": [
    "sample_policy.txt"
  ],
  "context_chunks_used": 2
}
```
*Notice how the sensitive information is automatically masked in the context and handled gracefully by the Gemini model!*

---

### Step 4.3: List Customer Documents
List all uploaded documents and verify the total chunk count for a customer.

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/documents/customer_001"
```

**Example Response:**
```json
{
  "customer_id": "customer_001",
  "documents": [
    "sample_policy.txt"
  ],
  "total_chunks": 2
}
```

---

### Step 4.4: Delete a Document
Remove a specific document from a customer's record (both vectors and local storage).

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/documents" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "customer_001",
    "filename": "sample_policy.txt"
  }'
```

**Example Response:**
```json
{
  "customer_id": "customer_001",
  "message": "Deleted 2 chunks for file 'sample_policy.txt'.",
  "deleted_chunks": 2
}
```

---

### Step 4.5: Purge All Customer Data
Delete all documents and the entire vector space associated with a customer.

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/documents" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "customer_001"
  }'
```

**Example Response:**
```json
{
  "customer_id": "customer_001",
  "message": "Deleted all 2 chunks for customer 'customer_001'.",
  "deleted_chunks": 2
}
```

---

## 5. Python Client Example

If you are developing a client application in Python to interact with the API, you can use the `requests` library as shown below:

```python
import requests

BASE_URL = "http://127.0.0.1:8000/api/v1"
CUSTOMER_ID = "cust_abc123"

# 1. Upload
upload_url = f"{BASE_URL}/documents/upload"
files = {"file": open("my_doc.txt", "rb")}
data = {"customer_id": CUSTOMER_ID}
r_upload = requests.post(upload_url, data=data, files=files)
print("Upload:", r_upload.json())

# 2. Query
query_url = f"{BASE_URL}/query"
query_payload = {
    "customer_id": CUSTOMER_ID,
    "query": "Summarize the document guidelines."
}
r_query = requests.post(query_url, json=query_payload)
print("Query Answer:", r_query.json()["answer"])

# 3. List Documents
list_url = f"{BASE_URL}/documents/{CUSTOMER_ID}"
r_list = requests.get(list_url)
print("Documents:", r_list.json())

# 4. Clean up (Delete)
delete_url = f"{BASE_URL}/documents"
delete_payload = {
    "customer_id": CUSTOMER_ID
}
r_delete = requests.delete(delete_url, json=delete_payload)
print("Delete Status:", r_delete.json())
```

---

## 6. Troubleshooting

* **Error: `415 Unsupported Media Type`**
  - Make sure the file extension is one of the supported types: `.pdf`, `.docx`, or `.txt`.
* **Error: `413 Request Entity Too Large`**
  - The default configuration limits uploads to 10 MB. Adjust `MAX_FILE_SIZE_MB` in your `.env` file if you need to ingest larger files.
* **Error: `500 Internal Server Error` (Failed to connect to API)**
  - Ensure that your `GEMINI_API_KEY` is correctly defined in your `.env` file and that you have an active internet connection.
* **Storage Location**:
  - Raw files are stored under `./data/uploads/{customer_id}/`.
  - Vectors are persisted in SQLite/Chroma binary format in `./data/chroma_db/`. You can safely clean up these directories to perform a hard reset.
