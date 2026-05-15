"""Adobe Sign API integration — Integration Key + OAuth 2.0 e-signature flow.

Preferred setup for backend services:
  1. Log in to Adobe Sign admin console
  2. Account → Adobe Sign API → API Information → REST API → Integration Key
  3. Create a key with scope: agreement_read, agreement_write, agreement_send, library_read
  4. Set ADOBE_INTEGRATION_KEY in .env
  5. Create reusable templates in Adobe Sign admin, copy their library doc IDs
  6. Set ADOBE_TEMPLATE_CARRIER_AGREEMENT (and ADOBE_TEMPLATE_W9 if hosting W9)
"""
from __future__ import annotations

import httpx
import json
from typing import Optional
from ..settings import get_settings
from ..logging_service import get_logger

log = get_logger("3ll.adobe_sign")


class AdobeSignClient:
    """Handles Integration Key + OAuth 2.0 token exchange and e-signature API calls."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.adobe_api_endpoint or "https://api.na1.adobesign.com"
        self.client_id = self.settings.adobe_client_id
        self.client_secret = self.settings.adobe_client_secret
        self.account_id = self.settings.adobe_account_id

    def _auth_headers(self, access_token: str | None = None) -> dict:
        """Return Authorization headers, preferring Integration Key over OAuth token."""
        key = self.settings.adobe_integration_key or access_token
        if not key:
            raise ValueError("Adobe Sign not configured — set ADOBE_INTEGRATION_KEY in .env")
        return {"Authorization": f"Bearer {key}", "Accept": "application/json"}

    def send_template_for_signature(
        self,
        template_id: str,
        agreement_name: str,
        recipient_email: str,
        recipient_name: str,
        message: str = "Please review and sign this agreement.",
        access_token: str | None = None,
    ) -> Optional[dict]:
        """Send a saved Adobe Sign library template to a recipient for signature.

        This is the recommended flow — create the template once in Adobe Sign admin,
        then reference it by library_doc_id for every new agreement send.

        Returns {"id": agreement_id, "name": ..., "status": "OUT_FOR_SIGNATURE"} or None.
        """
        url = f"{self.base_url}/api/rest/v6/agreements"
        try:
            headers = self._auth_headers(access_token)
            headers["Content-Type"] = "application/json"
            payload = {
                "fileInfos": [{"libraryDocumentId": template_id}],
                "name": agreement_name,
                "participantSetsInfo": [{
                    "memberInfos": [{"email": recipient_email, "name": recipient_name}],
                    "order": 1,
                    "role": "SIGNER",
                }],
                "signatureType": "ESIGN",
                "state": "OUT_FOR_SIGNATURE",
                "message": message,
            }
            r = httpx.post(url, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            data = r.json()
            log.info("Adobe Sign agreement %s sent to %s", data.get("id"), recipient_email)
            return data
        except ValueError as e:
            log.error("Adobe Sign config error: %s", e)
            return None
        except httpx.HTTPStatusError as e:
            log.error("Adobe Sign API error %s: %s", e.response.status_code, e.response.text)
            return None
        except Exception as e:  # noqa: BLE001
            log.error("Adobe Sign send_template_for_signature failed: %s", e)
            return None

    def get_access_token(self, auth_code: str, redirect_uri: str) -> Optional[str]:
        """Exchange authorization code for access token (OAuth 2.0)."""
        if not self.client_id or not self.client_secret:
            log.error("Adobe Sign credentials not configured")
            return None

        url = f"{self.base_url}/oauth/token"
        payload = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
        }

        try:
            r = httpx.post(url, data=payload, timeout=10)
            r.raise_for_status()
            data = r.json()
            return data.get("access_token")
        except Exception as e:
            log.error(f"Failed to exchange auth code: {e}")
            return None

    def send_for_signature(
        self,
        access_token: str,
        agreement_name: str,
        file_data: bytes,
        file_name: str,
        recipient_email: str,
        recipient_name: str,
        message: str = "Please sign this agreement",
        redirect_uri: Optional[str] = None,
    ) -> Optional[dict]:
        """Send agreement to recipient for signature."""
        url = f"{self.base_url}/api/rest/v6/agreements"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        # Adobe Sign accepts documents as multipart form data
        files = {
            "File": (file_name, file_data, "application/pdf"),
        }

        data = {
            "agreementName": agreement_name,
            "participantSetsInfo": json.dumps([{
                "memberInfos": [{
                    "email": recipient_email,
                    "label": recipient_name,
                }],
                "order": 1,
                "role": "SIGNER",
            }]),
            "signatureType": "ESIGN",
            "state": "OUT_FOR_SIGNATURE",
            "message": message,
        }

        # Add redirect URI if provided (for signed doc flow)
        if redirect_uri:
            data["redirectUrl"] = redirect_uri

        try:
            r = httpx.post(url, headers=headers, files=files, data=data, timeout=30)
            r.raise_for_status()
            response = r.json()
            log.info(f"Sent agreement {response.get('id')} to {recipient_email}")
            return response
        except httpx.HTTPStatusError as e:
            log.error(f"Adobe Sign API error: {e.response.status_code} — {e.response.text}")
            return None
        except Exception as e:
            log.error(f"Failed to send agreement for signature: {e}")
            return None

    def get_agreement_status(
        self,
        access_token: str,
        agreement_id: str,
    ) -> Optional[dict]:
        """Check the status of an agreement."""
        url = f"{self.base_url}/api/rest/v6/agreements/{agreement_id}"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            r = httpx.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.error(f"Failed to get agreement status: {e}")
            return None

    def get_signed_document(
        self,
        access_token: str,
        agreement_id: str,
    ) -> Optional[bytes]:
        """Download the signed document PDF."""
        url = f"{self.base_url}/api/rest/v6/agreements/{agreement_id}/combinedDocument"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/pdf",
        }

        try:
            r = httpx.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            return r.content
        except Exception as e:
            log.error(f"Failed to download signed document: {e}")
            return None

    def get_authorization_url(
        self,
        client_id: Optional[str] = None,
        redirect_uri: str = "http://localhost:8080/api/adobe/callback",
        scope: str = "agreement_read agreement_write agreement_send user_read",
    ) -> str:
        """Generate OAuth 2.0 authorization URL."""
        cid = client_id or self.client_id
        if not cid:
            log.error("Client ID not configured")
            return ""

        url = (
            f"{self.base_url}/oauth/authorize?"
            f"response_type=code&"
            f"client_id={cid}&"
            f"redirect_uri={redirect_uri}&"
            f"scope={scope}"
        )
        return url


# Singleton instance
_client: Optional[AdobeSignClient] = None


def get_adobe_sign_client() -> AdobeSignClient:
    """Get or create Adobe Sign client."""
    global _client
    if _client is None:
        _client = AdobeSignClient()
    return _client
