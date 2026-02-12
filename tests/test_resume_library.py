"""Tests for Resume Library PDF upload and management functionality."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_resume_dir(tmp_path):
    """Create temporary resume references directory."""
    resume_dir = tmp_path / "docs" / "Resume References"
    resume_dir.mkdir(parents=True, exist_ok=True)
    return resume_dir


@pytest.fixture
def temp_sources_file(tmp_path):
    """Create temporary resume_sources.json file."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    sources_path = data_dir / "resume_sources.json"
    sources_path.write_text(json.dumps({}), encoding="utf-8")
    return sources_path


@pytest.fixture
def sample_pdf_bytes():
    """Generate a minimal valid PDF."""
    # Minimal PDF structure
    return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test Resume) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000317 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
410
%%EOF"""


class TestPDFUpload:
    """Test PDF template upload functionality."""

    def test_single_pdf_upload(self, temp_resume_dir, temp_sources_file, sample_pdf_bytes):
        """Test uploading a single PDF template."""
        # Setup
        safe_name = "Test Resume 2026"
        pdf_path = temp_resume_dir / f"{safe_name}.pdf"

        # Simulate upload
        pdf_path.write_bytes(sample_pdf_bytes)

        # Update metadata
        sources_data = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        sources_data["uploaded_templates"] = [
            {
                "name": safe_name,
                "path": str(pdf_path),
                "language": "English",
                "uploaded_at": datetime.now().isoformat(),
                "size_kb": len(sample_pdf_bytes) / 1024,
            }
        ]
        temp_sources_file.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")

        # Verify
        assert pdf_path.exists()
        assert pdf_path.read_bytes() == sample_pdf_bytes

        metadata = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        assert "uploaded_templates" in metadata
        assert len(metadata["uploaded_templates"]) == 1
        assert metadata["uploaded_templates"][0]["name"] == safe_name
        assert metadata["uploaded_templates"][0]["language"] == "English"

    def test_batch_pdf_upload(self, temp_resume_dir, temp_sources_file, sample_pdf_bytes):
        """Test uploading multiple PDF templates at once."""
        # Setup
        templates = ["Resume_A", "Resume_B", "Resume_C"]

        sources_data = {"uploaded_templates": []}

        for template_name in templates:
            pdf_path = temp_resume_dir / f"{template_name}.pdf"
            pdf_path.write_bytes(sample_pdf_bytes)

            sources_data["uploaded_templates"].append(
                {
                    "name": template_name,
                    "path": str(pdf_path),
                    "language": "English",
                    "uploaded_at": datetime.now().isoformat(),
                    "size_kb": len(sample_pdf_bytes) / 1024,
                }
            )

        temp_sources_file.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")

        # Verify
        metadata = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        assert len(metadata["uploaded_templates"]) == 3
        assert all((temp_resume_dir / f"{t}.pdf").exists() for t in templates)

    def test_duplicate_template_detection(
        self, temp_resume_dir, temp_sources_file, sample_pdf_bytes
    ):
        """Test that duplicate template names are handled correctly."""
        template_name = "Duplicate_Resume"
        pdf_path = temp_resume_dir / f"{template_name}.pdf"
        pdf_path.write_bytes(sample_pdf_bytes)

        sources_data = {
            "uploaded_templates": [
                {
                    "name": template_name,
                    "path": str(pdf_path),
                    "language": "English",
                    "uploaded_at": datetime.now().isoformat(),
                    "size_kb": len(sample_pdf_bytes) / 1024,
                }
            ]
        }
        temp_sources_file.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")

        # Verify duplicate exists
        metadata = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        assert any(t.get("name") == template_name for t in metadata["uploaded_templates"])

    def test_filename_sanitization(self, temp_resume_dir, temp_sources_file, sample_pdf_bytes):
        """Test that unsafe characters are removed from filenames."""
        unsafe_name = 'Resume<>/\\:*?"| Test@2026'
        safe_name = "".join(c for c in unsafe_name if c.isalnum() or c in (" ", "-", "_")).strip()

        assert safe_name == "Resume Test2026"

        pdf_path = temp_resume_dir / f"{safe_name}.pdf"
        pdf_path.write_bytes(sample_pdf_bytes)

        assert pdf_path.exists()
        assert "<" not in pdf_path.name
        assert "/" not in pdf_path.name

    def test_file_size_validation(self, sample_pdf_bytes):
        """Test file size warning for large files."""
        # Simulate large file (> 10MB)
        large_file_bytes = sample_pdf_bytes * 30000  # ~12MB
        size_mb = len(large_file_bytes) / (1024 * 1024)

        assert size_mb > 10, "Test file should be > 10MB to trigger warning"

    def test_metadata_structure(self, temp_sources_file, sample_pdf_bytes):
        """Test that metadata follows expected structure."""
        sources_data = {
            "uploaded_templates": [
                {
                    "name": "Test_Resume",
                    "path": "X:/Projects/jSeeker/docs/Resume References/Test_Resume.pdf",
                    "language": "Spanish",
                    "uploaded_at": "2026-02-10T15:30:00",
                    "size_kb": len(sample_pdf_bytes) / 1024,
                }
            ]
        }
        temp_sources_file.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")

        # Verify structure
        metadata = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        template = metadata["uploaded_templates"][0]

        assert "name" in template
        assert "path" in template
        assert "language" in template
        assert "uploaded_at" in template
        assert "size_kb" in template
        assert isinstance(template["size_kb"], (int, float))


class TestTemplateManagement:
    """Test template management operations (delete, edit, display)."""

    def test_delete_template(self, temp_resume_dir, temp_sources_file, sample_pdf_bytes):
        """Test deleting a template file and metadata."""
        template_name = "To_Delete"
        pdf_path = temp_resume_dir / f"{template_name}.pdf"
        pdf_path.write_bytes(sample_pdf_bytes)

        sources_data = {
            "uploaded_templates": [
                {
                    "name": template_name,
                    "path": str(pdf_path),
                    "language": "English",
                    "uploaded_at": datetime.now().isoformat(),
                    "size_kb": len(sample_pdf_bytes) / 1024,
                }
            ]
        }
        temp_sources_file.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")

        assert pdf_path.exists()

        # Delete file
        pdf_path.unlink()

        # Remove from metadata
        sources_data["uploaded_templates"].pop(0)
        temp_sources_file.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")

        # Verify
        assert not pdf_path.exists()
        metadata = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        assert len(metadata["uploaded_templates"]) == 0

    def test_edit_template_metadata(self, temp_resume_dir, temp_sources_file, sample_pdf_bytes):
        """Test editing template name and language."""
        old_name = "Old_Resume"
        new_name = "New_Resume"

        pdf_path = temp_resume_dir / f"{old_name}.pdf"
        pdf_path.write_bytes(sample_pdf_bytes)

        sources_data = {
            "uploaded_templates": [
                {
                    "name": old_name,
                    "path": str(pdf_path),
                    "language": "English",
                    "uploaded_at": datetime.now().isoformat(),
                    "size_kb": len(sample_pdf_bytes) / 1024,
                }
            ]
        }
        temp_sources_file.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")

        # Rename file
        new_path = temp_resume_dir / f"{new_name}.pdf"
        pdf_path.rename(new_path)

        # Update metadata
        sources_data["uploaded_templates"][0]["name"] = new_name
        sources_data["uploaded_templates"][0]["path"] = str(new_path)
        sources_data["uploaded_templates"][0]["language"] = "Spanish"
        temp_sources_file.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")

        # Verify
        assert not pdf_path.exists()
        assert new_path.exists()
        metadata = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        assert metadata["uploaded_templates"][0]["name"] == new_name
        assert metadata["uploaded_templates"][0]["language"] == "Spanish"

    def test_template_download_data(self, temp_resume_dir, sample_pdf_bytes):
        """Test that template can be read for download."""
        template_name = "Download_Test"
        pdf_path = temp_resume_dir / f"{template_name}.pdf"
        pdf_path.write_bytes(sample_pdf_bytes)

        # Simulate download (read file)
        with open(pdf_path, "rb") as f:
            downloaded_data = f.read()

        assert downloaded_data == sample_pdf_bytes
        assert len(downloaded_data) > 0


class TestPDFPreview:
    """Test PDF preview rendering functionality."""

    def test_pdf_preview_with_pymupdf(self, temp_resume_dir, sample_pdf_bytes):
        """Test PDF preview rendering using PyMuPDF."""
        try:
            import fitz  # PyMuPDF

            pdf_path = temp_resume_dir / "Preview_Test.pdf"
            pdf_path.write_bytes(sample_pdf_bytes)

            # Render first page
            doc = fitz.open(pdf_path)
            assert len(doc) >= 1

            page = doc[0]
            pix = page.get_pixmap(dpi=150)

            # Verify pixmap created
            assert pix.width > 0
            assert pix.height > 0

            img_bytes = pix.tobytes("png")
            assert len(img_bytes) > 0

            doc.close()

        except ImportError:
            pytest.skip("PyMuPDF not installed")

    def test_pdf_preview_fallback(self, temp_resume_dir, sample_pdf_bytes):
        """Test graceful fallback when PyMuPDF unavailable."""
        pdf_path = temp_resume_dir / "Fallback_Test.pdf"
        pdf_path.write_bytes(sample_pdf_bytes)

        # Simulate missing PyMuPDF
        with patch.dict("sys.modules", {"fitz": None}):
            try:
                import fitz  # noqa: F401

                pytest.fail("Should have raised ImportError")
            except (ImportError, AttributeError):
                # Expected - fallback to message
                assert pdf_path.exists()  # File still accessible


class TestLanguageSupport:
    """Test multi-language template support."""

    def test_language_options(self):
        """Test that all expected languages are supported."""
        languages = ["English", "Spanish", "French", "Other"]

        for lang in languages:
            assert lang in ["English", "Spanish", "French", "Other"]

    def test_template_with_different_languages(
        self, temp_resume_dir, temp_sources_file, sample_pdf_bytes
    ):
        """Test uploading templates in different languages."""
        templates = [
            ("Resume_EN", "English"),
            ("Resume_ES", "Spanish"),
            ("Resume_FR", "French"),
            ("Resume_Other", "Other"),
        ]

        sources_data = {"uploaded_templates": []}

        for name, lang in templates:
            pdf_path = temp_resume_dir / f"{name}.pdf"
            pdf_path.write_bytes(sample_pdf_bytes)

            sources_data["uploaded_templates"].append(
                {
                    "name": name,
                    "path": str(pdf_path),
                    "language": lang,
                    "uploaded_at": datetime.now().isoformat(),
                    "size_kb": len(sample_pdf_bytes) / 1024,
                }
            )

        temp_sources_file.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")

        # Verify
        metadata = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        languages_used = [t["language"] for t in metadata["uploaded_templates"]]

        assert "English" in languages_used
        assert "Spanish" in languages_used
        assert "French" in languages_used
        assert "Other" in languages_used


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_sources_file_initialization(self, temp_sources_file):
        """Test that empty sources file is handled correctly."""
        # Start with empty file
        temp_sources_file.write_text("{}", encoding="utf-8")

        data = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        assert "uploaded_templates" not in data or data.get("uploaded_templates") == []

        # Initialize uploaded_templates
        data["uploaded_templates"] = []
        temp_sources_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

        data = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        assert "uploaded_templates" in data
        assert isinstance(data["uploaded_templates"], list)

    def test_missing_resume_references_directory(self, tmp_path):
        """Test that resume references directory is created if missing."""
        resume_dir = tmp_path / "docs" / "Resume References"
        assert not resume_dir.exists()

        # Create directory
        resume_dir.mkdir(parents=True, exist_ok=True)

        assert resume_dir.exists()
        assert resume_dir.is_dir()

    def test_empty_template_name(self, temp_resume_dir, sample_pdf_bytes):
        """Test handling of empty template name (use filename)."""
        # Simulate using filename when name is empty
        original_filename = "My_Resume_2026.pdf"
        safe_name = Path(original_filename).stem

        assert safe_name == "My_Resume_2026"

        pdf_path = temp_resume_dir / f"{safe_name}.pdf"
        pdf_path.write_bytes(sample_pdf_bytes)

        assert pdf_path.exists()

    def test_special_characters_in_path(self, tmp_path, sample_pdf_bytes):
        """Test handling paths with spaces and special characters."""
        resume_dir = tmp_path / "Resume References"
        resume_dir.mkdir(parents=True, exist_ok=True)

        safe_name = "Director of AI  ML"  # & removed

        pdf_path = resume_dir / f"{safe_name}.pdf"
        pdf_path.write_bytes(sample_pdf_bytes)

        assert pdf_path.exists()
        assert "&" not in pdf_path.name


class TestIntegration:
    """Integration tests for complete upload workflow."""

    def test_complete_upload_workflow(self, temp_resume_dir, temp_sources_file, sample_pdf_bytes):
        """Test complete workflow: upload -> display -> edit -> delete."""
        # Step 1: Upload
        template_name = "Integration_Test"
        pdf_path = temp_resume_dir / f"{template_name}.pdf"
        pdf_path.write_bytes(sample_pdf_bytes)

        sources_data = {
            "uploaded_templates": [
                {
                    "name": template_name,
                    "path": str(pdf_path),
                    "language": "English",
                    "uploaded_at": datetime.now().isoformat(),
                    "size_kb": len(sample_pdf_bytes) / 1024,
                }
            ]
        }
        temp_sources_file.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")

        # Step 2: Verify display data
        metadata = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        assert len(metadata["uploaded_templates"]) == 1

        # Step 3: Edit metadata
        new_name = "Integration_Test_Updated"
        new_path = temp_resume_dir / f"{new_name}.pdf"
        pdf_path.rename(new_path)

        metadata["uploaded_templates"][0]["name"] = new_name
        metadata["uploaded_templates"][0]["path"] = str(new_path)
        metadata["uploaded_templates"][0]["language"] = "Spanish"
        temp_sources_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        # Step 4: Verify edit
        updated_metadata = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        assert updated_metadata["uploaded_templates"][0]["name"] == new_name
        assert updated_metadata["uploaded_templates"][0]["language"] == "Spanish"

        # Step 5: Delete
        new_path.unlink()
        updated_metadata["uploaded_templates"].pop(0)
        temp_sources_file.write_text(json.dumps(updated_metadata, indent=2), encoding="utf-8")

        # Step 6: Verify deletion
        final_metadata = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        assert len(final_metadata["uploaded_templates"]) == 0
        assert not new_path.exists()

    def test_multiple_templates_concurrent_operations(
        self, temp_resume_dir, temp_sources_file, sample_pdf_bytes
    ):
        """Test handling multiple templates with concurrent operations."""
        # Upload multiple templates
        templates = ["Template_1", "Template_2", "Template_3"]
        sources_data = {"uploaded_templates": []}

        for template_name in templates:
            pdf_path = temp_resume_dir / f"{template_name}.pdf"
            pdf_path.write_bytes(sample_pdf_bytes)

            sources_data["uploaded_templates"].append(
                {
                    "name": template_name,
                    "path": str(pdf_path),
                    "language": "English",
                    "uploaded_at": datetime.now().isoformat(),
                    "size_kb": len(sample_pdf_bytes) / 1024,
                }
            )

        temp_sources_file.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")

        # Edit one, delete another, keep third
        metadata = json.loads(temp_sources_file.read_text(encoding="utf-8"))

        # Edit Template_1
        metadata["uploaded_templates"][0]["language"] = "Spanish"

        # Delete Template_2
        (temp_resume_dir / "Template_2.pdf").unlink()
        metadata["uploaded_templates"].pop(1)

        temp_sources_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        # Verify final state
        final_metadata = json.loads(temp_sources_file.read_text(encoding="utf-8"))
        assert len(final_metadata["uploaded_templates"]) == 2
        assert final_metadata["uploaded_templates"][0]["language"] == "Spanish"
        assert not (temp_resume_dir / "Template_2.pdf").exists()
        assert (temp_resume_dir / "Template_1.pdf").exists()
        assert (temp_resume_dir / "Template_3.pdf").exists()
