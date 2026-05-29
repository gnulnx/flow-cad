from flow_cad.scripts.check_through_mount_access import check_through_mount_access


def test_declared_through_mounts_have_washer_and_nut_access() -> None:
    assert check_through_mount_access() == []
