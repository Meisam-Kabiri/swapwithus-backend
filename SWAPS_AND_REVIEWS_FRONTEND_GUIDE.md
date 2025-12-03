# Swaps & Reviews System - Frontend Implementation Guide

## Overview

Complete frontend UI for the swap and review system. Users can request swaps, confirm receipt, and leave reviews after completing swaps.

---

## Files Created

### **1. Types** (`/src/types/swaps.ts`)
TypeScript interfaces for:
- `Swap` - Swap tracking
- `SwapWithDetails` - Swap with populated data
- `Review` - Review data
- `ReviewWithDetails` - Review with user info
- `UserStats` - User ratings and swap counts
- Request/Response types

### **2. API Functions** (`/src/lib/swapsApi.ts`)

#### Swaps API
```typescript
swapsApi.getMySwaps(config)           // Get all user's swaps
swapsApi.getSwap(swapId, config)      // Get specific swap
swapsApi.createSwap(data, config)     // Create new swap request
swapsApi.acceptSwap(swapId, config)   // Accept swap request
swapsApi.declineSwap(swapId, reason, config)  // Decline swap
swapsApi.confirmReceipt(swapId, config)       // Confirm item received
swapsApi.cancelSwap(swapId, reason, config)   // Cancel swap
```

#### Reviews API
```typescript
reviewsApi.getUserReviews(userUid, config)    // Get user's reviews
reviewsApi.getMyReviews(config)               // Get reviews I wrote
reviewsApi.canReviewSwap(swapId, config)      // Check if can review
reviewsApi.createReview(data, config)         // Create review
reviewsApi.updateReview(reviewId, data, config) // Update review
reviewsApi.deleteReview(reviewId, config)     // Delete review
```

### **3. Components**

#### `StarRating.tsx`
Interactive 5-star rating component
```tsx
<StarRating
  rating={4}
  onChange={(rating) => setRating(rating)}
  readonly={false}
  size="md"  // sm, md, lg
  showNumber={true}
/>
```

#### `ReviewModal.tsx`
Modal for submitting reviews
```tsx
<ReviewModal
  isOpen={true}
  onClose={() => setShowModal(false)}
  onSubmit={handleSubmit}
  otherUserName="John Doe"
  itemTitle="Book Title"
/>
```

#### `ReviewsSection.tsx`
Display user reviews and stats (for profile page)
```tsx
<ReviewsSection
  userUid="user123"
  isOwnProfile={true}
/>
```

### **4. Pages**

#### `/swaps` - Swaps Management Page
- View all swaps (Active/Completed/Cancelled)
- Confirm receipt of items
- Navigate to leave reviews
- View swap details

Features:
- ✅ Tabbed interface (Active/Completed/Cancelled)
- ✅ Confirm receipt button for accepted swaps
- ✅ "Leave Review" button for completed swaps
- ✅ Status badges (Pending/Accepted/Completed/Cancelled)
- ✅ Links to messages

#### `/swaps/[swapId]/review` - Review Page
- Leave a review for completed swap
- Overall rating (required)
- Detailed ratings (optional):
  - Communication
  - Item Condition
  - Timeliness
- Comment (optional, max 500 chars)

Features:
- ✅ Validates swap is completed
- ✅ Prevents duplicate reviews
- ✅ Shows swap details
- ✅ Character counter for comment

---

## User Flow

### **1. Swap Lifecycle**

```
┌─────────────────────────────────────────────────────────────┐
│                     SWAP LIFECYCLE                          │
└─────────────────────────────────────────────────────────────┘

1. INITIATE SWAP
   User A: "I want to swap my Book for your Bike"
   → Creates swap with status='pending'

2. ACCEPT/DECLINE
   User B: Clicks "Accept Swap Request"
   → Updates status to 'accepted'
   → Or clicks "Decline" → status='cancelled'

3. PHYSICAL SWAP HAPPENS
   Users meet and exchange items

4. CONFIRM RECEIPT (Both Must Confirm)
   User A: Clicks "Confirm Receipt" → user_a_confirmed=true
   User B: Clicks "Confirm Receipt" → user_b_confirmed=true

   When BOTH confirm:
   → status='completed'
   → completed_at=NOW()
   → Enables reviews

5. LEAVE REVIEWS
   Both users can now leave reviews
   → Opens review modal
   → Submits rating + comment
   → Updates reviewee's stats
```

### **2. Review Flow**

```
┌─────────────────────────────────────────────────────────────┐
│                     REVIEW FLOW                             │
└─────────────────────────────────────────────────────────────┘

1. Go to /swaps
2. Find completed swap
3. Click "Leave Review"
4. Redirects to /swaps/{swapId}/review
5. Fill review form:
   - Overall rating (1-5 stars, required)
   - Communication rating (optional)
   - Item condition rating (optional)
   - Timeliness rating (optional)
   - Comment (optional, 500 chars)
6. Submit
7. Updates reviewee's:
   - total_reviews += 1
   - average_rating (recalculated)
   - Reviews list
```

---

## UI Screenshots (Text Description)

### Swaps Page (`/swaps`)

```
┌─────────────────────────────────────────────────────────────┐
│ My Swaps                                                    │
│                                                             │
│ [Active (2)] [Completed (5)] [Cancelled (1)]               │
│ ─────────────                                              │
│                                                             │
│ ┌───────────────────────────────────────────────────────┐  │
│ │ Swap with John Doe            [Status: Accepted]      │  │
│ │ March 15, 2024                                        │  │
│ │                                                       │  │
│ │ Your item: "Harry Potter Book"                       │  │
│ │ Their item: "Mountain Bike"                          │  │
│ │                                                       │  │
│ │ ⚠️ Please confirm receipt of the item                │  │
│ │ [Confirm Receipt]                                     │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│ ┌───────────────────────────────────────────────────────┐  │
│ │ Swap with Jane Smith          [Status: Completed]     │  │
│ │ March 10, 2024                                        │  │
│ │                                                       │  │
│ │ Your item: "Winter Jacket"                           │  │
│ │ Their item: "Camera"                                 │  │
│ │                                                       │  │
│ │ [Leave Review] [View Messages]                       │  │
│ └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Review Modal

```
┌─────────────────────────────────────────────────────────────┐
│ Review John Doe                                      [X]    │
│ Swap: Mountain Bike                                        │
│ ─────────────────────────────────────────────────────────  │
│                                                             │
│ Overall Rating *                                           │
│ ★★★★★                                                      │
│                                                             │
│ Detailed Ratings (Optional)                                │
│ Communication:     ★★★★☆                                   │
│ Item Condition:    ★★★★★                                   │
│ Timeliness:        ★★★☆☆                                   │
│                                                             │
│ Your Review (Optional)                                     │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Great swapper! The bike was exactly as described.   │    │
│ │ Would swap again.                                   │    │
│ └─────────────────────────────────────────────────────┘    │
│ 128/500 characters                                         │
│                                                             │
│ 💡 Reviews help build trust in the community               │
│                                                             │
│ [Cancel] [Submit Review]                                   │
└─────────────────────────────────────────────────────────────┘
```

### Profile Reviews Section

```
┌─────────────────────────────────────────────────────────────┐
│ Reviews & Swaps                                            │
│                                                             │
│ ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐                    │
│ │★★★★☆│  │  23  │  │  45  │  │  87  │                    │
│ │ 4.5  │  │Reviews│ │ Swaps│  │Trust │                    │
│ └──────┘  └──────┘  └──────┘  └──────┘                    │
│                                                             │
│ Reviews (23)                                               │
│ ─────────────                                              │
│                                                             │
│ ┌───────────────────────────────────────────────────────┐  │
│ │ Jane Smith                    March 15, 2024          │  │
│ │ ★★★★★ 5.0                                            │  │
│ │                                                       │  │
│ │ Communication: ★★★★★                                 │  │
│ │ Item Condition: ★★★★★                                │  │
│ │ Timeliness: ★★★★☆                                    │  │
│ │                                                       │  │
│ │ "Excellent swapper! Very professional and item was   │  │
│ │ in perfect condition."                               │  │
│ │                                                       │  │
│ │ Swap: Winter Jacket                                  │  │
│ └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Integration Points

### Add to Profile Page

```tsx
import ReviewsSection from '@/components/profile/ReviewsSection';

// In profile page:
<ReviewsSection
  userUid={user.uid}
  isOwnProfile={true}
/>
```

### Add to Header Navigation

```tsx
<Link href="/swaps">
  My Swaps
  {unreadSwapsCount > 0 && (
    <span className="badge">{unreadSwapsCount}</span>
  )}
</Link>
```

### Add Swap Initiation in Messaging (TODO)

```tsx
// In conversation view:
<button onClick={handleInitiateSwap}>
  Request Swap
</button>

// Opens dialog to select:
// - Your listing (from your active listings)
// - Their listing (from their active listings)
```

---

## Next Steps (Backend Required)

To make this functional, you need to implement backend API endpoints:

1. **Swaps Endpoints**
   - `POST /api/swaps` - Create swap
   - `GET /api/swaps` - Get user's swaps
   - `GET /api/swaps/{swapId}` - Get swap details
   - `PATCH /api/swaps/{swapId}/accept` - Accept swap
   - `PATCH /api/swaps/{swapId}/decline` - Decline swap
   - `POST /api/swaps/{swapId}/confirm-receipt` - Confirm receipt
   - `PATCH /api/swaps/{swapId}/cancel` - Cancel swap

2. **Reviews Endpoints**
   - `POST /api/reviews` - Create review
   - `GET /api/reviews/user/{userUid}` - Get user's reviews
   - `GET /api/reviews/can-review/{swapId}` - Check if can review
   - `PATCH /api/reviews/{reviewId}` - Update review
   - `DELETE /api/reviews/{reviewId}` - Delete review

3. **User Stats**
   - `GET /api/users/{userUid}/stats` - Get user stats

---

## Testing Checklist

Once backend is ready, test:

- [ ] Create swap request
- [ ] Accept swap request
- [ ] Decline swap request
- [ ] Confirm receipt (both users)
- [ ] Verify swap marked as completed
- [ ] Leave review for completed swap
- [ ] View reviews on profile
- [ ] Verify rating aggregation
- [ ] Test permission checks (can't review own swaps, etc.)
- [ ] Test duplicate review prevention
- [ ] Cancel swap functionality

---

## Summary

Frontend is complete and ready for backend integration! 🎉

**Total Files Created:**
- 1 Type definition file
- 1 API functions file
- 3 Reusable components
- 2 Pages (swaps list, review page)
- 1 Profile section component

**Features:**
✅ Swap lifecycle management
✅ Review submission with detailed ratings
✅ User stats and reviews display
✅ Clean, responsive UI
✅ Error handling
✅ Loading states

**Next:** Implement backend API endpoints to make it functional!
