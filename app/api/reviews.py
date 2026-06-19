import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database.connection import get_pool_from_request
from app.middleware.auth import extract_firebase_user_uid
from app.middleware.rate_limit import limiter
from app.models.swap import ReviewCreate, ReviewUpdate

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("")
@limiter.limit("10/hour")
async def create_review(
    request: Request,
    review: ReviewCreate,
    reviewer_uid: str = Depends(extract_firebase_user_uid),
):
    """
    Create a review for a completed swap.
    Can only review if swap is completed and haven't reviewed yet.
    """
    # Verify reviewer is not reviewing themselves
    if reviewer_uid == review.reviewee_uid:
        raise HTTPException(status_code=400, detail="Cannot review yourself")

    try:
        async with get_pool_from_request(request).acquire() as conn:
            async with conn.transaction():
                # Verify swap exists and is completed
                swap_row = await conn.fetchrow(
                    "SELECT user_a_uid, user_b_uid, status FROM swaps WHERE swap_id = $1", review.swap_id
                )

                if not swap_row:
                    raise HTTPException(status_code=404, detail="Swap not found")

                # Verify reviewer is participant
                if swap_row["user_a_uid"] != reviewer_uid and swap_row["user_b_uid"] != reviewer_uid:
                    raise HTTPException(status_code=403, detail="You are not a participant in this swap")

                # Verify swap is completed
                if swap_row["status"] != "completed":
                    raise HTTPException(status_code=400, detail="Can only review completed swaps")

                # Verify reviewee is the other participant
                other_user = swap_row["user_b_uid"] if swap_row["user_a_uid"] == reviewer_uid else swap_row["user_a_uid"]
                if review.reviewee_uid != other_user:
                    raise HTTPException(status_code=400, detail="Can only review the other participant in the swap")

                # Check if already reviewed
                existing_review = await conn.fetchval(
                    "SELECT 1 FROM reviews WHERE reviewer_uid = $1 AND swap_id = $2", reviewer_uid, review.swap_id
                )

                if existing_review:
                    raise HTTPException(status_code=400, detail="You have already reviewed this swap")

                # Insert review
                review_dict = review.model_dump()
                review_row = await conn.fetchrow(
                    """
                    INSERT INTO reviews (reviewer_uid, reviewee_uid, swap_id, rating,
                                        communication_rating, item_condition_rating, timeliness_rating, comment)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING review_id, created_at, updated_at, reviewer_uid, reviewee_uid, swap_id,
                              rating, communication_rating, item_condition_rating, timeliness_rating, comment
                    """,
                    reviewer_uid,
                    review_dict["reviewee_uid"],
                    review_dict["swap_id"],
                    review_dict["rating"],
                    review_dict.get("communication_rating"),
                    review_dict.get("item_condition_rating"),
                    review_dict.get("timeliness_rating"),
                    review_dict.get("comment"),
                )

                # Update reviewee's stats
                await conn.execute(
                    """
                    UPDATE users
                    SET total_reviews = total_reviews + 1,
                        average_rating = (
                            SELECT AVG(rating)::DECIMAL(3,2)
                            FROM reviews
                            WHERE reviewee_uid = $1
                        ),
                        trust_score = (
                            SELECT (AVG(rating) * 10 + COUNT(*))::INTEGER
                            FROM reviews
                            WHERE reviewee_uid = $1
                        )
                    WHERE owner_firebase_uid = $1
                    """,
                    review.reviewee_uid,
                )

                result = dict(review_row)
                # Convert UUID to string
                result["review_id"] = str(result["review_id"])
                result["swap_id"] = str(result["swap_id"])
                # Convert datetime to ISO string
                result["created_at"] = result["created_at"].isoformat()
                result["updated_at"] = result["updated_at"].isoformat()

                logger.info(f"User {reviewer_uid} created review for {review.reviewee_uid} on swap {review.swap_id}")
                return JSONResponse(status_code=201, content=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating review: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create review. Please try again.")


@router.get("/user/{user_uid}")
@limiter.limit("100/minute")
async def get_user_reviews(
    request: Request,
    user_uid: str,
    _uid: str = Depends(extract_firebase_user_uid),  # Verify authenticated
):
    """
    Get all reviews for a specific user (reviews they received).
    Also returns user stats.
    """
    try:
        async with get_pool_from_request(request).acquire() as conn:
            # Get reviews
            reviews_rows = await conn.fetch(
                """
                SELECT r.review_id, r.created_at, r.updated_at, r.reviewer_uid, r.reviewee_uid,
                       r.swap_id, r.rating, r.communication_rating, r.item_condition_rating,
                       r.timeliness_rating, r.comment,
                       u.name as reviewer_name
                FROM reviews r
                LEFT JOIN users u ON r.reviewer_uid = u.owner_firebase_uid
                WHERE r.reviewee_uid = $1
                ORDER BY r.created_at DESC
                """,
                user_uid,
            )

            reviews = []
            for row in reviews_rows:
                review_dict = {
                    "reviewId": str(row["review_id"]),
                    "swapId": str(row["swap_id"]),
                    "reviewerUid": row["reviewer_uid"],
                    "revieweeUid": row["reviewee_uid"],
                    "rating": row["rating"],
                    "communicationRating": row["communication_rating"],
                    "itemConditionRating": row["item_condition_rating"],
                    "timelinessRating": row["timeliness_rating"],
                    "comment": row["comment"],
                    "reviewerName": row["reviewer_name"],
                    "createdAt": row["created_at"].isoformat(),
                    "updatedAt": row["updated_at"].isoformat(),
                }
                reviews.append(review_dict)

            # Get stats
            stats_row = await conn.fetchrow(
                """
                SELECT total_reviews, average_rating, total_swaps_completed, trust_score
                FROM users
                WHERE owner_firebase_uid = $1
                """,
                user_uid,
            )

            if stats_row:
                stats = {
                    "total_reviews": stats_row["total_reviews"] or 0,
                    "average_rating": float(stats_row["average_rating"]) if stats_row["average_rating"] else 0.0,
                    "total_swaps_completed": stats_row["total_swaps_completed"] or 0,
                    "trust_score": stats_row["trust_score"] or 0
                }
            else:
                stats = {"total_reviews": 0, "average_rating": 0.0, "total_swaps_completed": 0, "trust_score": 0}

            return JSONResponse(status_code=200, content={"reviews": reviews, "stats": stats})

    except Exception as e:
        logger.error(f"Error fetching reviews for user {user_uid}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch reviews. Please try again.")


@router.get("/my-reviews")
@limiter.limit("100/minute")
async def get_my_reviews(
    request: Request,
    uid: str = Depends(extract_firebase_user_uid),
):
    """
    Get all reviews written by the current user (reviews they gave).
    """
    try:
        async with get_pool_from_request(request).acquire() as conn:
            reviews_rows = await conn.fetch(
                """
                SELECT r.review_id, r.created_at, r.updated_at, r.reviewer_uid, r.reviewee_uid,
                       r.swap_id, r.rating, r.communication_rating, r.item_condition_rating,
                       r.timeliness_rating, r.comment,
                       u.name as reviewee_name
                FROM reviews r
                LEFT JOIN users u ON r.reviewee_uid = u.owner_firebase_uid
                WHERE r.reviewer_uid = $1
                ORDER BY r.created_at DESC
                """,
                uid,
            )

            reviews = []
            for row in reviews_rows:
                review_dict = {
                    "reviewId": str(row["review_id"]),
                    "swapId": str(row["swap_id"]),
                    "reviewerUid": row["reviewer_uid"],
                    "revieweeUid": row["reviewee_uid"],
                    "rating": row["rating"],
                    "communicationRating": row["communication_rating"],
                    "itemConditionRating": row["item_condition_rating"],
                    "timelinessRating": row["timeliness_rating"],
                    "comment": row["comment"],
                    "revieweeName": row["reviewee_name"],
                    "createdAt": row["created_at"].isoformat(),
                    "updatedAt": row["updated_at"].isoformat(),
                }
                reviews.append(review_dict)

            return JSONResponse(status_code=200, content={"reviews": reviews})

    except Exception as e:
        logger.error(f"Error fetching reviews by user {uid}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch reviews. Please try again.")


@router.get("/can-review/{swap_id}")
@limiter.limit("100/minute")
async def can_review_swap(
    request: Request,
    swap_id: str,
    uid: str = Depends(extract_firebase_user_uid),
):
    """
    Check if current user can review a swap.
    Returns can_review boolean and reason if not.
    """
    try:
        async with get_pool_from_request(request).acquire() as conn:
            # Get swap details
            swap_row = await conn.fetchrow("SELECT user_a_uid, user_b_uid, status FROM swaps WHERE swap_id = $1", swap_id)

            logger.info(f"🔍 Can review check - User: {uid}, Swap: {swap_id}")
            logger.info(f"🔍 Swap data: {dict(swap_row) if swap_row else 'Not found'}")

            if not swap_row:
                logger.warning(f"❌ Swap not found: {swap_id}")
                return JSONResponse(status_code=200, content={"can_review": False, "reason": "Swap not found"})

            # Check if user is participant
            if swap_row["user_a_uid"] != uid and swap_row["user_b_uid"] != uid:
                logger.warning(f"❌ User {uid} not participant in swap {swap_id}")
                return JSONResponse(
                    status_code=200, content={"can_review": False, "reason": "You are not a participant in this swap"}
                )

            # Check if swap is completed
            if swap_row["status"] != "completed":
                logger.warning(f"❌ Swap {swap_id} status is '{swap_row['status']}', not completed")
                return JSONResponse(
                    status_code=200, content={"can_review": False, "reason": "Swap must be completed before reviewing"}
                )

            # Check if already reviewed
            existing_review = await conn.fetchval(
                "SELECT 1 FROM reviews WHERE reviewer_uid = $1 AND swap_id = $2", uid, swap_id
            )

            if existing_review:
                logger.info(f"⚠️ User {uid} already reviewed swap {swap_id}")
                return JSONResponse(
                    status_code=200, content={"can_review": False, "reason": "You have already reviewed this swap"}
                )

            logger.info(f"✅ User {uid} CAN review swap {swap_id}")
            return JSONResponse(status_code=200, content={"can_review": True})

    except Exception as e:
        logger.error(f"Error checking review eligibility for swap {swap_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to check review eligibility. Please try again.")


@router.patch("/{review_id}")
@limiter.limit("10/hour")
async def update_review(
    request: Request,
    review_id: str,
    review_update: ReviewUpdate,
    uid: str = Depends(extract_firebase_user_uid),
):
    """
    Update an existing review.
    Only the reviewer can update their own review.
    """
    try:
        async with get_pool_from_request(request).acquire() as conn:
            async with conn.transaction():
                # Verify review exists and user is reviewer
                review_row = await conn.fetchrow(
                    "SELECT reviewer_uid, reviewee_uid, rating FROM reviews WHERE review_id = $1", review_id
                )

                if not review_row:
                    raise HTTPException(status_code=404, detail="Review not found")

                if review_row["reviewer_uid"] != uid:
                    raise HTTPException(status_code=403, detail="You can only update your own reviews")

                # Build update query dynamically
                update_dict = review_update.model_dump(exclude_none=True)
                if not update_dict:
                    raise HTTPException(status_code=400, detail="No fields to update")

                set_clauses = []
                values = []
                param_num = 1

                for key, value in update_dict.items():
                    set_clauses.append(f"{key} = ${param_num}")
                    values.append(value)
                    param_num += 1

                set_clauses.append(f"updated_at = NOW()")
                values.append(review_id)

                query = f"UPDATE reviews SET {', '.join(set_clauses)} WHERE review_id = ${param_num}"

                result = await conn.execute(query, *values)

                if result == "UPDATE 0":
                    raise HTTPException(status_code=404, detail="Review not found")

                # Recalculate reviewee's stats if rating changed
                if "rating" in update_dict:
                    reviewee_uid = review_row["reviewee_uid"]
                    await conn.execute(
                        """
                        UPDATE users
                        SET average_rating = (
                                SELECT AVG(rating)::DECIMAL(3,2)
                                FROM reviews
                                WHERE reviewee_uid = $1
                            ),
                            trust_score = (
                                SELECT (AVG(rating) * 10 + COUNT(*))::INTEGER
                                FROM reviews
                                WHERE reviewee_uid = $1
                            )
                        WHERE owner_firebase_uid = $1
                        """,
                        reviewee_uid,
                    )

                logger.info(f"User {uid} updated review {review_id}")
                return JSONResponse(status_code=200, content={"message": "Review updated successfully"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating review {review_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update review. Please try again.")


@router.delete("/{review_id}")
@limiter.limit("10/hour")
async def delete_review(
    request: Request,
    review_id: str,
    uid: str = Depends(extract_firebase_user_uid),
):
    """
    Delete a review.
    Only the reviewer can delete their own review.
    """
    try:
        async with get_pool_from_request(request).acquire() as conn:
            async with conn.transaction():
                # Verify review exists and user is reviewer
                review_row = await conn.fetchrow(
                    "SELECT reviewer_uid, reviewee_uid FROM reviews WHERE review_id = $1", review_id
                )

                if not review_row:
                    raise HTTPException(status_code=404, detail="Review not found")

                if review_row["reviewer_uid"] != uid:
                    raise HTTPException(status_code=403, detail="You can only delete your own reviews")

                reviewee_uid = review_row["reviewee_uid"]

                # Delete review
                result = await conn.execute("DELETE FROM reviews WHERE review_id = $1", review_id)

                if result == "DELETE 0":
                    raise HTTPException(status_code=404, detail="Review not found")

                # Update reviewee's stats
                await conn.execute(
                    """
                    UPDATE users
                    SET total_reviews = (
                            SELECT COUNT(*)::INTEGER
                            FROM reviews
                            WHERE reviewee_uid = $1
                        ),
                        average_rating = COALESCE(
                            (SELECT AVG(rating)::DECIMAL(3,2) FROM reviews WHERE reviewee_uid = $1),
                            0.00
                        ),
                        trust_score = COALESCE(
                            (SELECT (AVG(rating) * 10 + COUNT(*))::INTEGER FROM reviews WHERE reviewee_uid = $1),
                            0
                        )
                    WHERE owner_firebase_uid = $1
                    """,
                    reviewee_uid,
                )

                logger.info(f"User {uid} deleted review {review_id}")
                return JSONResponse(status_code=200, content={"message": "Review deleted successfully"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting review {review_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete review. Please try again.")
