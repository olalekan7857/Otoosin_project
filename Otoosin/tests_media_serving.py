import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import Resolver404, resolve

from .media_serving import serve_media


class MediaServingTests(SimpleTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.media_root = Path(self.temp_dir) / "media"
        self.media_root.mkdir()
        self.override = override_settings(
            DEBUG=False,
            MEDIA_ROOT=str(self.media_root),
            MEDIA_URL="/media/",
        )
        self.override.enable()
        self.media_file = (
            self.media_root
            / "products"
            / "2026"
            / "11"
            / "test-image.jpg"
        )
        self.media_file.parent.mkdir(parents=True)
        self.media_file.write_bytes(b"fake-jpeg-bytes")

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_existing_media_file_is_served_with_debug_false(self):
        response = self.client.get(
            "/media/products/2026/11/test-image.jpg"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            b"".join(response.streaming_content),
            b"fake-jpeg-bytes",
        )

    def test_missing_media_file_returns_404_without_listing(self):
        response = self.client.get("/media/products/2026/11/missing.jpg")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"Not Found")

    def test_directory_requests_do_not_list_files(self):
        response = self.client.get("/media/products/2026/11/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"Not Found")

    def test_traversal_cannot_read_outside_media_root(self):
        secret = Path(self.temp_dir) / "secret.txt"
        secret.write_text("outside media root", encoding="utf-8")

        request = RequestFactory().get("/media/unused")
        for path in (
            "../secret.txt",
            "..\\secret.txt",
            "/etc/passwd",
            str(secret),
        ):
            with self.subTest(path=path):
                response = serve_media(request, path=path)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(b"outside media root", response.content)

    def test_encoded_traversal_through_url_returns_404(self):
        secret = Path(self.temp_dir) / "secret.txt"
        secret.write_text("outside media root", encoding="utf-8")

        response = self.client.get("/media/%2e%2e/secret.txt")
        self.assertEqual(response.status_code, 404)

    def test_static_file_handling_is_unchanged(self):
        self.assertEqual(resolve("/media/test.jpg").url_name, "media")
        with self.assertRaises(Resolver404):
            resolve("/static/assets/img/categorie/otoosin-eggs.png")
        self.assertIsNotNone(
            finders.find("assets/img/categorie/otoosin-eggs.png")
        )
        self.assertIn("staticfiles", settings.STORAGES)
