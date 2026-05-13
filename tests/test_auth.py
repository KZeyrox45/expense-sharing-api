from httpx import AsyncClient

from tests.conftest import auth_headers


class TestRegister:

    async def test_register_success(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "newuser@test.com",
            "username": "newuser",
            "password": "password123",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@test.com"
        assert "hashed_password" not in data

    async def test_register_duplicate_email(self, client: AsyncClient, user_alice):
        response = await client.post("/api/v1/auth/register", json={
            "email": "alice@test.com",   # same as user_alice fixture
            "username": "alice2",
            "password": "password123",
        })
        assert response.status_code == 400
        assert "Email already registered" in response.json()["detail"]

    async def test_register_duplicate_username(self, client: AsyncClient, user_alice):
        response = await client.post("/api/v1/auth/register", json={
            "email": "different@test.com",
            "username": "alice",         # same as user_alice
            "password": "password123",
        })
        assert response.status_code == 400
        assert "Username already registered" in response.json()["detail"]

    async def test_register_short_password(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "x@test.com",
            "username": "xuser",
            "password": "short",
        })
        assert response.status_code == 422


class TestLogin:

    async def test_login_success(self, client: AsyncClient, user_alice):
        response = await client.post("/api/v1/auth/login", json={
            "email": "alice@test.com",
            "password": "password123",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, user_alice):
        response = await client.post("/api/v1/auth/login", json={
            "email": "alice@test.com",
            "password": "wrongpassword",
        })
        assert response.status_code in (401, 403)

    async def test_login_unknown_email(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/login", json={
            "email": "nobody@test.com",
            "password": "password123",
        })
        assert response.status_code in (401, 403)


class TestMe:

    async def test_get_me_authenticated(self, client: AsyncClient, user_alice):
        response = await client.get(
            "/api/v1/auth/me",
            headers=auth_headers(user_alice),
        )
        assert response.status_code == 200
        assert response.json()["username"] == "alice"

    async def test_get_me_no_token(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code in (401, 403)