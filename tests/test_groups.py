from httpx import AsyncClient

from tests.conftest import auth_headers


class TestCreateGroup:

    async def test_create_group_success(self, client: AsyncClient, user_alice):
        response = await client.post(
            "/api/v1/groups",
            json={"name": "Trip", "description": "Summer trip"},
            headers=auth_headers(user_alice),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Trip"
        assert data["member_count"] == 1

async def test_create_group_unauthenticated(client: AsyncClient):
    response = await client.post("/api/v1/groups", json={"name": "Trip"})
    assert response.status_code == 401


class TestGroupMembership:

    async def test_non_member_cannot_view_group(
        self, client: AsyncClient, user_bob, group_with_alice_and_bob, user_charlie
    ):
        """Charlie is not in the group - should get 403."""
        response = await client.get(
            f"/api/v1/groups/{group_with_alice_and_bob.id}",
            headers=auth_headers(user_charlie),
        )
        assert response.status_code == 403

    async def test_member_can_view_group(
        self, client: AsyncClient, user_bob, group_with_alice_and_bob
    ):
        response = await client.get(
            f"/api/v1/groups/{group_with_alice_and_bob.id}",
            headers=auth_headers(user_bob),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["member_count"] == 2

    async def test_non_admin_cannot_invite(
        self, client: AsyncClient, user_bob, user_charlie, group_with_alice_and_bob
    ):
        """Bob is member (not admin) - cannot invite."""
        response = await client.post(
            f"/api/v1/groups/{group_with_alice_and_bob.id}/members",
            json={"email": "charlie@test.com"},
            headers=auth_headers(user_bob),
        )
        assert response.status_code == 403

    async def test_admin_can_invite(
        self, client: AsyncClient, user_alice, user_charlie, group_with_alice_and_bob
    ):
        response = await client.post(
            f"/api/v1/groups/{group_with_alice_and_bob.id}/members",
            json={"email": "charlie@test.com"},
            headers=auth_headers(user_alice),
        )
        assert response.status_code == 201
        assert response.json()["username"] == "charlie"

    async def test_sole_admin_cannot_leave(
        self, client: AsyncClient, user_alice, group_with_alice_and_bob
    ):
        """Alice is the only admin — cannot leave."""
        response = await client.delete(
            f"/api/v1/groups/{group_with_alice_and_bob.id}/leave",
            headers=auth_headers(user_alice),
        )
        assert response.status_code == 400