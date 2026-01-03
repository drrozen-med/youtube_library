"""
Authentication Helper
=====================
Handles service account authentication for YouTube API.
"""

import os
from typing import Optional
from google.auth import default
from google.auth.transport.requests import Request
from google.oauth2 import service_account
import requests


def get_access_token(service_account_path: Optional[str] = None) -> str:
    """
    Get OAuth2 access token using service account or default credentials.
    
    Args:
        service_account_path: Path to service account JSON file (or from env)
        
    Returns:
        Access token string
    """
    # Check environment variable if not provided
    if not service_account_path:
        service_account_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH")
    
    if service_account_path and os.path.exists(service_account_path):
        # Use specific service account
        credentials = service_account.Credentials.from_service_account_file(
            service_account_path,
            scopes=['https://www.googleapis.com/auth/youtube.readonly']
        )
        credentials.refresh(Request())
        return credentials.token
    else:
        # Try default credentials (ADC)
        try:
            credentials, _ = default(scopes=['https://www.googleapis.com/auth/youtube.readonly'])
            credentials.refresh(Request())
            return credentials.token
        except Exception:
            raise RuntimeError(
                f"No valid credentials found. Set GOOGLE_SERVICE_ACCOUNT_PATH or use gcloud auth application-default login"
            )


def make_authenticated_request(url: str, params: dict, service_account_path: Optional[str] = None) -> dict:
    """
    Make authenticated request to YouTube API using service account.
    
    Args:
        url: Full API URL
        params: Query parameters
        service_account_path: Path to service account JSON file
        
    Returns:
        JSON response
    """
    token = get_access_token(service_account_path)
    headers = {'Authorization': f'Bearer {token}'}
    
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

