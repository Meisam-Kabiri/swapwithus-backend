"""
Public report endpoints
Allows users to report inappropriate content, scams, spam, etc.
"""

from fastapi import APIRouter, HTTPException, Request

from app.database.connection import get_pool_from_request
from app.middleware.auth import extract_firebase_user_uid
from app.middleware.rate_limit import limiter
from app.models.report import ReportCreate, ReportResponse

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ReportResponse, status_code=201)
@limiter.limit("5/hour")
async def create_report(request: Request, report: ReportCreate):
    """
    Submit a report for inappropriate content or user behavior

    Users can report:
    - Other users (harassment, scam, etc.)
    - Listings (spam, inappropriate content)
    - Swaps (fraud, dispute)
    - Messages (harassment, spam)

    At least one target must be specified
    """
    reporter_uid = extract_firebase_user_uid(request)

    # Validate that at least one target is specified
    if not any([
        report.reported_uid,
        report.reported_listing_id,
        report.reported_swap_id,
        report.reported_message_id
    ]):
        raise HTTPException(
            status_code=400,
            detail="At least one target must be specified (user, listing, swap, or message)"
        )

    # Prevent self-reporting (will also be caught by database trigger)
    if report.reported_uid and report.reported_uid == reporter_uid:
        raise HTTPException(
            status_code=400,
            detail="Cannot report yourself"
        )

    async with get_pool_from_request(request).acquire() as conn:
        # Verify reported entities exist
        if report.reported_uid:
            user_exists = await conn.fetchval(
                "SELECT 1 FROM users WHERE owner_firebase_uid = $1",
                report.reported_uid
            )
            if not user_exists:
                raise HTTPException(status_code=404, detail="Reported user not found")

        if report.reported_listing_id:
            listing_exists = await conn.fetchval(
                "SELECT 1 FROM listings WHERE id = $1",
                report.reported_listing_id
            )
            if not listing_exists:
                raise HTTPException(status_code=404, detail="Reported listing not found")

        if report.reported_swap_id:
            swap_exists = await conn.fetchval(
                "SELECT 1 FROM swaps WHERE id = $1",
                report.reported_swap_id
            )
            if not swap_exists:
                raise HTTPException(status_code=404, detail="Reported swap not found")

        # Check for duplicate reports (same reporter, same target, pending status)
        duplicate = await conn.fetchval(
            """
            SELECT 1 FROM reports
            WHERE reporter_uid = $1
                AND status = 'pending'
                AND (
                    (reported_uid = $2 AND $2 IS NOT NULL) OR
                    (reported_listing_id = $3 AND $3 IS NOT NULL) OR
                    (reported_swap_id = $4 AND $4 IS NOT NULL) OR
                    (reported_message_id = $5 AND $5 IS NOT NULL)
                )
            """,
            reporter_uid,
            report.reported_uid,
            report.reported_listing_id,
            report.reported_swap_id,
            report.reported_message_id
        )

        if duplicate:
            raise HTTPException(
                status_code=400,
                detail="You have already reported this item/user"
            )

        # Create report
        created_report = await conn.fetchrow(
            """
            INSERT INTO reports (
                reporter_uid,
                reported_uid,
                reported_listing_id,
                reported_swap_id,
                reported_message_id,
                report_type,
                description
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            reporter_uid,
            report.reported_uid,
            report.reported_listing_id,
            report.reported_swap_id,
            report.reported_message_id,
            report.report_type,
            report.description
        )

        return ReportResponse(**dict(created_report))


@router.get("/my-reports")
@limiter.limit("100/minute")
async def get_my_reports(request: Request):
    """
    Get all reports submitted by the authenticated user

    Returns list of reports with their current status
    """
    user_uid = extract_firebase_user_uid(request)

    async with get_pool_from_request(request).acquire() as conn:
        reports = await conn.fetch(
            """
            SELECT *
            FROM reports
            WHERE reporter_uid = $1
            ORDER BY created_at DESC
            """,
            user_uid
        )

        return [ReportResponse(**dict(r)) for r in reports]


@router.get("/{report_id}")
@limiter.limit("100/minute")
async def get_report(request: Request, report_id: int):
    """
    Get details of a specific report

    Users can only view reports they submitted
    """
    user_uid = extract_firebase_user_uid(request)

    async with get_pool_from_request(request).acquire() as conn:
        report = await conn.fetchrow(
            """
            SELECT *
            FROM reports
            WHERE id = $1 AND reporter_uid = $2
            """,
            report_id,
            user_uid
        )

        if not report:
            raise HTTPException(
                status_code=404,
                detail="Report not found or you don't have permission to view it"
            )

        return ReportResponse(**dict(report))
