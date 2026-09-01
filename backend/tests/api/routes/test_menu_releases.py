"""Integration tests for the gray-release (menu release stage) system-config API."""

from fastapi.testclient import TestClient

from app.core.config import settings

BASE = f"{settings.API_V1_STR}/access-control"


def _menu_by_code(menus: list[dict], code: str) -> dict | None:
    return next((m for m in menus if m["code"] == code), None)


def test_access_context_exposes_stages_for_superuser(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.get(f"{BASE}/me", headers=superuser_token_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["can_manage_system"] is True
    assert isinstance(body["menu_stages"], dict)
    # data-management ships gray (BETA); superusers preview it in both maps.
    assert body["menu_stages"].get("/data-management") == "BETA"
    assert "/data-management" in body["menu_paths"]
    # The system-config page itself is always released.
    assert body["menu_stages"].get("/system-config") == "GA"


def test_menu_releases_lists_stages(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.get(f"{BASE}/menu-releases", headers=superuser_token_headers)
    assert r.status_code == 200
    body = r.json()
    assert set(body["stages"]) == {"GA", "BETA", "HIDDEN"}
    data_mgmt = _menu_by_code(body["menus"], "data-management")
    assert data_mgmt is not None and data_mgmt["release_stage"] == "BETA"
    sys_cfg = _menu_by_code(body["menus"], "system-config")
    assert sys_cfg is not None and sys_cfg["release_stage"] == "GA"


def test_menu_releases_forbidden_for_normal_user(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    r = client.get(f"{BASE}/menu-releases", headers=normal_user_token_headers)
    assert r.status_code == 403


def test_system_config_menu_cannot_be_hidden(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    catalog = client.get(f"{BASE}/menu-releases", headers=superuser_token_headers).json()
    sys_cfg = _menu_by_code(catalog["menus"], "system-config")
    assert sys_cfg is not None
    r = client.put(
        f"{BASE}/menu-releases/{sys_cfg['id']}",
        headers=superuser_token_headers,
        json={"release_stage": "HIDDEN", "is_active": True},
    )
    assert r.status_code == 422


def test_release_stage_round_trip(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    catalog = client.get(f"{BASE}/menu-releases", headers=superuser_token_headers).json()
    data_mgmt = _menu_by_code(catalog["menus"], "data-management")
    assert data_mgmt is not None
    menu_id = data_mgmt["id"]
    try:
        promote = client.put(
            f"{BASE}/menu-releases/{menu_id}",
            headers=superuser_token_headers,
            json={"release_stage": "GA", "is_active": True},
        )
        assert promote.status_code == 200
        assert promote.json()["release_stage"] == "GA"
        # After promotion the released path set includes the module.
        me = client.get(f"{BASE}/me", headers=superuser_token_headers).json()
        assert "/data-management" in me["menu_paths"]
    finally:
        # Restore the seeded gray state so the test is idempotent.
        client.put(
            f"{BASE}/menu-releases/{menu_id}",
            headers=superuser_token_headers,
            json={"release_stage": "BETA", "is_active": True},
        )
