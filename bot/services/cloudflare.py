"""Cloudflare API wrapper using httpx async client."""

import logging
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

RecordType = Literal["A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA", "PTR"]

VALID_RECORD_TYPES: set[str] = {"A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA", "PTR"}


class CloudflareAPIError(Exception):
    """Custom exception for Cloudflare API errors."""

    def __init__(self, message: str, status_code: int | None = None, errors: list | None = None):
        self.message = message
        self.status_code = status_code
        self.errors = errors or []
        super().__init__(self.message)


class CloudflareAPI:
    """Async Cloudflare DNS API wrapper."""

    BASE_URL = "https://api.cloudflare.com/client/v4"

    def __init__(self, api_token: str, default_zone_id: str | None = None):
        self.api_token = api_token
        self.default_zone_id = default_zone_id
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Make an API request to Cloudflare."""
        client = await self._get_client()

        try:
            response = await client.request(
                method=method,
                url=endpoint,
                json=json_data,
                params=params,
            )
        except httpx.TimeoutException as e:
            logger.error(f"Cloudflare API timeout: {e}")
            raise CloudflareAPIError("Request timed out. Please try again.") from e
        except httpx.RequestError as e:
            logger.error(f"Cloudflare API request error: {e}")
            raise CloudflareAPIError(f"Network error: {e}") from e

        try:
            data = response.json()
        except Exception as e:
            logger.error(f"Failed to parse Cloudflare response: {e}")
            raise CloudflareAPIError("Invalid response from Cloudflare API") from e

        if not data.get("success", False):
            errors = data.get("errors", [])
            error_messages = [e.get("message", "Unknown error") for e in errors]
            error_text = "; ".join(error_messages) if error_messages else "Unknown API error"
            logger.error(f"Cloudflare API error: {error_text}")
            raise CloudflareAPIError(error_text, response.status_code, errors)

        return data

    def _get_zone_id(self, zone_id: str | None) -> str:
        """Get zone ID, falling back to default."""
        zid = zone_id or self.default_zone_id
        if not zid:
            raise CloudflareAPIError("No zone ID provided and no default zone configured")
        return zid

    async def list_records(
        self,
        zone_id: str | None = None,
        record_type: str | None = None,
        name: str | None = None,
        per_page: int = 100,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """
        List DNS records for a zone.

        Args:
            zone_id: Cloudflare zone ID (uses default if not provided)
            record_type: Filter by record type (A, AAAA, CNAME, etc.)
            name: Filter by exact record name
            per_page: Number of records per page (max 100)
            page: Page number

        Returns:
            List of DNS record dictionaries
        """
        zid = self._get_zone_id(zone_id)
        params: dict[str, Any] = {"per_page": per_page, "page": page}

        if record_type:
            record_type = record_type.upper()
            if record_type not in VALID_RECORD_TYPES:
                raise CloudflareAPIError(f"Invalid record type: {record_type}")
            params["type"] = record_type

        if name:
            params["name"] = name

        data = await self._request("GET", f"/zones/{zid}/dns_records", params=params)
        return data.get("result", [])

    async def get_record(self, record_id: str, zone_id: str | None = None) -> dict[str, Any]:
        """
        Get a specific DNS record by ID.

        Args:
            record_id: The DNS record ID
            zone_id: Cloudflare zone ID

        Returns:
            DNS record dictionary
        """
        zid = self._get_zone_id(zone_id)
        data = await self._request("GET", f"/zones/{zid}/dns_records/{record_id}")
        return data.get("result", {})

    async def find_records_by_name(
        self,
        name: str,
        zone_id: str | None = None,
        record_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find DNS records by name (supports partial matching).

        Args:
            name: Record name to search for
            zone_id: Cloudflare zone ID
            record_type: Optional record type filter

        Returns:
            List of matching DNS records
        """
        zid = self._get_zone_id(zone_id)
        all_records = await self.list_records(zone_id=zid, record_type=record_type)

        name_lower = name.lower()
        return [r for r in all_records if name_lower in r.get("name", "").lower()]

    async def create_record(
        self,
        name: str,
        record_type: str,
        content: str,
        ttl: int = 1,
        proxied: bool = False,
        priority: int | None = None,
        zone_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new DNS record.

        Args:
            name: DNS record name (e.g., "sub.example.com")
            record_type: Record type (A, AAAA, CNAME, TXT, MX, etc.)
            content: Record content (IP address, hostname, etc.)
            ttl: TTL in seconds (1 = auto)
            proxied: Whether to proxy through Cloudflare (only for A/AAAA/CNAME)
            priority: Priority for MX records
            zone_id: Cloudflare zone ID

        Returns:
            Created DNS record dictionary
        """
        zid = self._get_zone_id(zone_id)
        record_type = record_type.upper()

        if record_type not in VALID_RECORD_TYPES:
            raise CloudflareAPIError(f"Invalid record type: {record_type}")

        payload: dict[str, Any] = {
            "type": record_type,
            "name": name,
            "content": content,
            "ttl": ttl,
        }

        # Only A, AAAA, and CNAME records can be proxied
        if record_type in ("A", "AAAA", "CNAME"):
            payload["proxied"] = proxied

        # MX records require priority
        if record_type == "MX":
            payload["priority"] = priority if priority is not None else 10

        data = await self._request("POST", f"/zones/{zid}/dns_records", json_data=payload)
        return data.get("result", {})

    async def update_record(
        self,
        record_id: str,
        name: str | None = None,
        record_type: str | None = None,
        content: str | None = None,
        ttl: int | None = None,
        proxied: bool | None = None,
        priority: int | None = None,
        zone_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Update an existing DNS record.

        Args:
            record_id: The DNS record ID to update
            name: New record name (optional)
            record_type: New record type (optional)
            content: New content (optional)
            ttl: New TTL (optional)
            proxied: New proxy status (optional)
            priority: New priority for MX records (optional)
            zone_id: Cloudflare zone ID

        Returns:
            Updated DNS record dictionary
        """
        zid = self._get_zone_id(zone_id)

        # First get the existing record
        existing = await self.get_record(record_id, zone_id=zid)

        payload: dict[str, Any] = {
            "type": record_type or existing["type"],
            "name": name or existing["name"],
            "content": content or existing["content"],
            "ttl": ttl if ttl is not None else existing.get("ttl", 1),
        }

        rtype = payload["type"]
        if rtype in ("A", "AAAA", "CNAME"):
            payload["proxied"] = proxied if proxied is not None else existing.get("proxied", False)

        if rtype == "MX":
            payload["priority"] = priority if priority is not None else existing.get("priority", 10)

        data = await self._request("PUT", f"/zones/{zid}/dns_records/{record_id}", json_data=payload)
        return data.get("result", {})

    async def delete_record(self, record_id: str, zone_id: str | None = None) -> bool:
        """
        Delete a DNS record.

        Args:
            record_id: The DNS record ID to delete
            zone_id: Cloudflare zone ID

        Returns:
            True if deletion was successful
        """
        zid = self._get_zone_id(zone_id)
        await self._request("DELETE", f"/zones/{zid}/dns_records/{record_id}")
        return True

    async def toggle_proxy(self, record_id: str, zone_id: str | None = None) -> dict[str, Any]:
        """
        Toggle the proxy status of a DNS record.

        Args:
            record_id: The DNS record ID
            zone_id: Cloudflare zone ID

        Returns:
            Updated DNS record dictionary
        """
        zid = self._get_zone_id(zone_id)
        existing = await self.get_record(record_id, zone_id=zid)

        if existing["type"] not in ("A", "AAAA", "CNAME"):
            raise CloudflareAPIError(f"Cannot proxy {existing['type']} records")

        new_proxied = not existing.get("proxied", False)
        return await self.update_record(record_id, proxied=new_proxied, zone_id=zid)

    async def get_zone_info(self, zone_id: str | None = None) -> dict[str, Any]:
        """
        Get information about a zone.

        Args:
            zone_id: Cloudflare zone ID

        Returns:
            Zone information dictionary
        """
        zid = self._get_zone_id(zone_id)
        data = await self._request("GET", f"/zones/{zid}")
        return data.get("result", {})

    async def list_zones(self) -> list[dict[str, Any]]:
        """
        List all zones accessible with the API token.

        Returns:
            List of zone dictionaries
        """
        data = await self._request("GET", "/zones", params={"per_page": 50})
        return data.get("result", [])

    async def export_records(
        self,
        zone_id: str | None = None,
        record_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Export all DNS records (for backup/export functionality).

        Args:
            zone_id: Cloudflare zone ID
            record_type: Optional filter by record type

        Returns:
            List of all DNS records
        """
        zid = self._get_zone_id(zone_id)
        all_records: list[dict[str, Any]] = []
        page = 1

        while True:
            records = await self.list_records(
                zone_id=zid,
                record_type=record_type,
                per_page=100,
                page=page,
            )
            if not records:
                break
            all_records.extend(records)
            if len(records) < 100:
                break
            page += 1

        return all_records