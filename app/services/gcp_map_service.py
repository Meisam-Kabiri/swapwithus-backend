from typing import Tuple, Optional
import os
import logging
import aiohttp

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def geocode_address(address: str) -> Tuple[Optional[float], Optional[float]]:
    """Convert address to coordinates using Google Geocoding API"""
    try:
        if not address or not address.strip():
            return None, None

        # Get API key from environment
        api_key = os.getenv("GOOGLE_GEOCODING_API_KEY")
        if not api_key:
            logger.warning("Google Geocoding API key not found")
            return None, None

        # Prepare API request
        base_url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address.strip(),
            "key": api_key,
            "region": "US",  # Optional: bias results to a specific region
        }

        # Make async HTTP request
        timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(base_url, params=params) as response:
                if response.status != 200:
                    logger.error(f"Geocoding API returned status {response.status}")
                    return None, None

                data = await response.json()

        # Parse response
        if data.get("status") == "OK" and data.get("results"):
            location = data["results"][0]["geometry"]["location"]
            latitude = location["lat"]
            longitude = location["lng"]

            logger.info(f"Successfully geocoded address: {address}")
            return latitude, longitude

        elif data.get("status") == "ZERO_RESULTS":
            logger.warning(f"No results found for address: {address}")
            return None, None

        else:
            logger.error(
                f"Geocoding failed: {data.get('status')} - {data.get('error_message', 'Unknown error')}"
            )
            return None, None

    except aiohttp.ClientError as e:
        logger.error(f"HTTP request error during geocoding: {e}")
        return None, None

    except Exception as e:
        logger.error(f"Geocoding error: {e}")
        return None, None
