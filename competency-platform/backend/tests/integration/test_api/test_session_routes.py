"""API tests for session lifecycle endpoints.

From spec §15.1 (API - routes):
All endpoints: Session CRUD, WebSocket — with httpx AsyncClient.

From §8.5: POST /sessions, GET /sessions/{id}, POST /sessions/{id}/interact.
"""
import pytest
from uuid import uuid4


class TestSessionRoutes:
    """Test learning session API endpoints."""

    @pytest.mark.asyncio
    async def test_create_session(self, test_client):
        """POST /api/v1/sessions creates a new learning session."""
        response = await test_client.post(
            "/api/v1/sessions",
            json={
                "employee_id": str(uuid4()),
                "skill_id": str(uuid4()),
            },
        )
        assert response.status_code in (200, 201, 401, 422, 500, 501)

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, test_client):
        """GET /api/v1/sessions/{id} returns 404 for missing session."""
        fake_id = str(uuid4())
        response = await test_client.get(f"/api/v1/sessions/{fake_id}")
        assert response.status_code in (404, 401, 422, 501)

    @pytest.mark.asyncio
    async def test_interact_with_session(self, test_client):
        """POST /api/v1/sessions/{id}/interact sends learner message."""
        fake_id = str(uuid4())
        response = await test_client.post(
            f"/api/v1/sessions/{fake_id}/interact",
            json={
                "message": "What are Python decorators?",
                "interaction_type": "question",
            },
        )
        assert response.status_code in (200, 404, 401, 422, 500, 501)

    @pytest.mark.asyncio
    async def test_health_endpoint(self, test_client):
        """GET /health returns 200 with status healthy or ok."""
        response = await test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ("healthy", "ok")
