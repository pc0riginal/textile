"""
GST Verification Router
Provides endpoints for GST number verification and captcha handling.
"""

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app import TEMPLATES_DIR
from app.dependencies import get_current_user
from app.services import gst_service

router = APIRouter(prefix="/gst", tags=["gst"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/api/captcha")
async def get_gst_captcha_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get captcha image for GST verification.
    
    Returns:
        {
            "success": true,
            "captcha_image": "data:image/png;base64,...",
            "captcha_cookie": "session_cookie_value"
        }
    """
    result = await gst_service.get_gst_captcha()
    return JSONResponse(content=result)


@router.post("/api/verify")
async def verify_gstin(
    request: Request,
    gstin: str = Form(...),
    captcha: str = Form(...),
    captcha_cookie: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Verify GSTIN and fetch company details.
    
    Args:
        gstin: 15-character GST identification number
        captcha: User-solved captcha text
        captcha_cookie: Session cookie from captcha endpoint
    
    Returns:
        {
            "success": true,
            "data": {
                "legal_name": "Company Name",
                "trade_name": "Trade Name",
                "gstin": "15AAAAA0000A1Z5",
                "status": "Active",
                "registration_date": "01/01/2020",
                "taxpayer_type": "Regular",
                "constitution": "Private Limited Company",
                "address": "Full address",
                "state": "Maharashtra",
                "state_code": "27",
                "pincode": "400001",
                ...
            }
        }
    """
    result = await gst_service.verify_gstin(
        gstin=gstin.strip(),
        captcha=captcha.strip(),
        captcha_cookie=captcha_cookie.strip()
    )
    
    return JSONResponse(content=result)


@router.post("/api/validate-format")
async def validate_gstin_format_endpoint(
    request: Request,
    gstin: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Validate GSTIN format without API call (client-side validation).
    
    Returns:
        {
            "valid": true/false,
            "pan": "AAAAA0000A" (if valid),
            "state_code": "27" (if valid)
        }
    """
    is_valid = gst_service.validate_gstin_format(gstin)
    
    response = {"valid": is_valid}
    
    if is_valid:
        response["pan"] = gst_service.extract_pan_from_gstin(gstin)
        response["state_code"] = gst_service.extract_state_code_from_gstin(gstin)
    
    return JSONResponse(content=response)


@router.get("/api/test-connection")
async def test_gst_portal_connection(
    current_user: dict = Depends(get_current_user)
):
    """
    Test connection to GST portal and return debug information.
    This helps diagnose connectivity issues.
    """
    import httpx
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Test captcha endpoint
            response = await client.get(
                "https://services.gst.gov.in/services/api/captcha",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "image/png,image/*;q=0.8,*/*;q=0.5",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://services.gst.gov.in/services/searchtp",
                }
            )
            
            return JSONResponse(content={
                "success": True,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "cookies": {name: value for name, value in response.cookies.items()},
                "content_type": response.headers.get("content-type"),
                "content_length": len(response.content),
                "message": "Connection successful"
            })
    except Exception as e:
        return JSONResponse(content={
            "success": False,
            "error": str(e),
            "message": "Failed to connect to GST portal"
        })
