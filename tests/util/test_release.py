from infuse_iot.util.release import ota_image_paths, ota_images


def test_ota_image_preference():
    tfm = "app/zephyr/tfm_s_zephyr_ns_signed.bin"
    signed = "app/zephyr/zephyr.signed.bin"
    assert ota_images(["ota-app-1.0.0+00000000.bin", tfm, signed], "app") == (["ota-app-1.0.0+00000000.bin"], False)
    assert ota_images([tfm, signed], "app") == ([tfm], True)
    assert ota_images([signed, "nested/ota-app.bin"], "app") == ([signed], True)
    assert ota_images(["other/zephyr/zephyr.signed.bin"], "app") == ([], True)
    assert ota_images(["ota-a.bin", "ota-b.bin"], "app")[0] == ["ota-a.bin", "ota-b.bin"]


def test_ota_image_paths(tmp_path):
    image = tmp_path / "app" / "zephyr" / "zephyr.signed.bin"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    assert ota_image_paths(tmp_path, "app") == (["app/zephyr/zephyr.signed.bin"], True)
    (tmp_path / "ota-app.bin").write_bytes(b"image")
    assert ota_image_paths(tmp_path, "app") == (["ota-app.bin"], False)
