# Swaps & Reviews System - Backend Implementation Complete

## Overview

Backend API implementation for the swaps and reviews system, following your exact coding style and structure from `users.py` and `listings.py`.

---

## Files Created

### **1. Models** (`app/models/swap.py`)

All models use your standard pattern:
- `ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)`
- `Annotated` with Field validators
- Python 3.10+ style with `|` for Optional types

**Models:**
- `SwapCreate` - Create new swap request
- `SwapUpdate` - Update swap status or cancellation reason
- `SwapResponse` - Swap data response
- `ReviewCreate` - Create new review
- `ReviewUpdate` - Update existing review
- `ReviewResponse` - Review data response
- `UserStatsResponse` - User rating and swap statistics

---

## API Endpoints

### **Swaps API** (`app/api/swaps.py`)

All endpoints follow your patterns:
- `extract_firebase_user_uid(request)` for auth
- `@limiter.limit()` decorators
- `get_pool().acquire()` for DB connections
- `JSONResponse` for responses
- Try/except with logging
- ISO string conversion for datetime fields

#### `POST /api/swaps`
Create new swap request
- **Auth:** Required (user_a)
- **Rate limit:** 20/hour
- **Body:** SwapCreate (user_b_uid, listing_a_id, listing_b_id, conversation_id?)
- **Returns:** Created swap with status='pending'
- **Validation:** Cannot swap with yourself

#### `GET /api/swaps`
Get all user's swaps
- **Auth:** Required
- **Rate limit:** 100/minute
- **Query params:** status? (pending/accepted/completed/cancelled)
- **Returns:** Array of swaps where user is participant
- **Sort:** Created date DESC

#### `GET /api/swaps/{swap_id}`
Get specific swap details
- **Auth:** Required
- **Rate limit:** 100/minute
- **Returns:** Swap data
- **Validation:** User must be participant

#### `PATCH /api/swaps/{swap_id}/accept`
Accept swap request
- **Auth:** Required (must be user_b)
- **Rate limit:** 20/hour
- **Action:** Updates status to 'accepted', sets accepted_at
- **Validation:** Only user_b can accept, status must be 'pending'

#### `PATCH /api/swaps/{swap_id}/decline`
Decline swap request
- **Auth:** Required (must be user_b)
- **Rate limit:** 20/hour
- **Body:** SwapUpdate (cancellation_reason?)
- **Action:** Updates status to 'cancelled', sets cancelled_at, cancelled_by
- **Validation:** Only user_b can decline, status must be 'pending'

#### `POST /api/swaps/{swap_id}/confirm-receipt`
Confirm item receipt (both users must confirm)
- **Auth:** Required (must be participant)
- **Rate limit:** 20/hour
- **Action:**
  - Sets user_a_confirmed or user_b_confirmed to true
  - If both confirmed: status='completed', completed_at=NOW()
  - Updates both users' total_swaps_completed and last_swap_at
- **Validation:** Status must be 'accepted', can't confirm twice
- **Transaction:** Uses FOR UPDATE lock for race condition safety

#### `PATCH /api/swaps/{swap_id}/cancel`
Cancel swap (either party can cancel)
- **Auth:** Required (must be participant)
- **Rate limit:** 20/hour
- **Body:** SwapUpdate (cancellation_reason?)
- **Action:** Updates status to 'cancelled', sets cancelled_at, cancelled_by
- **Validation:** Cannot cancel completed or already cancelled swaps

---

### **Reviews API** (`app/api/reviews.py`)

#### `POST /api/reviews`
Create review for completed swap
- **Auth:** Required
- **Rate limit:** 10/hour
- **Body:** ReviewCreate (swap_id, reviewee_uid, rating, communication_rating?, item_condition_rating?, timeliness_rating?, comment?)
- **Action:**
  - Inserts review
  - Updates reviewee's total_reviews, average_rating, trust_score
- **Validation:**
  - Swap must exist and be completed
  - Reviewer must be participant
  - Reviewee must be the other participant
  - Cannot review same swap twice
  - Cannot review yourself
- **Trust Score Formula:** `(AVG(rating) * 10 + COUNT(*))`

#### `GET /api/reviews/user/{user_uid}`
Get reviews for specific user (reviews they received)
- **Auth:** Required
- **Rate limit:** 100/minute
- **Returns:**
  - Array of reviews with reviewer names
  - User stats (total_reviews, average_rating, total_swaps_completed, trust_score)
- **Sort:** Created date DESC

#### `GET /api/reviews/my-reviews`
Get reviews written by current user
- **Auth:** Required
- **Rate limit:** 100/minute
- **Returns:** Array of reviews with reviewee names
- **Sort:** Created date DESC

#### `GET /api/reviews/can-review/{swap_id}`
Check if user can review swap
- **Auth:** Required
- **Rate limit:** 100/minute
- **Returns:** `{ can_review: boolean, reason?: string }`
- **Checks:**
  - Swap exists
  - User is participant
  - Swap is completed
  - Haven't already reviewed

#### `PATCH /api/reviews/{review_id}`
Update existing review
- **Auth:** Required (must be reviewer)
- **Rate limit:** 10/hour
- **Body:** ReviewUpdate (any fields)
- **Action:**
  - Updates review fields
  - Recalculates reviewee stats if rating changed
- **Validation:** Only reviewer can update own review

#### `DELETE /api/reviews/{review_id}`
Delete review
- **Auth:** Required (must be reviewer)
- **Rate limit:** 10/hour
- **Action:**
  - Deletes review
  - Recalculates reviewee stats (uses COALESCE for 0 defaults)
- **Validation:** Only reviewer can delete own review

---

## Database Integration

### **Migrations Already Created:**

1. **`migration/_001_create_users.py`** - Updated with review columns:
   - `total_reviews INTEGER DEFAULT 0`
   - `average_rating DECIMAL(3,2) DEFAULT 0.00`
   - `total_swaps_completed INTEGER DEFAULT 0`
   - `trust_score INTEGER DEFAULT 0`
   - `last_swap_at TIMESTAMPTZ`

2. **`migration/_008_create_swaps.py`** - Swaps table:
   - Primary key: `swap_id UUID`
   - Foreign keys: `user_a_uid`, `user_b_uid` → users(owner_firebase_uid)
   - Status: pending → accepted → completed (or cancelled)
   - Confirmation tracking: `user_a_confirmed`, `user_b_confirmed` (both must be true)
   - Timestamps: initiated_at, accepted_at, completed_at, cancelled_at
   - Index on user_a_uid, user_b_uid, status

3. **`migration/_009_create_reviews.py`** - Reviews table:
   - Primary key: `review_id UUID`
   - Foreign keys: reviewer_uid, reviewee_uid → users, swap_id → swaps
   - Ratings: overall (required), communication, item_condition, timeliness (optional)
   - Constraint: `CHECK (rating >= 1 AND rating <= 5)`
   - Constraint: `CHECK (reviewer_uid != reviewee_uid)` - No self-reviews
   - Constraint: `UNIQUE(reviewer_uid, swap_id)` - No duplicate reviews
   - Index on reviewee_uid, swap_id

---

## Main App Integration

Updated `app/main.py`:
```python
from app.api.reviews import router as reviews_router
from app.api.swaps import router as swaps_router

app.include_router(swaps_router, prefix="/api")
app.include_router(reviews_router, prefix="/api")
```

---

## Complete Swap Flow

```
1. CREATE SWAP REQUEST
   POST /api/swaps
   { userBUid, listingAId, listingBId, conversationId? }
   → status='pending'

2. USER B ACCEPTS
   PATCH /api/swaps/{swapId}/accept
   → status='accepted', accepted_at=NOW()

3. PHYSICAL SWAP HAPPENS
   Users meet and exchange items

4. USER A CONFIRMS RECEIPT
   POST /api/swaps/{swapId}/confirm-receipt
   → user_a_confirmed=true

5. USER B CONFIRMS RECEIPT
   POST /api/swaps/{swapId}/confirm-receipt
   → user_b_confirmed=true
   → status='completed', completed_at=NOW()
   → Both users' total_swaps_completed += 1

6. BOTH USERS CAN LEAVE REVIEWS
   POST /api/reviews
   { swapId, revieweeUid, rating, comment?, ... }
   → Updates reviewee's stats
```

---

## Review Flow

```
1. CHECK IF CAN REVIEW
   GET /api/reviews/can-review/{swapId}
   → { canReview: true/false, reason? }

2. CREATE REVIEW
   POST /api/reviews
   {
     swapId,
     revieweeUid,
     rating: 1-5 (required),
     communicationRating: 1-5 (optional),
     itemConditionRating: 1-5 (optional),
     timelinessRating: 1-5 (optional),
     comment: string (optional, max 500)
   }

3. STATS AUTO-UPDATE
   Reviewee's profile updated:
   - total_reviews += 1
   - average_rating = AVG(all ratings)
   - trust_score = (AVG(rating) * 10 + COUNT(*))
```

---

## Error Handling

All endpoints follow your error handling pattern:

```python
try:
    # Business logic
    logger.info(f"Success message")
    return JSONResponse(status_code=200, content={...})
except HTTPException:
    raise  # Re-raise FastAPI exceptions
except Exception as e:
    logger.error(f"Error description: {type(e).__name__}: {str(e)}", exc_info=True)
    raise HTTPException(status_code=500, detail="User-friendly error message")
```

---

## Authentication

All protected endpoints use:
```python
uid = extract_firebase_user_uid(request)
```

This extracts and verifies the Firebase token from the Authorization header.

---

## Rate Limiting

Following your patterns:
- **Read operations:** `@limiter.limit("100/minute")`
- **Write operations:** `@limiter.limit("10/hour")` or `@limiter.limit("20/hour")`

---

## Response Format

All datetime fields converted to ISO strings:
```python
result["created_at"] = result["created_at"].isoformat()
```

All models use `snake_to_camel` aliasing, so:
- Database: `user_a_uid`
- API Response: `userAUid`

---

## Next Steps

1. **Run migrations:**
   ```bash
   cd migration
   python run_migrations.py
   ```

2. **Test the API:**
   - Create swap request
   - Accept swap
   - Confirm receipt (both users)
   - Verify swap marked as completed
   - Create review
   - Verify stats updated
   - Test all validation rules

3. **Frontend is already ready** - See `SWAPS_AND_REVIEWS_FRONTEND_GUIDE.md`

---

## Security Features

✅ Firebase authentication required
✅ User can only review swaps they participated in
✅ User cannot review same swap twice (DB constraint)
✅ User cannot review themselves (DB constraint)
✅ Only user_b can accept/decline swap requests
✅ Both users must confirm receipt for completion
✅ Cannot review incomplete swaps
✅ Transaction safety with FOR UPDATE locks
✅ Rate limiting on all endpoints

---

## Summary

**Backend Complete!** 🎉

- ✅ 7 models (3 for swaps, 3 for reviews, 1 for stats)
- ✅ 13 API endpoints (7 for swaps, 6 for reviews)
- ✅ Complete CRUD operations
- ✅ Full validation and security
- ✅ Automatic stats calculation
- ✅ Transaction safety
- ✅ Your exact coding style maintained
- ✅ Integrated into main.py

Ready for testing and deployment!
