from httpx import AsyncClient

from tests.conftest import auth_headers


class TestCreateExpense:

    async def test_equal_split(
        self, client: AsyncClient, user_alice, user_bob, group_with_alice_and_bob
    ):
        response = await client.post(
            f"/api/v1/groups/{group_with_alice_and_bob.id}/expenses",
            json={
                "description": "Dinner",
                "total_amount": "100.00",
                "split_type": "equal",
                "date_happened": "2025-05-10",
                "payers": [{"user_id": str(user_alice.id), "amount": "100.00"}],
                "splits": [
                    {"user_id": str(user_alice.id)},
                    {"user_id": str(user_bob.id)},
                ],
            },
            headers=auth_headers(user_alice),
        )
        assert response.status_code == 201
        splits = response.json()["splits"]
        amounts = {s["username"]: s["amount"] for s in splits}
        assert amounts["alice"] == "50.00"
        assert amounts["bob"] == "50.00"

    async def test_percentage_split(
        self, client: AsyncClient, user_alice, user_bob, group_with_alice_and_bob
    ):
        response = await client.post(
            f"/api/v1/groups/{group_with_alice_and_bob.id}/expenses",
            json={
                "description": "Hotel",
                "total_amount": "200.00",
                "split_type": "percentage",
                "date_happened": "2025-05-10",
                "payers": [{"user_id": str(user_alice.id), "amount": "200.00"}],
                "splits": [
                    {"user_id": str(user_alice.id), "value": "70"},
                    {"user_id": str(user_bob.id), "value": "30"},
                ],
            },
            headers=auth_headers(user_alice),
        )
        assert response.status_code == 201
        splits = response.json()["splits"]
        amounts = {s["username"]: s["amount"] for s in splits}
        assert amounts["alice"] == "140.00"
        assert amounts["bob"] == "60.00"

    async def test_percentage_not_100_rejected(
        self, client: AsyncClient, user_alice, user_bob, group_with_alice_and_bob
    ):
        response = await client.post(
            f"/api/v1/groups/{group_with_alice_and_bob.id}/expenses",
            json={
                "description": "Hotel",
                "total_amount": "100.00",
                "split_type": "percentage",
                "date_happened": "2025-05-10",
                "payers": [{"user_id": str(user_alice.id), "amount": "100.00"}],
                "splits": [
                    {"user_id": str(user_alice.id), "value": "60"},
                    {"user_id": str(user_bob.id), "value": "60"},
                ],
            },
            headers=auth_headers(user_alice),
        )
        assert response.status_code == 400
        assert "100" in response.json()["detail"]

    async def test_non_member_cannot_create_expense(
        self, client: AsyncClient, user_charlie, group_with_alice_and_bob
    ):
        response = await client.post(
            f"/api/v1/groups/{group_with_alice_and_bob.id}/expenses",
            json={
                "description": "Test",
                "total_amount": "100.00",
                "split_type": "equal",
                "date_happened": "2025-05-10",
                "payers": [{"user_id": str(user_charlie.id), "amount": "100.00"}],
                "splits": [{"user_id": str(user_charlie.id)}],
            },
            headers=auth_headers(user_charlie),
        )
        assert response.status_code == 403

    async def test_payer_sum_mismatch_rejected(
        self, client: AsyncClient, user_alice, user_bob, group_with_alice_and_bob
    ):
        response = await client.post(
            f"/api/v1/groups/{group_with_alice_and_bob.id}/expenses",
            json={
                "description": "Test",
                "total_amount": "100.00",
                "split_type": "equal",
                "date_happened": "2025-05-10",
                "payers": [{"user_id": str(user_alice.id), "amount": "80.00"}],
                "splits": [
                    {"user_id": str(user_alice.id)},
                    {"user_id": str(user_bob.id)},
                ],
            },
            headers=auth_headers(user_alice),
        )
        assert response.status_code == 400

    async def test_soft_delete(
        self, client: AsyncClient, user_alice, user_bob, group_with_alice_and_bob
    ):
        """Create then delete - subsequent GET returns 404."""
        create_resp = await client.post(
            f"/api/v1/groups/{group_with_alice_and_bob.id}/expenses",
            json={
                "description": "To delete",
                "total_amount": "50.00",
                "split_type": "equal",
                "date_happened": "2025-05-10",
                "payers": [{"user_id": str(user_alice.id), "amount": "50.00"}],
                "splits": [{"user_id": str(user_alice.id)}, {"user_id": str(user_bob.id)}],
            },
            headers=auth_headers(user_alice),
        )
        assert create_resp.status_code == 201
        expense_id = create_resp.json()["id"]

        delete_resp = await client.delete(
            f"/api/v1/groups/{group_with_alice_and_bob.id}/expenses/{expense_id}",
            headers=auth_headers(user_alice),
        )
        assert delete_resp.status_code == 204

        get_resp = await client.get(
            f"/api/v1/groups/{group_with_alice_and_bob.id}/expenses/{expense_id}",
            headers=auth_headers(user_alice),
        )
        assert get_resp.status_code == 404