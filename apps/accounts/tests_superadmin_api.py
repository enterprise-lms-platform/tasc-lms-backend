import pytest
from rest_framework.test import APIClient
from django.urls import reverse
from .models import Organization
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def tasc_admin_user():
    return User.objects.create_user(
        username="tasc_admin_test",
        email="tasc_admin@test.com",
        password="testpassword123",
        role=User.Role.TASC_ADMIN,
    )


@pytest.fixture
def regular_learner_user():
    return User.objects.create_user(
        username="learner_test",
        email="learner@test.com",
        password="testpassword123",
        role=User.Role.LEARNER,
    )


@pytest.mark.django_db
def test_organization_superadmin_access_denied_for_learners(api_client, regular_learner_user):
    api_client.force_authenticate(user=regular_learner_user)
    response = api_client.get("/api/v1/superadmin/organizations/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_organization_superadmin_crud_tasc_admin(api_client, tasc_admin_user):
    api_client.force_authenticate(user=tasc_admin_user)

    # CREATE
    data = {
        "name": "Test Org",
        "slug": "test-org",
        "is_active": True,
    }
    response = api_client.post("/api/v1/superadmin/organizations/", data)
    assert response.status_code == 201
    org_id = response.data["id"]

    # LIST
    response = api_client.get("/api/v1/superadmin/organizations/")
    assert response.status_code == 200
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["name"] == "Test Org"

    # STATS
    response = api_client.get("/api/v1/superadmin/organizations/stats/")
    assert response.status_code == 200
    assert response.data["total"] == 1
    assert response.data["active"] == 1

    # DELETE
    response = api_client.delete(f"/api/v1/superadmin/organizations/{org_id}/")
    assert response.status_code == 204

    # STATS AFTER DELETE
    response = api_client.get("/api/v1/superadmin/organizations/stats/")
    assert response.status_code == 200
    assert response.data["total"] == 0


@pytest.mark.django_db
def test_user_superadmin_crud_tasc_admin(api_client, tasc_admin_user):
    api_client.force_authenticate(user=tasc_admin_user)

    # CREATE
    data = {
        "email": "new_superadmin_user@test.com",
        "username": "newuser3322",
        "first_name": "Test",
        "last_name": "User",
        "role": User.Role.LEARNER,
    }
    # Note: password is not set in this serializer stub, real flow uses invite/password reset
    response = api_client.post("/api/v1/superadmin/users/", data)
    assert response.status_code == 201
    user_id = response.data["id"]

    # LIST
    response = api_client.get("/api/v1/superadmin/users/")
    assert response.status_code == 200
    # 2 users: tasc_admin_user + the newly created one
    assert len(response.data["results"]) == 2

    # CSV TEMPLATE
    response = api_client.get("/api/v1/superadmin/users/csv_template/")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "attachment; filename" in response["Content-Disposition"]
