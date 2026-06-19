"""
Admin API endpoints for platform management and moderation
"""

from datetime import datetime, timedelta

import asyncpg  # type: ignore
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.database.connection import get_db_conn
from app.middleware.admin import verify_admin
from app.middleware.rate_limit import limiter
from app.models.admin import (
  BanUserRequest,
  DashboardStats,
  PaginatedResponse,
  SwapManagement,
  UserManagement,
)
from app.models.report import ReportResolve, ReportWithDetails

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_admin)])


# ==================== DASHBOARD & STATS ====================


@router.get("/stats", response_model=DashboardStats)
@limiter.limit("60/minute")
async def get_dashboard_stats(
  request: Request,
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Get overview statistics for admin dashboard

  Returns counts and metrics for users, listings, swaps, and reports
  """
  # User stats
  total_users = await conn.fetchval("SELECT COUNT(*) FROM users") or 0
  active_users = await conn.fetchval(
    "SELECT COUNT(*) FROM users WHERE is_banned = FALSE"
  ) or 0
  banned_users = await conn.fetchval(
    "SELECT COUNT(*) FROM users WHERE is_banned = TRUE"
  ) or 0

  # Listing stats (aggregate across homes, books, caravans, clothes)
  total_listings = await conn.fetchval("""
    SELECT (
      (SELECT COUNT(*) FROM homes) +
      (SELECT COUNT(*) FROM books) +
      (SELECT COUNT(*) FROM caravans) +
      (SELECT COUNT(*) FROM clothes)
    )
  """) or 0
  active_listings = await conn.fetchval("""
    SELECT (
      (SELECT COUNT(*) FROM homes WHERE status = 'published') +
      (SELECT COUNT(*) FROM books) +
      (SELECT COUNT(*) FROM caravans WHERE status = 'published') +
      (SELECT COUNT(*) FROM clothes)
    )
  """) or 0

  # Swap stats
  total_swaps = await conn.fetchval("SELECT COUNT(*) FROM swaps") or 0
  swaps_pending = await conn.fetchval(
    "SELECT COUNT(*) FROM swaps WHERE status = 'pending'"
  ) or 0
  swaps_active = await conn.fetchval(
    "SELECT COUNT(*) FROM swaps WHERE status = 'accepted'"
  ) or 0
  swaps_completed = await conn.fetchval(
    "SELECT COUNT(*) FROM swaps WHERE status = 'completed'"
  ) or 0
  swaps_cancelled = await conn.fetchval(
    "SELECT COUNT(*) FROM swaps WHERE status = 'cancelled'"
  ) or 0

  # Report stats
  pending_reports = await conn.fetchval(
    "SELECT COUNT(*) FROM reports WHERE status = 'pending'"
  ) or 0

  # Time-based stats
  seven_days_ago = datetime.now() - timedelta(days=7)
  thirty_days_ago = datetime.now() - timedelta(days=30)

  new_users_7d = await conn.fetchval(
    "SELECT COUNT(*) FROM users WHERE created_at > $1",
    seven_days_ago
  ) or 0
  new_users_30d = await conn.fetchval(
    "SELECT COUNT(*) FROM users WHERE created_at > $1",
    thirty_days_ago
  ) or 0
  new_listings_7d = await conn.fetchval("""
    SELECT (
      (SELECT COUNT(*) FROM homes WHERE created_at > $1) +
      (SELECT COUNT(*) FROM books WHERE created_at > $1) +
      (SELECT COUNT(*) FROM caravans WHERE created_at > $1) +
      (SELECT COUNT(*) FROM clothes WHERE created_at > $1)
    )
  """, seven_days_ago) or 0
  new_swaps_7d = await conn.fetchval(
    "SELECT COUNT(*) FROM swaps WHERE initiated_at > $1",
    seven_days_ago
  ) or 0

  return DashboardStats(
    total_users=total_users,
    active_users=active_users,
    banned_users=banned_users,
    total_listings=total_listings,
    active_listings=active_listings,
    total_swaps=total_swaps,
    swaps_pending=swaps_pending,
    swaps_active=swaps_active,
    swaps_completed=swaps_completed,
    swaps_cancelled=swaps_cancelled,
    pending_reports=pending_reports,
    new_users_7d=new_users_7d,
    new_users_30d=new_users_30d,
    new_listings_7d=new_listings_7d,
    new_swaps_7d=new_swaps_7d,
  )


# ==================== USER MANAGEMENT ====================


@router.get("/users")
@limiter.limit("100/minute")
async def get_users(
  request: Request,
  page: int = Query(1, ge=1),
  page_size: int = Query(20, ge=1, le=100),
  search: str | None = Query(None),
  status: str = Query("all"),  # all, active, banned, admin
  sort_by: str = Query("created_at"),  # created_at, trust_score, total_swaps
  sort_order: str = Query("desc"),  # asc, desc
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Get paginated list of users with filtering and search

  Query params:
  - page: Page number (default: 1)
  - page_size: Items per page (default: 20, max: 100)
  - search: Search by email or name
  - status: Filter by status (all, active, banned, admin)
  - sort_by: Sort field (created_at, trust_score, total_swaps)
  - sort_order: Sort direction (asc, desc)
  """
  offset = (page - 1) * page_size

  # Build query
  query = """
    SELECT
      u.owner_firebase_uid,
      u.email,
      u.name as display_name,  -- Map 'name' to 'display_name' for frontend compatibility
      u.trust_score,
      u.is_banned,
      u.is_admin,
      u.ban_reason,
      u.banned_at,
      u.created_at,
      u.last_active,
      COUNT(DISTINCT s.swap_id) FILTER (WHERE s.status IN ('accepted', 'completed')) as total_swaps,
      COUNT(DISTINCT s.swap_id) FILTER (WHERE s.status = 'completed') as completed_swaps,
      AVG(r.rating) as average_rating
    FROM users u
    LEFT JOIN swaps s ON (u.owner_firebase_uid = s.user_a_uid OR u.owner_firebase_uid = s.user_b_uid)
    LEFT JOIN reviews r ON u.owner_firebase_uid = r.reviewee_uid
    WHERE 1=1
  """
  count_query = "SELECT COUNT(DISTINCT u.owner_firebase_uid) FROM users u WHERE 1=1"
  params = []
  param_idx = 1

  # Add search filter
  if search:
    search_condition = f" AND (u.email ILIKE ${param_idx} OR u.name ILIKE ${param_idx})"
    query += search_condition
    count_query += search_condition
    params.append(f"%{search}%")
    param_idx += 1

  # Add status filter
  if status == "banned":
    query += " AND u.is_banned = TRUE"
    count_query += " AND u.is_banned = TRUE"
  elif status == "active":
    query += " AND u.is_banned = FALSE"
    count_query += " AND u.is_banned = FALSE"
  elif status == "admin":
    query += " AND u.is_admin = TRUE"
    count_query += " AND u.is_admin = TRUE"

  # Group by for aggregates
  query += """
    GROUP BY u.owner_firebase_uid, u.email, u.name, u.trust_score,
         u.is_banned, u.is_admin, u.ban_reason, u.banned_at,
         u.created_at, u.last_active
  """

  # Add sorting
  sort_mapping = {
    "created_at": "u.created_at",
    "trust_score": "u.trust_score",
    "total_swaps": "total_swaps",
  }
  sort_field = sort_mapping.get(sort_by, "u.created_at")
  sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"
  query += f" ORDER BY {sort_field} {sort_direction}"

  # Add pagination
  query += f" LIMIT ${param_idx} OFFSET ${param_idx + 1}"
  params.extend([page_size, offset])

  # Execute queries
  users = await conn.fetch(query, *params)
  total = await conn.fetchval(count_query, *(params[:param_idx - 1]))

  total_pages = (total + page_size - 1) // page_size

  return PaginatedResponse(
    items=[UserManagement(**dict(u)) for u in users],
    total=total,
    page=page,
    page_size=page_size,
    total_pages=total_pages,
  )


@router.get("/users/{user_id}")
@limiter.limit("100/minute")
async def get_user_details(
  request: Request,
  user_id: str,
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Get detailed information about a specific user

  Returns user profile, stats, recent activity, and moderation history
  """
  # Get user info with stats
  user = await conn.fetchrow(
    """
    SELECT
      u.*,
      COUNT(DISTINCT s.swap_id) FILTER (WHERE s.status IN ('accepted', 'completed')) as total_swaps,
      COUNT(DISTINCT s.swap_id) FILTER (WHERE s.status = 'completed') as completed_swaps,
      AVG(r.rating) as average_rating
    FROM users u
    LEFT JOIN swaps s ON (u.owner_firebase_uid = s.user_a_uid OR u.owner_firebase_uid = s.user_b_uid)
    LEFT JOIN reviews r ON u.owner_firebase_uid = r.reviewee_uid
    WHERE u.owner_firebase_uid = $1
    GROUP BY u.owner_firebase_uid
    """,
    user_id
  )

  if not user:
    raise HTTPException(status_code=404, detail="User not found")

  # Count user's listings across all types
  total_listings = await conn.fetchval("""
    SELECT (
      (SELECT COUNT(*) FROM homes WHERE owner_firebase_uid = $1) +
      (SELECT COUNT(*) FROM books WHERE owner_firebase_uid = $1) +
      (SELECT COUNT(*) FROM caravans WHERE owner_firebase_uid = $1) +
      (SELECT COUNT(*) FROM clothes WHERE owner_firebase_uid = $1)
    )
  """, user_id) or 0

  active_listings = await conn.fetchval("""
    SELECT (
      (SELECT COUNT(*) FROM homes WHERE owner_firebase_uid = $1 AND status = 'published') +
      (SELECT COUNT(*) FROM books WHERE owner_firebase_uid = $1) +
      (SELECT COUNT(*) FROM caravans WHERE owner_firebase_uid = $1 AND status = 'published') +
      (SELECT COUNT(*) FROM clothes WHERE owner_firebase_uid = $1)
    )
  """, user_id) or 0

  # Add listing counts to user dict
  user = dict(user)
  user['total_listings'] = total_listings
  user['active_listings'] = active_listings

  # Get recent reports (both as reporter and reported)
  reports_made = await conn.fetch(
    """
    SELECT id, report_type, status, created_at
    FROM reports
    WHERE reporter_uid = $1
    ORDER BY created_at DESC
    LIMIT 10
    """,
    user_id
  )

  reports_received = await conn.fetch(
    """
    SELECT id, report_type, status, created_at, resolved_at
    FROM reports
    WHERE reported_uid = $1
    ORDER BY created_at DESC
    LIMIT 10
    """,
    user_id
  )

  # Get recent swaps
  recent_swaps = await conn.fetch(
    """
    SELECT swap_id, status, initiated_at, completed_at
    FROM swaps
    WHERE user_a_uid = $1 OR user_b_uid = $1
    ORDER BY initiated_at DESC
    LIMIT 10
    """,
    user_id
  )

  return {
    "user": UserManagement(**dict(user)),
    "reports_made": [dict(r) for r in reports_made],
    "reports_received": [dict(r) for r in reports_received],
    "recent_swaps": [dict(s) for s in recent_swaps],
  }


# RPC-style endpoint (not REST): Uses POST with action verb for clarity
@router.post("/users/{user_id}/ban")
@limiter.limit("20/hour")
async def ban_user(
  request: Request,
  user_id: str,
  ban_request: BanUserRequest,
  admin_uid: str = Depends(verify_admin),
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Ban a user from the platform

  Body params:
  - reason: Reason for the ban (required)
  - permanent: Whether ban is permanent (default: true)
  - ban_duration_days: Duration in days if not permanent
  """
  # Check user exists
  user = await conn.fetchrow(
    "SELECT owner_firebase_uid, is_admin FROM users WHERE owner_firebase_uid = $1",
    user_id
  )

  if not user:
    raise HTTPException(status_code=404, detail="User not found")

  if user["is_admin"]:
    raise HTTPException(
      status_code=403,
      detail="Cannot ban an admin user"
    )

  # Ban the user
  await conn.execute(
    """
    UPDATE users
    SET is_banned = TRUE,
      ban_reason = $1,
      banned_at = NOW(),
      ban_duration_days = $2
    WHERE owner_firebase_uid = $3
    """,
    ban_request.reason,
    ban_request.ban_duration_days if not ban_request.permanent else None,
    user_id
  )

  # Log the action (optional: create admin_actions table)
  # For now, we'll just return success

  return {
    "success": True,
    "message": f"User {user_id} has been banned",
    "banned_by": admin_uid,
    "reason": ban_request.reason,
  }


# RPC-style endpoint (not REST): Uses POST with action verb for clarity
@router.post("/users/{user_id}/unban")
@limiter.limit("20/hour")
async def unban_user(
  request: Request,
  user_id: str,
  admin_uid: str = Depends(verify_admin),
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Unban a user

  Removes ban status and clears ban reason
  """
  # Check user exists and is banned
  user = await conn.fetchrow(
    "SELECT owner_firebase_uid, is_banned FROM users WHERE owner_firebase_uid = $1",
    user_id
  )

  if not user:
    raise HTTPException(status_code=404, detail="User not found")

  if not user["is_banned"]:
    raise HTTPException(status_code=400, detail="User is not banned")

  # Unban the user
  await conn.execute(
    """
    UPDATE users
    SET is_banned = FALSE,
      ban_reason = NULL,
      banned_at = NULL,
      ban_duration_days = NULL
    WHERE owner_firebase_uid = $1
    """,
    user_id
  )

  return {
    "success": True,
    "message": f"User {user_id} has been unbanned",
    "unbanned_by": admin_uid,
  }


# RPC-style endpoint (not REST): Uses POST with action verb for clarity
@router.post("/users/{user_id}/make-admin")
@limiter.limit("5/hour")
async def make_user_admin(
  request: Request,
  user_id: str,
  admin_uid: str = Depends(verify_admin),
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Grant admin privileges to a user

  Only existing admins can create new admins
  """
  # Check user exists
  user = await conn.fetchrow(
    "SELECT owner_firebase_uid, is_admin FROM users WHERE owner_firebase_uid = $1",
    user_id
  )

  if not user:
    raise HTTPException(status_code=404, detail="User not found")

  if user["is_admin"]:
    raise HTTPException(status_code=400, detail="User is already an admin")

  # Make user admin
  await conn.execute(
    "UPDATE users SET is_admin = TRUE WHERE owner_firebase_uid = $1",
    user_id
  )

  return {
    "success": True,
    "message": f"User {user_id} is now an admin",
    "granted_by": admin_uid,
  }


# RPC-style endpoint (not REST): Uses POST with action verb for clarity
@router.post("/users/{user_id}/remove-admin")
@limiter.limit("5/hour")
async def remove_admin_privileges(
  request: Request,
  user_id: str,
  admin_uid: str = Depends(verify_admin),
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Remove admin privileges from a user

  Cannot remove your own admin privileges
  """
  if admin_uid == user_id:
    raise HTTPException(
      status_code=403,
      detail="Cannot remove your own admin privileges"
    )

  # Check user exists and is admin
  user = await conn.fetchrow(
    "SELECT owner_firebase_uid, is_admin FROM users WHERE owner_firebase_uid = $1",
    user_id
  )

  if not user:
    raise HTTPException(status_code=404, detail="User not found")

  if not user["is_admin"]:
    raise HTTPException(status_code=400, detail="User is not an admin")

  # Remove admin privileges
  await conn.execute(
    "UPDATE users SET is_admin = FALSE WHERE owner_firebase_uid = $1",
    user_id
  )

  return {
    "success": True,
    "message": f"Admin privileges removed from user {user_id}",
    "removed_by": admin_uid,
  }


# ==================== REPORT MANAGEMENT ====================


@router.get("/reports", response_model=list[ReportWithDetails])
@limiter.limit("100/minute")
async def get_reports(
  request: Request,
  status: str = Query("pending"),  # pending, in_review, resolved, dismissed, all
  report_type: str | None = Query(None),
  page: int = Query(1, ge=1),
  page_size: int = Query(20, ge=1, le=100),
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Get list of reports with filtering

  Query params:
  - status: Filter by status (pending, in_review, resolved, dismissed, all)
  - report_type: Filter by type (spam, scam, inappropriate, etc.)
  - page: Page number
  - page_size: Items per page
  """
  offset = (page - 1) * page_size

  query = """
    SELECT
      r.*,
      reporter.email as reporter_email,
      reporter.name as reporter_name,
      reported.email as reported_user_email,
      reported.name as reported_user_name
    FROM reports r
    JOIN users reporter ON r.reporter_uid = reporter.owner_firebase_uid
    LEFT JOIN users reported ON r.reported_uid = reported.owner_firebase_uid
    WHERE 1=1
  """
  params = []
  param_idx = 1

  # Add status filter
  if status and status != "all":
    query += f" AND r.status = ${param_idx}"
    params.append(status)
    param_idx += 1

  # Add type filter
  if report_type:
    query += f" AND r.report_type = ${param_idx}"
    params.append(report_type)
    param_idx += 1

  query += " ORDER BY r.created_at DESC"
  query += f" LIMIT ${param_idx} OFFSET ${param_idx + 1}"
  params.extend([page_size, offset])

  reports = await conn.fetch(query, *params)

  return [ReportWithDetails(**dict(r)) for r in reports]


@router.get("/reports/{report_id}", response_model=ReportWithDetails)
@limiter.limit("100/minute")
async def get_report_details(
  request: Request,
  report_id: int,
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Get detailed information about a specific report
  """
  report = await conn.fetchrow(
    """
    SELECT
      r.*,
      reporter.email as reporter_email,
      reporter.name as reporter_name,
      reported.email as reported_user_email,
      reported.name as reported_user_name
    FROM reports r
    JOIN users reporter ON r.reporter_uid = reporter.owner_firebase_uid
    LEFT JOIN users reported ON r.reported_uid = reported.owner_firebase_uid
    WHERE r.id = $1
    """,
    report_id
  )

  if not report:
    raise HTTPException(status_code=404, detail="Report not found")

  return ReportWithDetails(**dict(report))


# RPC-style endpoint (not REST): Uses POST with action verb for clarity
@router.post("/reports/{report_id}/resolve")
@limiter.limit("30/hour")
async def resolve_report(
  request: Request,
  report_id: int,
  resolution: ReportResolve,
  admin_uid: str = Depends(verify_admin),
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Resolve a report and take action

  Body params:
  - action: Action to take (dismiss, warn, ban_user, delete_content, other)
  - notes: Optional notes about the resolution
  """
  # Get report details
  report = await conn.fetchrow(
    "SELECT * FROM reports WHERE id = $1",
    report_id
  )

  if not report:
    raise HTTPException(status_code=404, detail="Report not found")

  if report["status"] in ["resolved", "dismissed"]:
    raise HTTPException(
      status_code=400,
      detail="Report already resolved"
    )

  # Update report status
  await conn.execute(
    """
    UPDATE reports
    SET status = 'resolved',
      resolution_action = $1,
      resolution_notes = $2,
      resolved_by = $3,
      resolved_at = NOW()
    WHERE id = $4
    """,
    resolution.action,
    resolution.notes,
    admin_uid,
    report_id
  )

  # Take action based on resolution
  if resolution.action == "ban_user" and report["reported_uid"]:
    await conn.execute(
      """
      UPDATE users
      SET is_banned = TRUE,
        ban_reason = $1,
        banned_at = NOW()
      WHERE owner_firebase_uid = $2
      """,
      f"Banned due to report #{report_id}: {resolution.notes or 'Policy violation'}",
      report["reported_uid"]
    )

  # Note: delete_content action for listings not implemented
  # Would need to determine listing type (homes/books/caravans/clothes) first

  return {
    "success": True,
    "message": f"Report {report_id} resolved",
    "action_taken": resolution.action,
    "resolved_by": admin_uid,
  }


# RPC-style endpoint (not REST): Uses POST with action verb for clarity
@router.post("/reports/{report_id}/dismiss")
@limiter.limit("30/hour")
async def dismiss_report(
  request: Request,
  report_id: int,
  notes: str | None = None,
  admin_uid: str = Depends(verify_admin),
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Dismiss a report as invalid or not actionable

  Query params:
  - notes: Optional reason for dismissal
  """
  report = await conn.fetchrow(
    "SELECT id, status FROM reports WHERE id = $1",
    report_id
  )

  if not report:
    raise HTTPException(status_code=404, detail="Report not found")

  if report["status"] in ["resolved", "dismissed"]:
    raise HTTPException(status_code=400, detail="Report already resolved")

  await conn.execute(
    """
    UPDATE reports
    SET status = 'dismissed',
      resolution_action = 'dismiss',
      resolution_notes = $1,
      resolved_by = $2,
      resolved_at = NOW()
    WHERE id = $3
    """,
    notes,
    admin_uid,
    report_id
  )

  return {
    "success": True,
    "message": f"Report {report_id} dismissed",
  }


# ==================== SWAP MANAGEMENT ====================


@router.get("/swaps")
@limiter.limit("100/minute")
async def get_swaps(
  request: Request,
  status: str | None = Query(None),
  page: int = Query(1, ge=1),
  page_size: int = Query(20, ge=1, le=100),
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Get list of swaps for admin review

  Query params:
  - status: Filter by status (pending, accepted, completed, cancelled)
  - page: Page number
  - page_size: Items per page
  """
  offset = (page - 1) * page_size

  query = """
    SELECT
      s.swap_id as id,
      s.user_a_uid as requester_uid,
      s.user_b_uid as recipient_uid,
      s.status,
      s.initiated_at,
      s.accepted_at,
      s.completed_at,
      s.cancelled_at,
      user_a.email as requester_email,
      user_a.name as requester_name,
      user_b.email as recipient_email,
      user_b.name as recipient_name,
      s.listing_a_category || ' listing' as requested_item_title,
      s.listing_b_category || ' listing' as offered_item_title
    FROM swaps s
    JOIN users user_a ON s.user_a_uid = user_a.owner_firebase_uid
    JOIN users user_b ON s.user_b_uid = user_b.owner_firebase_uid
    WHERE 1=1
  """
  params = []
  param_idx = 1

  if status:
    query += f" AND s.status = ${param_idx}"
    params.append(status)
    param_idx += 1

  query += " ORDER BY s.initiated_at DESC"
  query += f" LIMIT ${param_idx} OFFSET ${param_idx + 1}"
  params.extend([page_size, offset])

  swaps = await conn.fetch(query, *params)
  swaps_dict = [dict(s) for s in swaps]
  for swap_dict in swaps_dict:
    swap_dict["id"] = str(swap_dict["id"])  # Convert swap_id to string if needed

  return [SwapManagement(**dict(s)) for s in swaps_dict]


# RPC-style endpoint (not REST): Uses POST with action verb for clarity
@router.post("/swaps/{swap_id}/cancel")
@limiter.limit("20/hour")
async def admin_cancel_swap(
  request: Request,
  swap_id: str,  # Changed from int to str since swap_id is UUID
  reason: str = Query(..., min_length=10),
  admin_uid: str = Depends(verify_admin),
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Admin force-cancel a swap

  Query params:
  - reason: Reason for cancellation (required)
  """
  swap = await conn.fetchrow(
    "SELECT swap_id, status FROM swaps WHERE swap_id = $1",
    swap_id
  )

  if not swap:
    raise HTTPException(status_code=404, detail="Swap not found")

  if swap["status"] in ["completed", "cancelled"]:
    raise HTTPException(
      status_code=400,
      detail="Cannot cancel a completed or already cancelled swap"
    )

  await conn.execute(
    """
    UPDATE swaps
    SET status = 'cancelled',
      cancelled_at = NOW(),
      cancellation_reason = $1
    WHERE swap_id = $2
    """,
    f"Admin cancelled: {reason}",
    swap_id
  )

  return {
    "success": True,
    "message": f"Swap {swap_id} cancelled by admin",
    "reason": reason,
    "cancelled_by": admin_uid,
  }


# ==================== ANALYTICS ====================


@router.get("/analytics/growth")
@limiter.limit("60/minute")
async def get_growth_analytics(
  request: Request,
  days: int = Query(30, ge=7, le=365),
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Get growth analytics for the specified time period

  Query params:
  - days: Number of days to analyze (default: 30, max: 365)
  """
  start_date = datetime.now() - timedelta(days=days)

  # Daily user signups
  user_signups = await conn.fetch(
    """
    SELECT
      DATE(created_at) as date,
      COUNT(*) as count
    FROM users
    WHERE created_at >= $1
    GROUP BY DATE(created_at)
    ORDER BY date
    """,
    start_date
  )

  # Daily swaps
  swap_activity = await conn.fetch(
    """
    SELECT
      DATE(initiated_at) as date,
      COUNT(*) as total,
      COUNT(*) FILTER (WHERE status = 'completed') as completed
    FROM swaps
    WHERE initiated_at >= $1
    GROUP BY DATE(initiated_at)
    ORDER BY date
    """,
    start_date
  )

  # Daily listings (aggregate across all listing types)
  listing_activity = await conn.fetch(
    """
    SELECT
      date,
      category,
      SUM(count) as count
    FROM (
      SELECT DATE(created_at) as date, 'homes' as category, COUNT(*) as count
      FROM homes WHERE created_at >= $1
      GROUP BY DATE(created_at)
      UNION ALL
      SELECT DATE(created_at) as date, 'books' as category, COUNT(*) as count
      FROM books WHERE created_at >= $1
      GROUP BY DATE(created_at)
      UNION ALL
      SELECT DATE(created_at) as date, 'caravans' as category, COUNT(*) as count
      FROM caravans WHERE created_at >= $1
      GROUP BY DATE(created_at)
      UNION ALL
      SELECT DATE(created_at) as date, 'clothes' as category, COUNT(*) as count
      FROM clothes WHERE created_at >= $1
      GROUP BY DATE(created_at)
    ) combined
    GROUP BY date, category
    ORDER BY date
    """,
    start_date, start_date, start_date, start_date
  )

  return {
    "period_days": days,
    "start_date": start_date.isoformat(),
    "user_signups": [dict(row) for row in user_signups],
    "swap_activity": [dict(row) for row in swap_activity],
    "listing_activity": [dict(row) for row in listing_activity],
  }


@router.get("/analytics/categories")
@limiter.limit("60/minute")
async def get_category_analytics(
  request: Request,
  conn: asyncpg.Connection = Depends(get_db_conn),
):
  """
  Get analytics by category

  Returns listing counts, swap counts, and success rates by category
  """
  # Get listing counts by category
  category_stats = await conn.fetch(
    """
    SELECT
      category,
      total_listings,
      active_listings,
      COALESCE(total_swaps, 0) as total_swaps,
      COALESCE(completed_swaps, 0) as completed_swaps,
      CASE
        WHEN COALESCE(total_swaps, 0) > 0
        THEN ROUND(100.0 * COALESCE(completed_swaps, 0) / total_swaps, 2)
        ELSE 0
      END as success_rate
    FROM (
      SELECT 'homes' as category,
             COUNT(*) as total_listings,
             COUNT(*) FILTER (WHERE status = 'published') as active_listings
      FROM homes
      UNION ALL
      SELECT 'books' as category,
             COUNT(*) as total_listings,
             COUNT(*) as active_listings
      FROM books
      UNION ALL
      SELECT 'caravans' as category,
             COUNT(*) as total_listings,
             COUNT(*) FILTER (WHERE status = 'published') as active_listings
      FROM caravans
      UNION ALL
      SELECT 'clothes' as category,
             COUNT(*) as total_listings,
             COUNT(*) as active_listings
      FROM clothes
    ) listing_counts
    LEFT JOIN (
      SELECT
        category,
        COUNT(*) as total_swaps,
        COUNT(*) FILTER (WHERE status = 'completed') as completed_swaps
      FROM swaps
      GROUP BY category
    ) swap_counts USING (category)
    ORDER BY total_listings DESC
    """
  )

  return [dict(row) for row in category_stats]
