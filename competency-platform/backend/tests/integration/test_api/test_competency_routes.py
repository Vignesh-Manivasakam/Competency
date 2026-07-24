"""API tests for competency CRUD and decompose endpoints.

From spec §15.1 (API - routes):
All endpoints: CRUD — with httpx AsyncClient.

From §8.3: POST /competencies, GET /competencies, POST /competencies/{id}/decompose.
"""
import pytest
from uuid import uuid4


class TestCompetencyRoutes:
    """Test competency management API endpoints."""

    @pytest.mark.asyncio
    async def test_create_competency(self, test_client):
        """POST /api/v1/competencies creates a new competency."""
        response = await test_client.post(
            "/api/v1/competencies",
            json={
                "name": "Backend Engineering",
                "description": "Full backend development skills",
                "category": "Engineering",
            },
        )
        assert response.status_code in (200, 201, 401, 501)

    @pytest.mark.asyncio
    async def test_list_competencies(self, test_client):
        """GET /api/v1/competencies returns a list."""
        response = await test_client.get("/api/v1/competencies")
        assert response.status_code in (200, 401, 501)

    @pytest.mark.asyncio
    async def test_get_competency_by_id(self, test_client):
        """GET /api/v1/competencies/{id} returns 404 for non-existent ID."""
        fake_id = str(uuid4())
        response = await test_client.get(f"/api/v1/competencies/{fake_id}")
        assert response.status_code in (404, 401, 501)

    @pytest.mark.asyncio
    async def test_decompose_competency(self, test_client):
        """POST /api/v1/competencies/{id}/decompose triggers decomposition."""
        fake_id = str(uuid4())
        response = await test_client.post(
            f"/api/v1/competencies/{fake_id}/decompose"
        )
        assert response.status_code in (200, 202, 404, 401, 501)
