# User Files API (Chatbot Attachments)

This document describes the **User Files** API: upload, list, metadata, download, and delete of user-uploaded files (e.g. attachments for a chatbot). Files are stored in MinIO and metadata in MongoDB.

---

## Overview

- **Purpose:** Let users attach files (text, documents) from the UI; other services can download and use them (e.g. parse, summarize) via the API.
- **Storage:** MinIO path `user-files/{user_id}/{file_id}/{filename}`. Each upload gets a unique `file_id` (MongoDB ObjectId string).
- **Allowed types:** `.txt`, `.md`, `.csv`, `.json`, `.xml`, `.pdf`, `.doc`, `.docx`, `.odt`, `.rtf`.
- **Max file size:** 20 MB per file.

---

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| **POST** | `/user-files/upload/{user_id}` | Upload a file. Multipart: `file` (required), optional `name`, `description`, `project_id`. |
| **GET** | `/user-files/{user_id}` | List files for a user. Query: `project_id`, `skip`, `limit`. |
| **GET** | `/user-files/{user_id}/{file_id}` | Get metadata for one file. |
| **GET** | `/user-files/{user_id}/{file_id}/download` | Download file (for other services: parse, summarize, etc.). |
| **DELETE** | `/user-files/{user_id}/{file_id}` | Delete file (from UI or API). |

---

## 1. Upload

**Request**

```http
POST /user-files/upload/{user_id}
Content-Type: multipart/form-data

Form fields:
  file       (required)  – The file to upload
  name       (optional)  – Display name
  description (optional) – Description
  project_id (optional)  – Project or conversation ID
```

**Example (curl)**

```bash
curl -X POST "http://localhost:8000/user-files/upload/user1" \
  -F "file=@document.txt" \
  -F "name=My notes" \
  -F "description=Chatbot context" \
  -F "project_id=conv-123"
```

**Response (200)**

```json
{
  "file_id": "507f1f77bcf86cd799439011",
  "user_id": "user1",
  "name": "My notes",
  "description": "Chatbot context",
  "project_id": "conv-123",
  "original_filename": "document.txt",
  "content_type": "text/plain",
  "size_bytes": 1024,
  "created_at": "2025-02-10T12:00:00Z"
}
```

Use `file_id` for subsequent get/download/delete.

**Errors**

- **400** – Missing filename, disallowed file type, or file too large (> 20 MB).
- **500** – Storage or server error.

---

## 2. List files

**Request**

```http
GET /user-files/{user_id}?project_id=conv-123&skip=0&limit=100
```

| Query | Type | Description |
|-------|------|-------------|
| `project_id` | string | Optional. Filter by project/conversation. |
| `skip` | int | Default 0. Pagination offset. |
| `limit` | int | Default 100, max 500. Page size. |

**Response (200)**

```json
{
  "files": [
    {
      "file_id": "507f1f77bcf86cd799439011",
      "user_id": "user1",
      "name": "My notes",
      "description": "Chatbot context",
      "project_id": "conv-123",
      "original_filename": "document.txt",
      "content_type": "text/plain",
      "size_bytes": 1024,
      "created_at": "2025-02-10T12:00:00Z"
    }
  ],
  "total": 1
}
```

---

## 3. Get metadata

**Request**

```http
GET /user-files/{user_id}/{file_id}
```

**Response (200)** – Same shape as one entry in the list above.

**Errors**

- **404** – File not found or not owned by `user_id`.

---

## 4. Download

**Request**

```http
GET /user-files/{user_id}/{file_id}/download
```

**Response (200)** – Binary body with file content; `Content-Type` and `Content-Disposition` set so the file can be saved or processed (e.g. parse, summarize) by other services.

**Errors**

- **404** – File not found or not owned by `user_id`.

**Example (curl, save to file)**

```bash
curl -o downloaded.txt "http://localhost:8000/user-files/user1/507f1f77bcf86cd799439011/download"
```

---

## 5. Delete

**Request**

```http
DELETE /user-files/{user_id}/{file_id}
```

**Response (200)**

```json
{
  "message": "File deleted",
  "file_id": "507f1f77bcf86cd799439011"
}
```

**Errors**

- **404** – File not found or not owned by `user_id`.

---

## Allowed file types and limits

- **Extensions:** `.txt`, `.md`, `.csv`, `.json`, `.xml`, `.pdf`, `.doc`, `.docx`, `.odt`, `.rtf`
- **Max size:** 20 MB per file

Defined in `app/models/user_file.py` (`ALLOWED_EXTENSIONS`, `MAX_FILE_SIZE_BYTES`). To support more types or a larger limit, change those constants and redeploy.

---

## Integration notes

- **Chatbot UI:** Upload via `POST /user-files/upload/{user_id}` with optional `project_id`; list with `GET /user-files/{user_id}?project_id=...`; delete when the user removes an attachment.
- **Downstream services:** Use `GET /user-files/{user_id}/{file_id}/download` to fetch the file for parsing, summarization, or other processing. Identify files by `file_id` returned at upload or from the list endpoint.

---

*Last updated: February 2025*
