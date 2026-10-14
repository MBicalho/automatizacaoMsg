import tempfile
from pathlib import Path
import unittest

from file_validator import (
    AttachmentSecurityError,
    classify_attachment_type,
    resolve_and_validate_attachment,
)


class FileValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        # Cria arquivos ficticios
        (self.base_path / "documento.pdf").write_bytes(b"%PDF-1.4 test")
        (self.base_path / "foto.png").write_bytes(b"\x89PNG test")
        (self.base_path / "overview.docx").write_bytes(b"PK test")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolves_valid_file(self):
        res = resolve_and_validate_attachment("documento.pdf", base_dir=self.base_path, must_exist=True)
        self.assertIsNotNone(res)
        self.assertEqual(res.name, "documento.pdf")
        self.assertEqual(classify_attachment_type(res), 2)

    def test_classifies_image(self):
        res = resolve_and_validate_attachment("foto.png", base_dir=self.base_path, must_exist=True)
        self.assertEqual(classify_attachment_type(res), 3)

    def test_resolves_stem_without_extension(self):
        res = resolve_and_validate_attachment("overview", base_dir=self.base_path, must_exist=True)
        self.assertIsNotNone(res)
        self.assertEqual(res.name, "overview.docx")

    def test_blocks_directory_traversal(self):
        with self.assertRaises(AttachmentSecurityError):
            resolve_and_validate_attachment("../../../boot.ini", base_dir=self.base_path)

        with self.assertRaises(AttachmentSecurityError):
            resolve_and_validate_attachment("subdir/../../secret.txt", base_dir=self.base_path)

    def test_blocks_unauthorized_extension(self):
        with self.assertRaises(AttachmentSecurityError):
            resolve_and_validate_attachment("script.exe", base_dir=self.base_path)

    def test_missing_file_raises_when_required(self):
        with self.assertRaises(FileNotFoundError):
            resolve_and_validate_attachment("nao_existe.pdf", base_dir=self.base_path, must_exist=True)


if __name__ == "__main__":
    unittest.main()
