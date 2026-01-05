# docs & Issue Attachments API Reference

## 📚 docs Module

### 1. Create Wiki Page

**Endpoint:** `POST /api/v1/projects/{project_id}/wiki`

**Request Body:**

```json
{
  "title": "Project Setup Guide",
  "content": "# Setup\n\n1. Install Python...",
  "parent_id": null 
  // OR "parent_id": "60d5ecb..." (for sub-pages)
}
```

**Response (200 OK):**

```json
{
  "id": "64f1a2b3c9e8...",
  "project_id": "64f1a2b3c9e8...",
  "title": "Project Setup Guide",
  "content": "# Setup\n\n1. Install Python...",
  "parent_id": null,
  "created_by": "64f1a2b3c9e8...",
  "created_at": "2023-09-01T10:00:00.000Z",
  "updated_at": "2023-09-01T10:00:00.000Z",
  "is_deleted": false
}
```

### 2. List Wiki Pages (Tree Structure)

**Endpoint:** `GET /api/v1/projects/{project_id}/wiki`

**Response (200 OK):**

```json
[
  {
    "id": "64f1a2...",
    "title": "Home",
    "children": [
      {
        "id": "64f1b3...",
        "title": "Setup",
        "children": []
      }
    ]
  }
]
```

### 3. Get Wiki Page Details

**Endpoint:** `GET /api/v1/projects/{project_id}/wiki/{page_id}`

**Response (200 OK):**

```json
{
  "id": "64f1a2...",
  "title": "Home",
  "content": "# Welcome...",
  "parent_id": null,
  "created_by": "...",
  "created_at": "...",
  "updated_at": "..."
}
```

### 4. Upload Wiki Asset (Image)

**Endpoint:** `POST /api/v1/projects/{project_id}/wiki/assets/upload`
**Content-Type:** `multipart/form-data`

**Request:**

* `file`: (Binary File)

**Response (200 OK):**

```json
{
  "id": "651a2b...",
  "project_id": "...",
  "filename": "20230901_image.png",
  "original_name": "image.png",
  "content_type": "image/png",
  "uploaded_by": "...",
  "created_at": "..."
}
```

*Usage: To view this image, use the ID in the 'Get Wiki Asset' endpoint below.*

### 5. Get/ Image Wiki Asset

**Endpoint:** `GET /api/v1/projects/{project_id}/wiki/assets/{asset_id}`

**Response:**

* Returns the raw file (image/pdf/etc) directly. Created for embedding in `<img>` tags.

---

## 📎 Issue Attachments Module

### 1. Upload Attachment

**Endpoint:** `POST /api/v1/issues/{issue_id}/attachments     #.png,.jpg # .pdf,.docx,.txt`
**Content-Type:** `multipart/form-data`

**Request:**

* `file`: (Binary File)

**Response (200 OK):**

```json
{
  "id": "652b3c...",
  "issue_id": "...",
  "project_id": "...",
  "name": "error_log.txt",
  "file_path": "uploads/issues/...",
  "file_type": ".txt",
  "content_type": "text/plain",
  "uploaded_by": "...",
  "uploaded_by_name": "John Doe",
  "created_at": "..."
}
```

### 2. List Attachments

**Endpoint:** `GET /api/v1/issues/{issue_id}/attachments`

**Response (200 OK):**

```json
[
  {
    "id": "652b3c...",
    "name": "error_log.txt",
    "uploaded_by_name": "John Doe",
    "created_at": "...",
    "content_type": "text/plain"
  },
  {
    "id": "652b3d...",
    "name": "screenshot.png",
    "uploaded_by_name": "Jane Doe",
    "created_at": "...",
    "content_type": "image/png"
  }
]
```

### 3. Download Attachment

**Endpoint:** `GET /api/v1/issues/{issue_id}/attachments/{attachment_id}/download`

**Response:**

* Triggers a file download of the specific attachment.

### 4. Delete Attachment

**Endpoint:** `DELETE /api/v1/issues/{issue_id}/attachments/{attachment_id}`

**Response (200 OK):**

```json
{
  "id": "652b3c...",
  "deleted": true
}
```
