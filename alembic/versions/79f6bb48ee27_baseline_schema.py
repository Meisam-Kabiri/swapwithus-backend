"""baseline schema

Revision ID: 79f6bb48ee27
Revises:
Create Date: 2025-12-16 14:14:07.294176

This baseline migration contains the complete schema from migration/ folder.
For existing databases: use 'alembic stamp head' to mark as applied without running.
For new databases: use 'alembic upgrade head' to create all tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79f6bb48ee27'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create all tables from baseline schema.

    This represents the complete schema from migration/ folder as of 2025-12-16.
    Schema includes: users, homes, images, favorites, books, caravans, clothes, swaps, reviews.
    """
    op.execute("""
    -- From _001_create_users.py
    CREATE TABLE IF NOT EXISTS users (
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

          owner_firebase_uid VARCHAR(128) PRIMARY KEY,
          email VARCHAR(255) NOT NULL UNIQUE,
          name VARCHAR(200),
          profile_image VARCHAR(500),

          phone_country_code VARCHAR(10),
          phone_number VARCHAR(50),
          is_email_verified BOOLEAN DEFAULT FALSE,

          linkedin_url VARCHAR(255),
          instagram_id VARCHAR(100),
          facebook_id VARCHAR(100),

          is_banking_verified BOOLEAN DEFAULT FALSE,
          is_phone_verified BOOLEAN DEFAULT FALSE,

          -- Review and swap statistics
          total_reviews INTEGER DEFAULT 0,
          average_rating DECIMAL(3,2) DEFAULT 0.00,
          total_swaps_completed INTEGER DEFAULT 0,
          trust_score INTEGER DEFAULT 0,
          last_swap_at TIMESTAMPTZ
      );

    -- From _002_create_homes.py
    CREATE TABLE IF NOT EXISTS homes (
          -- Primary key and timestamps
          listing_id UUID PRIMARY KEY,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

          -- Owner (from frontend user data)
          owner_firebase_uid VARCHAR(100) NOT NULL,
          email VARCHAR(255) NULL,
          name VARCHAR(200) NULL,
          profile_image VARCHAR(500) NULL,

          -- Step 1: Property Type
          accommodation_type VARCHAR(20) NULL,
          property_type VARCHAR(30) NULL,

          -- Step 2: Capacity & Layout
          max_guests INTEGER NULL,
          bedrooms INTEGER NULL,

          size_m2 NUMERIC(10, 2) NULL,
          surroundings_type VARCHAR(30) NULL,

          -- Step 3: Location
          country VARCHAR(20) NOT NULL,
          city VARCHAR(50) NOT NULL,
          street_address VARCHAR(100) NULL,
          postal_code VARCHAR(20) NULL,
          latitude DECIMAL(10, 8) NULL,
          longitude DECIMAL(11, 8) NULL,
          privacy_radius INTEGER NULL,



          -- Step 5: House Rules
          house_rules TEXT[] DEFAULT '{}',
          main_residence BOOLEAN NULL,

          -- Step 6: Transport & Car Swap
          open_to_car_swap BOOLEAN DEFAULT FALSE,
          require_car_swap_match BOOLEAN DEFAULT FALSE,
          car_details JSONB NULL,

          -- Step 7:  Available Amenities
          amenities JSONB NULL,
          accessibility_features TEXT[] DEFAULT '{}',
          parking_type VARCHAR(20) NULL,

          -- Step 8: Availability
          is_flexible BOOLEAN NULL,
          available_from DATE NULL,
          available_until DATE NULL,

          -- Step 9: Title and Description
          title VARCHAR(100) NOT NULL,
          description TEXT NULL,

          -- Status
          status VARCHAR(20) DEFAULT 'draft',

          FOREIGN KEY (owner_firebase_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE
      );

       -- Indexes for homes
      CREATE INDEX IF NOT EXISTS idx_homes_owner ON homes(owner_firebase_uid);
      CREATE INDEX IF NOT EXISTS idx_homes_country_city ON homes(country, city);
      CREATE INDEX IF NOT EXISTS idx_homes_created_at ON homes(created_at DESC);

    -- From _003_create_images.py
    CREATE TABLE IF NOT EXISTS images (

          owner_firebase_uid VARCHAR(100) NOT NULL,
          listing_id UUID NOT NULL,
          category VARCHAR(20) NOT NULL,
          public_url VARCHAR(500) NOT NULL,
          cdn_url VARCHAR(500) NOT NULL,
          tag VARCHAR(100) NULL,
          caption TEXT NULL,
          sort_order INTEGER DEFAULT 0,
          is_hero BOOLEAN DEFAULT FALSE,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW(),

          FOREIGN KEY (owner_firebase_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE,
          UNIQUE (listing_id, public_url)

        );

        -- Indexes for images
        CREATE INDEX IF NOT EXISTS idx_images_listing ON images(listing_id);
        CREATE INDEX IF NOT EXISTS idx_images_owner ON images(owner_firebase_uid);
        CREATE INDEX IF NOT EXISTS idx_images_category_listing ON images(category, listing_id);
        CREATE INDEX IF NOT EXISTS idx_images_sort_order ON images(listing_id, sort_order);

    -- From _004_create_favorites.py
    CREATE TABLE IF NOT EXISTS favorites (
      owner_firebase_uid  VARCHAR(100) NOT NULL REFERENCES users(owner_firebase_uid)  ON DELETE CASCADE,
      listing_id  UUID NOT NULL REFERENCES homes(listing_id) ON DELETE CASCADE,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY (owner_firebase_uid, listing_id)
    );

    -- useful for counts & reverse lookups
    CREATE INDEX IF NOT EXISTS idx_favorites_listing ON favorites(listing_id);

    -- From _005_create_books.py
    CREATE TABLE IF NOT EXISTS books (
          -- Primary key and timestamps
          listing_id UUID PRIMARY KEY,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

          -- Owner (from frontend user data)
          owner_firebase_uid VARCHAR(100) NOT NULL,

          -- Step 1: Property Type
          title VARCHAR(100) NOT NULL,
          author VARCHAR(100) NOT NULL,
          format VARCHAR(20) NOT NULL,
          language VARCHAR(20) NOT NULL,
          condition VARCHAR(20) NULL,
          description TEXT NULL,
          publication_year INTEGER NULL,

          -- Step 2: Capacity & Layout
          country VARCHAR(100) NOT NULL,
          city VARCHAR(100) NOT NULL,
          exchange_method VARCHAR(30) NOT NULL,
          exchange_mode VARCHAR(30) NOT NULL,

          -- Step 3: Location
          genre_tags TEXT[] default '{}',


          FOREIGN KEY (owner_firebase_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE
      );

       -- Indexes for books
      CREATE INDEX IF NOT EXISTS idx_books_owner ON books(owner_firebase_uid);
      CREATE INDEX IF NOT EXISTS idx_books_country_city ON books(country, city);
      CREATE INDEX IF NOT EXISTS idx_books_created_at ON books(created_at DESC);

    -- From _006_create_caravans.py
    CREATE TABLE IF NOT EXISTS caravans (
          listing_id UUID PRIMARY KEY,
          owner_firebase_uid VARCHAR(100) NOT NULL,

          -- Basic Info
          title VARCHAR(200) NOT NULL,
          vehicle_type VARCHAR(20) NOT NULL CHECK (vehicle_type IN ('caravan', 'campervan', 'motorhome')),

          -- Location
          country VARCHAR(100) NOT NULL,
          city VARCHAR(100) NOT NULL,

          -- Capacity
          max_guests INTEGER NOT NULL CHECK (max_guests > 0 AND max_guests <= 20),

          -- Exchange Details
          exchange_method VARCHAR(30) NOT NULL CHECK (exchange_method IN ('pickup_only', 'delivery_possible', 'both')),

          -- Vehicle-specific
          tow_requirement VARCHAR(100),
          drive_license_req VARCHAR(50),

          -- Vehicle Details
          year INTEGER CHECK (year >= 1950 AND year <= 2100),
          make VARCHAR(100),
          model VARCHAR(100),
          condition VARCHAR(20) CHECK (condition IN ('new', 'excellent', 'good', 'fair', 'needs_work')),
          registration_country VARCHAR(100),

          -- For motorized vehicles
          fuel_type VARCHAR(20) CHECK (fuel_type IN ('diesel', 'petrol', 'electric', 'hybrid')),
          transmission VARCHAR(20) CHECK (transmission IN ('manual', 'automatic')),
          mileage_km INTEGER CHECK (mileage_km >= 0),

          -- Dimensions & weight
          length_meters DECIMAL(4,1) CHECK (length_meters > 0 AND length_meters <= 30),
          weight_kg INTEGER CHECK (weight_kg > 0),

          -- Sleeping
          bed_layout VARCHAR(200),
          bed_count INTEGER CHECK (bed_count >= 0 AND bed_count <= 20),

          -- Amenities & Features
          amenities TEXT[] DEFAULT '{}',
          power_source TEXT[] DEFAULT '{}',
          water_system VARCHAR(200),
          winterized BOOLEAN,

          -- Rules & Policies
          pet_allowed BOOLEAN,
          smoking_allowed BOOLEAN,
          insurance_included BOOLEAN,
          deposit_required INTEGER CHECK (deposit_required >= 0),

          -- Location & Availability
          location_note VARCHAR(500),
          available_from DATE,
          available_until DATE,
          delivery_radius_km INTEGER CHECK (delivery_radius_km >= 0),

          -- Description
          description TEXT,

          -- User info (duplicated for convenience)
          email VARCHAR(255),
          name VARCHAR(100),
          profile_image VARCHAR(500),

          -- Status
          status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),

          -- Timestamps
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW(),

          FOREIGN KEY (owner_firebase_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE
        );

        -- Indexes for caravans
        CREATE INDEX IF NOT EXISTS idx_caravans_owner ON caravans(owner_firebase_uid);
        CREATE INDEX IF NOT EXISTS idx_caravans_location ON caravans(country, city);
        CREATE INDEX IF NOT EXISTS idx_caravans_vehicle_type ON caravans(vehicle_type);
        CREATE INDEX IF NOT EXISTS idx_caravans_status ON caravans(status);
        CREATE INDEX IF NOT EXISTS idx_caravans_created_at ON caravans(created_at DESC);

    -- From _007_create_clothes.py
    CREATE TABLE IF NOT EXISTS clothes (
          listing_id UUID PRIMARY KEY,
          owner_firebase_uid VARCHAR(100) NOT NULL,

          -- Basic Info
          title VARCHAR(200) NOT NULL,
          clothing_category VARCHAR(30) NOT NULL CHECK (clothing_category IN (
            'tshirt', 'shirt', 'dress', 'trousers', 'jeans', 'coat', 'jacket',
            'sweater', 'hoodie', 'sportswear', 'shoes', 'bag', 'accessory', 'other'
          )),
          size VARCHAR(20) NOT NULL,
          condition VARCHAR(20) NOT NULL CHECK (condition IN ('new', 'like_new', 'very_good', 'good', 'used')),

          -- Location
          city VARCHAR(100) NOT NULL,
          country VARCHAR(100) NOT NULL,

          -- Exchange Details
          exchange_method VARCHAR(30) NOT NULL CHECK (exchange_method IN ('pickup_only', 'shipping_possible', 'both')),

          -- Optional Details
          gender VARCHAR(20) CHECK (gender IN ('women', 'men', 'unisex', 'kids')),
          brand VARCHAR(100),
          color VARCHAR(50),
          material VARCHAR(200),
          season VARCHAR(20) CHECK (season IN ('all', 'spring', 'summer', 'autumn', 'winter')),
          kids_age_range VARCHAR(50),
          fit VARCHAR(20) CHECK (fit IN ('regular', 'oversized', 'slim')),
          defects VARCHAR(500),

          -- Description
          description TEXT,

          -- User info (duplicated for convenience)
          email VARCHAR(255),
          name VARCHAR(100),
          profile_image VARCHAR(500),


          -- Timestamps
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW(),

          FOREIGN KEY (owner_firebase_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE
        );

        -- Indexes for clothes
        CREATE INDEX IF NOT EXISTS idx_clothes_owner ON clothes(owner_firebase_uid);
        CREATE INDEX IF NOT EXISTS idx_clothes_location ON clothes(country, city);
        CREATE INDEX IF NOT EXISTS idx_clothes_category ON clothes(clothing_category);
        CREATE INDEX IF NOT EXISTS idx_clothes_size ON clothes(size);
        CREATE INDEX IF NOT EXISTS idx_clothes_gender ON clothes(gender);
        CREATE INDEX IF NOT EXISTS idx_clothes_created_at ON clothes(created_at);

    -- From _008_create_swaps.py
    CREATE TABLE IF NOT EXISTS swaps (
          swap_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          category VARCHAR(50) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),


          -- Participants (users involved in the swap)
          user_a_uid VARCHAR(128) NOT NULL,
          user_b_uid VARCHAR(128) NOT NULL,

          -- Listings being swapped
          listing_a_id UUID NOT NULL,
          listing_b_id UUID NOT NULL,

          -- Listing categories (for easier querying)
          listing_a_category VARCHAR(50),
          listing_b_category VARCHAR(50),

          -- Swap status: 'pending', 'accepted', 'completed', 'cancelled'
          status VARCHAR(50) NOT NULL DEFAULT 'pending',

          -- Reference to the conversation
          conversation_id VARCHAR(128),

          -- Completion tracking (both users must confirm receipt)
          user_a_confirmed BOOLEAN DEFAULT FALSE,
          user_b_confirmed BOOLEAN DEFAULT FALSE,
          completed_at TIMESTAMPTZ,

          -- Important timestamps
          initiated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          accepted_at TIMESTAMPTZ,
          cancelled_at TIMESTAMPTZ,

          -- Cancellation details
          cancelled_by VARCHAR(128) REFERENCES users(owner_firebase_uid),
          cancellation_reason TEXT,

          user_a_deleted BOOLEAN DEFAULT FALSE,
          user_b_deleted BOOLEAN DEFAULT FALSE,
          listing_a_deleted BOOLEAN DEFAULT FALSE,
          listing_b_deleted BOOLEAN DEFAULT FALSE,


          -- Check constraints
          CONSTRAINT different_users CHECK (user_a_uid != user_b_uid),
          CONSTRAINT different_listings CHECK (listing_a_id != listing_b_id),
          CONSTRAINT valid_status CHECK (status IN ('pending', 'accepted', 'completed', 'cancelled'))
        );

        -- Indexes for efficient querying
        CREATE INDEX IF NOT EXISTS idx_swaps_user_a ON swaps(user_a_uid);
        CREATE INDEX IF NOT EXISTS idx_swaps_user_b ON swaps(user_b_uid);
        CREATE INDEX IF NOT EXISTS idx_swaps_status ON swaps(status);
        CREATE INDEX IF NOT EXISTS idx_swaps_conversation ON swaps(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_swaps_completed_at ON swaps(completed_at);

        -- Index for finding swaps between two users
        CREATE INDEX IF NOT EXISTS idx_swaps_users ON swaps(user_a_uid, user_b_uid);

    -- From _009_create_reviews.py
    CREATE TABLE IF NOT EXISTS reviews (
          review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

          -- Who is reviewing whom
          reviewer_uid VARCHAR(128) NOT NULL REFERENCES users(owner_firebase_uid) ON DELETE CASCADE,
          reviewee_uid VARCHAR(128) NOT NULL REFERENCES users(owner_firebase_uid) ON DELETE CASCADE,

          -- Associated swap (ensures review is from completed swap)
          swap_id UUID NOT NULL REFERENCES swaps(swap_id) ON DELETE CASCADE,

          -- Overall rating (1-5 stars)
          rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),

          -- Review comment (optional)
          comment TEXT,

          -- Detailed ratings (optional, 1-5 stars each)
          communication_rating INTEGER CHECK (communication_rating >= 1 AND communication_rating <= 5),
          item_condition_rating INTEGER CHECK (item_condition_rating >= 1 AND item_condition_rating <= 5),
          timeliness_rating INTEGER CHECK (timeliness_rating >= 1 AND timeliness_rating <= 5),

          -- Prevent reviewing yourself
          CONSTRAINT no_self_review CHECK (reviewer_uid != reviewee_uid),

          -- Prevent duplicate reviews (one review per swap per user)
          UNIQUE(reviewer_uid, swap_id)
        );

        -- Indexes for efficient querying
        CREATE INDEX IF NOT EXISTS idx_reviews_reviewer ON reviews(reviewer_uid);
        CREATE INDEX IF NOT EXISTS idx_reviews_reviewee ON reviews(reviewee_uid);
        CREATE INDEX IF NOT EXISTS idx_reviews_swap ON reviews(swap_id);
        CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating);
        CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at DESC);
    """)


def downgrade() -> None:
    """Drop all tables in reverse dependency order"""
    op.execute("""
        DROP TABLE IF EXISTS reviews CASCADE;
        DROP TABLE IF EXISTS swaps CASCADE;
        DROP TABLE IF EXISTS favorites CASCADE;
        DROP TABLE IF EXISTS clothes CASCADE;
        DROP TABLE IF EXISTS caravans CASCADE;
        DROP TABLE IF EXISTS books CASCADE;
        DROP TABLE IF EXISTS images CASCADE;
        DROP TABLE IF EXISTS homes CASCADE;
        DROP TABLE IF EXISTS users CASCADE;
    """)
