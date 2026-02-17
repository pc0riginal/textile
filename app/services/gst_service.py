"""
GST Verification Service
Fetches GST details from the official Indian government portal without paid APIs.

Based on: https://github.com/sivunq/fetch-GST-details-without-using-any-paid-API

Flow:
1. Get captcha image and CaptchaCookie from GST portal
2. User solves captcha
3. Submit GSTIN + captcha + cookie to get company details
"""

import httpx
import base64
from typing import Optional, Dict, Any
import re
import random


# GST Portal URLs (from working implementation)
GST_CAPTCHA_URL = "https://services.gst.gov.in/services/captcha"
GST_DETAILS_URL = "https://services.gst.gov.in/services/api/search/taxpayerDetails"

# Regex patterns
GST_REGEX = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z0-9A-J]{1}[0-9A-Z]{1}$', re.IGNORECASE)
CAPTCHA_REGEX = re.compile(r'^[0-9]{6}$')

# Error codes from GST portal
INVALID_GST_CODE = "SWEB_9035"
INVALID_CAPTCHA_CODE = "SWEB_9000"

# Cookie name used by GST portal
CAPTCHA_COOKIE_NAME = "CaptchaCookie"


class GSTVerificationError(Exception):
    """Custom exception for GST verification errors"""
    pass


def _validate_gst_checksum(gst_number: str) -> bool:
    """
    Validate GST number checksum (last character).
    Algorithm from the working TypeScript implementation.
    """
    if len(gst_number) != 15:
        return False
    
    gst_substring = gst_number[:14].upper()
    cp_chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    mod = len(cp_chars)
    factor = 2
    sum_val = 0
    
    # Process characters from right to left
    for char in reversed(gst_substring):
        code_point = cp_chars.find(char)
        if code_point == -1:
            return False
        
        digit = factor * code_point
        factor = 1 if factor == 2 else 2
        digit = (digit // mod) + (digit % mod)
        sum_val += digit
    
    check_code_point = (mod - (sum_val % mod)) % mod
    expected_checksum = cp_chars[check_code_point]
    
    return gst_number[14].upper() == expected_checksum


def validate_gstin_format(gstin: str) -> bool:
    """
    Validate GSTIN format and checksum.
    
    Format: 22AAAAA0000A1Z5
    - First 2 digits: State code (01-38)
    - Next 10 characters: PAN
    - 13th character: Entity number (1-9, A-Z)
    - 14th character: Z or alphanumeric
    - 15th character: Checksum
    """
    if not gstin or len(gstin) != 15:
        return False
    
    if not GST_REGEX.match(gstin):
        return False
    
    # Validate checksum
    return _validate_gst_checksum(gstin)


async def get_gst_captcha() -> Dict[str, Any]:
    """
    Fetch captcha image from GST portal.
    
    Returns:
        dict: {
            "success": True/False,
            "captcha_image": "data:image/png;base64,...",
            "captcha_cookie": "cookie_value",
            "error": "error_message" (if failed)
        }
    """
    try:
        # Add random parameter to prevent caching
        url = f"{GST_CAPTCHA_URL}?rnd={random.random()}"
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://services.gst.gov.in/",
                }
            )
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to fetch captcha. Status: {response.status_code}"
                }
            
            # Extract CaptchaCookie from Set-Cookie header
            captcha_cookie = None
            set_cookie_header = response.headers.get("set-cookie", "")
            
            if set_cookie_header:
                # Parse Set-Cookie header to find CaptchaCookie
                cookie_parts = set_cookie_header.split(";")
                for part in cookie_parts:
                    if "=" in part:
                        key, value = part.split("=", 1)
                        if key.strip() == CAPTCHA_COOKIE_NAME:
                            captcha_cookie = value.strip()
                            break
            
            if not captcha_cookie:
                return {
                    "success": False,
                    "error": "No CaptchaCookie received from GST portal",
                    "debug_info": {
                        "status_code": response.status_code,
                        "set_cookie_header": set_cookie_header,
                        "all_cookies": dict(response.cookies)
                    }
                }
            
            # Check if response is an image
            content_type = response.headers.get("content-type", "")
            if "image" not in content_type:
                return {
                    "success": False,
                    "error": f"Expected image but got {content_type}",
                    "debug_info": {
                        "content_type": content_type,
                        "content_preview": response.text[:200] if len(response.content) < 1000 else "Binary data"
                    }
                }
            
            # Convert image to base64
            captcha_base64 = base64.b64encode(response.content).decode('utf-8')
            
            return {
                "success": True,
                "captcha_image": f"data:image/png;base64,{captcha_base64}",
                "captcha_cookie": captcha_cookie
            }
            
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Request timeout. GST portal may be slow or unavailable."
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error fetching captcha: {str(e)}"
        }


async def verify_gstin(
    gstin: str,
    captcha: str,
    captcha_cookie: str
) -> Dict[str, Any]:
    """
    Verify GSTIN and fetch company details from GST portal.
    
    Args:
        gstin: 15-character GST identification number
        captcha: User-solved captcha text (6 digits)
        captcha_cookie: CaptchaCookie value from get_gst_captcha()
    
    Returns:
        dict: {
            "success": True/False,
            "data": {
                "legal_name": "Company Legal Name",
                "trade_name": "Trade Name",
                "gstin": "15AAAAA0000A1Z5",
                "status": "Active/Cancelled",
                "address": "Full address",
                "business_nature": "Business nature",
                "company_type": "Company type",
                "state_code": "XX"
            },
            "error": "error_message" (if failed)
        }
    """
    # Validate GSTIN format and checksum
    if not validate_gstin_format(gstin):
        return {
            "success": False,
            "error": "Invalid GSTIN format or checksum"
        }
    
    # Validate captcha format (6 digits)
    if not CAPTCHA_REGEX.match(captcha):
        return {
            "success": False,
            "error": "Invalid captcha format. Must be 6 digits."
        }
    
    if not captcha_cookie:
        return {
            "success": False,
            "error": "Captcha cookie is required"
        }
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Prepare payload (exactly as in TypeScript implementation)
            payload = {
                "gstin": gstin.upper(),
                "captcha": captcha
            }
            
            # Set cookie header (exactly as in TypeScript implementation)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Content-Type": "application/json",
                "Origin": "https://services.gst.gov.in",
                "Referer": "https://services.gst.gov.in/",
                "Cookie": f"{CAPTCHA_COOKIE_NAME}={captcha_cookie}"
            }
            
            # Make POST request to GST details API
            response = await client.post(
                GST_DETAILS_URL,
                json=payload,
                headers=headers
            )
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"GST portal returned status {response.status_code}",
                    "debug_info": {
                        "status": response.status_code,
                        "response_text": response.text[:500]
                    }
                }
            
            # Parse JSON response
            gst_data = response.json()
            
            # Check for errors first
            error_code = gst_data.get("errorCode")
            
            if error_code == INVALID_GST_CODE:
                return {
                    "success": False,
                    "error": "Invalid GSTIN. Please check the number."
                }
            elif error_code == INVALID_CAPTCHA_CODE:
                return {
                    "success": False,
                    "error": "Invalid captcha. Please try again."
                }
            elif error_code:
                # Some other error code
                return {
                    "success": False,
                    "error": f"GST portal error: {error_code}"
                }
            
            # Check if we have the required data fields
            if not gst_data.get("lgnm"):
                return {
                    "success": False,
                    "error": "No data found for this GSTIN"
                }
            
            # Extract details (as per TypeScript implementation)
            address_data = gst_data.get("pradr", {})
            full_address = address_data.get("adr", "")
            
            # Parse address to extract city, state, and pincode
            # Address format: "..., City, District, State, Pincode"
            city = ""
            state = ""
            pincode = ""
            
            if full_address:
                # Split by comma and get last parts
                parts = [p.strip() for p in full_address.split(',')]
                
                # Pincode is usually the last part (6 digits)
                if len(parts) > 0:
                    last_part = parts[-1].strip()
                    if last_part.isdigit() and len(last_part) == 6:
                        pincode = last_part
                        parts = parts[:-1]  # Remove pincode from parts
                
                # State is usually second to last
                if len(parts) >= 2:
                    state = parts[-1].strip()
                    city = parts[-2].strip()
                elif len(parts) == 1:
                    state = parts[0].strip()
            
            # Extract state code from GSTIN (first 2 digits)
            state_code = gstin[:2]
            
            gst_details = {
                "legal_name": gst_data.get("lgnm", ""),
                "trade_name": gst_data.get("tradeNam", ""),
                "gstin": gstin.upper(),
                "status": gst_data.get("sts", ""),
                "address": full_address,
                "city": city,
                "state": state,
                "pincode": pincode,
                "business_nature": gst_data.get("nba", []),
                "company_type": gst_data.get("ctb", ""),
                "state_code": state_code,
                "registration_date": gst_data.get("rgdt", ""),
                "taxpayer_type": gst_data.get("dty", ""),
            }
            
            return {
                "success": True,
                "data": gst_details
            }
            
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Request timeout. GST portal may be slow or unavailable."
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error verifying GSTIN: {str(e)}"
        }


def extract_pan_from_gstin(gstin: str) -> Optional[str]:
    """Extract PAN from GSTIN (characters 3-12)."""
    if validate_gstin_format(gstin):
        return gstin[2:12].upper()
    return None


def extract_state_code_from_gstin(gstin: str) -> Optional[str]:
    """Extract state code from GSTIN (first 2 digits)."""
    if validate_gstin_format(gstin):
        return gstin[0:2]
    return None
