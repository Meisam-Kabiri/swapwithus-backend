# Messaging Media Implementation Guide

## Overview

The messaging system now supports images and videos using **Firebase Cloud Storage**. Media files are uploaded directly from the frontend to Firebase Storage, then the URL is sent to the backend API.

## Architecture

```
┌─────────────┐
│  Frontend   │
└──────┬──────┘
       │
       ├──── 1. Upload media ────────► Firebase Storage
       │                               /conversations/{conversationId}/{filename}
       │                               [Validated by storage.rules]
       │
       ├──── 2. Get download URL ────► Firebase Storage
       │
       ├──── 3. Send message ────────► Backend API
       │     {text?, mediaUrl, mediaType}
       │                               [Backend validates Firebase URL]
       │
       └──── 4. Listen to messages ──► Firestore (real-time)
                                       {text?, mediaUrl?, mediaType?}
```

## Backend Changes

### 1. Updated Models (`app/models/message.py`)

#### `CreateConversationRequest`
```python
{
  "recipientUid": "string",
  "requesterListingId": "string?",
  "recipientListingId": "string?",
  "initialMessage": "string",
  "mediaUrl": "string?",        # NEW - Firebase Storage URL
  "mediaType": "image|video?"   # NEW - Type of media
}
```

#### `SendMessageRequest`
```python
{
  "text": "string?",              # Optional (but text OR media required)
  "mediaUrl": "string?",          # NEW - Firebase Storage URL
  "mediaType": "image|video?"     # NEW - Type of media
}
```

**Validation:**
- At least `text` OR `mediaUrl` must be provided
- If `mediaUrl` provided, `mediaType` is required
- `mediaUrl` must start with `https://firebasestorage.googleapis.com/`

### 2. Updated API Responses

#### `GET /api/messaging/conversations/{conversationId}/messages`
```json
{
  "messages": [
    {
      "messageId": "string",
      "senderUid": "string",
      "receiverUid": "string",
      "text": "string?",
      "mediaUrl": "string?",      // NEW
      "mediaType": "image|video?", // NEW
      "createdAt": "timestamp",
      "isRead": "boolean",
      "readAt": "timestamp?"
    }
  ]
}
```

#### Conversation List Preview
When a message contains media, the `lastMessage` field shows:
- `"📷 Image"` for images
- `"🎥 Video"` for videos
- Text content if text is provided

## Frontend Implementation

### Step 1: Setup Firebase Storage

```typescript
import { getStorage, ref, uploadBytes, getDownloadURL } from 'firebase/storage';

const storage = getStorage();
```

### Step 2: Upload Media Function

```typescript
async function uploadMessageMedia(
  conversationId: string,
  file: File
): Promise<{ mediaUrl: string; mediaType: 'image' | 'video' }> {

  // Validate file type
  const isImage = file.type.startsWith('image/');
  const isVideo = file.type.startsWith('video/');

  if (!isImage && !isVideo) {
    throw new Error('Only images and videos are allowed');
  }

  // Validate size
  const maxSize = isImage ? 10 * 1024 * 1024 : 20 * 1024 * 1024; // 10MB/20MB
  if (file.size > maxSize) {
    throw new Error(`File too large (max ${maxSize / 1024 / 1024}MB)`);
  }

  // Generate unique filename
  const timestamp = Date.now();
  const randomId = Math.random().toString(36).substring(7);
  const extension = file.name.split('.').pop();
  const filename = `${timestamp}_${randomId}.${extension}`;

  // Upload to Firebase Storage
  const storageRef = ref(storage, `conversations/${conversationId}/${filename}`);
  await uploadBytes(storageRef, file);

  // Get download URL
  const mediaUrl = await getDownloadURL(storageRef);

  return {
    mediaUrl,
    mediaType: isImage ? 'image' : 'video'
  };
}
```

### Step 3: Send Message with Media

```typescript
async function sendMessageWithMedia(
  conversationId: string,
  text?: string,
  file?: File
) {
  let mediaUrl: string | undefined;
  let mediaType: 'image' | 'video' | undefined;

  // Upload media if provided
  if (file) {
    const result = await uploadMessageMedia(conversationId, file);
    mediaUrl = result.mediaUrl;
    mediaType = result.mediaType;
  }

  // Send message to backend
  const response = await fetch(
    `${API_BASE_URL}/api/messaging/conversations/${conversationId}/messages`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({
        text,
        mediaUrl,
        mediaType
      })
    }
  );

  if (!response.ok) {
    throw new Error('Failed to send message');
  }

  return response.json();
}
```

### Step 4: Create Conversation with Media

```typescript
async function createConversationWithMedia(
  recipientUid: string,
  initialMessage: string,
  file?: File,
  requesterListingId?: string,
  recipientListingId?: string
) {
  let mediaUrl: string | undefined;
  let mediaType: 'image' | 'video' | undefined;

  // For new conversations, we need a temporary conversationId
  // Option 1: Create conversation first without media, then send media
  // Option 2: Use a temporary ID based on participants (sorted UIDs)

  const tempConvId = [currentUserUid, recipientUid].sort().join('_');

  if (file) {
    const result = await uploadMessageMedia(tempConvId, file);
    mediaUrl = result.mediaUrl;
    mediaType = result.mediaType;
  }

  const response = await fetch(`${API_BASE_URL}/api/messaging/conversations`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${idToken}`
    },
    body: JSON.stringify({
      recipientUid,
      requesterListingId,
      recipientListingId,
      initialMessage,
      mediaUrl,
      mediaType
    })
  });

  return response.json();
}
```

### Step 5: Display Messages in UI

```tsx
function MessageBubble({ message }: { message: Message }) {
  return (
    <div className={`message ${message.senderUid === currentUserUid ? 'sent' : 'received'}`}>

      {/* Show media if present */}
      {message.mediaUrl && message.mediaType === 'image' && (
        <img
          src={message.mediaUrl}
          alt="Shared image"
          className="message-image"
          loading="lazy"
        />
      )}

      {message.mediaUrl && message.mediaType === 'video' && (
        <video
          src={message.mediaUrl}
          controls
          className="message-video"
        />
      )}

      {/* Show text if present */}
      {message.text && <p>{message.text}</p>}

      <span className="timestamp">
        {formatTimestamp(message.createdAt)}
      </span>
    </div>
  );
}
```

## Security

### Firebase Storage Rules (Already Configured)

Your `storage.rules` already handle this correctly:

```javascript
// conversations/{conversationId}/{fileName}
match /conversations/{conversationId}/{fileName} {

  // Read: Only participants
  allow read: if isParticipantInConversation(conversationId);

  // Upload: Only participants + valid file type + size limits
  allow write: if isParticipantInConversation(conversationId) &&
                  (isValidImage() || isValidVideo()) &&
                  isValidSize();
}
```

**File Limits:**
- Images: max 10MB, types: jpeg, jpg, png, gif, webp
- Videos: max 20MB, types: mp4, quicktime, x-m4v, webm

### Backend Validation

The backend validates:
1. ✅ User authentication (Firebase token)
2. ✅ User is participant in conversation
3. ✅ `mediaUrl` is from Firebase Storage (not external URLs)
4. ✅ Either `text` or `media` is provided
5. ✅ Rate limiting (20 messages/minute)

## Example: Complete Message Flow

```typescript
// 1. User selects a file
const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
  const file = event.target.files?.[0];
  if (!file) return;

  try {
    // Show loading indicator
    setUploading(true);

    // Upload and send
    await sendMessageWithMedia(conversationId, messageText, file);

    // Clear input
    setMessageText('');
    event.target.value = '';
  } catch (error) {
    console.error('Failed to send media:', error);
    alert('Failed to send media');
  } finally {
    setUploading(false);
  }
};

// 2. Message form with file input
<form onSubmit={handleSubmit}>
  <input
    type="text"
    value={messageText}
    onChange={(e) => setMessageText(e.target.value)}
    placeholder="Type a message..."
  />

  <input
    type="file"
    accept="image/*,video/*"
    onChange={handleFileSelect}
    style={{ display: 'none' }}
    ref={fileInputRef}
  />

  <button type="button" onClick={() => fileInputRef.current?.click()}>
    📎 Attach
  </button>

  <button type="submit" disabled={!messageText && !selectedFile}>
    Send
  </button>
</form>
```

## Testing

### Test Image Upload
```bash
# 1. Upload image to Firebase Storage
# 2. Send message with mediaUrl
curl -X POST https://your-api.com/api/messaging/conversations/{id}/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Check this out!",
    "mediaUrl": "https://firebasestorage.googleapis.com/...",
    "mediaType": "image"
  }'
```

### Test Video Upload
```bash
curl -X POST https://your-api.com/api/messaging/conversations/{id}/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "mediaUrl": "https://firebasestorage.googleapis.com/...",
    "mediaType": "video"
  }'
```

## Notes

1. **No Backend Upload Endpoint**: Media uploads go directly to Firebase Storage, not through the backend
2. **URL Validation**: Backend only accepts Firebase Storage URLs for security
3. **Text is Optional**: Messages can be media-only (no text required)
4. **Last Message Preview**: Conversations show emoji previews (📷/🎥) when last message is media
5. **Real-time Updates**: Firestore listeners automatically receive media messages
6. **Storage Costs**: Firebase Storage has free tier (5GB), then pay-as-you-go

## Migration Notes

If you have existing conversations:
- Old messages without media will continue to work (backward compatible)
- Only new messages can include media
- No database migration needed

## Future Enhancements

- [ ] Image compression before upload (frontend)
- [ ] Video thumbnails
- [ ] Progress indicators for uploads
- [ ] Image/video galleries
- [ ] Delete media functionality
- [ ] Media preview before sending
