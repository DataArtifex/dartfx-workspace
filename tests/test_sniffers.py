"""Tests for the sniffers sub-package."""

from pathlib import Path

from dartfx.workspace.sniffers import FileFormat, FileType, sniff_file
from dartfx.workspace.sniffers.extension import classify_by_extension
from dartfx.workspace.sniffers.magic import sniff_magic_bytes
from dartfx.workspace.sniffers.text import sniff_text_heuristic


class TestExtensionClassifier:
    """Tests for the extension-based classifier (Step 1)."""

    def test_csv_extension(self, tmp_path: Path):
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2\n")
        result = classify_by_extension(f)
        assert result is not None
        assert result.file_type == FileType.DATA
        assert result.file_format == FileFormat.CSV

    def test_parquet_extension(self, tmp_path: Path):
        f = tmp_path / "data.parquet"
        f.write_bytes(b"PAR1dummy")
        result = classify_by_extension(f)
        assert result is not None
        assert result.file_type == FileType.DATA
        assert result.file_format == FileFormat.PARQUET

    def test_python_extension(self, tmp_path: Path):
        f = tmp_path / "script.py"
        f.write_text("print('hello')")
        result = classify_by_extension(f)
        assert result is not None
        assert result.file_type == FileType.CODE
        assert result.file_format == FileFormat.PYTHON

    def test_json_defaults_to_metadata(self, tmp_path: Path):
        f = tmp_path / "schema.json"
        f.write_text('{"key": "value"}')
        result = classify_by_extension(f)
        assert result is not None
        assert result.file_type == FileType.METADATA
        assert result.file_format == FileFormat.JSON

    def test_sas7bdat_extension(self, tmp_path: Path):
        f = tmp_path / "data.sas7bdat"
        f.write_bytes(b"\x00" * 100)
        result = classify_by_extension(f)
        assert result is not None
        assert result.file_type == FileType.DATA
        assert result.file_format == FileFormat.SAS7BDAT

    def test_txt_is_ambiguous(self, tmp_path: Path):
        f = tmp_path / "readme.txt"
        f.write_text("some text")
        result = classify_by_extension(f)
        assert result is None  # ambiguous → needs content sniffing

    def test_dat_is_ambiguous(self, tmp_path: Path):
        f = tmp_path / "values.dat"
        f.write_text("1,2,3")
        result = classify_by_extension(f)
        assert result is None

    def test_folder_heuristic_boosts_type(self, tmp_path: Path):
        ws = tmp_path / "workspace"
        data_dir = ws / "data"
        data_dir.mkdir(parents=True)
        f = data_dir / "report.pdf"
        f.write_bytes(b"%PDF-1.4 dummy")
        result = classify_by_extension(f)
        assert result is not None
        # DOCUMENTATION extension (.pdf) should maintain identity even in /data/ folder
        assert result.file_type == FileType.DOCUMENTATION
        assert result.file_format == FileFormat.PDF

    def test_unknown_extension_returns_other(self, tmp_path: Path):
        f = tmp_path / "mystery.xyz"
        f.write_text("???")
        result = classify_by_extension(f)
        assert result is not None
        assert result.file_type == FileType.OTHER
        assert result.file_format == FileFormat.UNDETERMINED


class TestMagicByteSniffer:
    """Tests for binary signature detection (Step 2)."""

    def test_parquet_magic(self, tmp_path: Path):
        f = tmp_path / "data.unknown"
        f.write_bytes(b"PAR1" + b"\x00" * 100)
        result = sniff_magic_bytes(f)
        assert result is not None
        assert result.file_format == FileFormat.PARQUET

    def test_pdf_magic(self, tmp_path: Path):
        f = tmp_path / "doc.unknown"
        f.write_bytes(b"%PDF-1.7 dummy content")
        result = sniff_magic_bytes(f)
        assert result is not None
        assert result.file_format == FileFormat.PDF

    def test_spss_magic(self, tmp_path: Path):
        f = tmp_path / "data.unknown"
        f.write_bytes(b"$FL2" + b"\x00" * 100)
        result = sniff_magic_bytes(f)
        assert result is not None
        assert result.file_format == FileFormat.SAV

    def test_sas_magic(self, tmp_path: Path):
        f = tmp_path / "data.unknown"
        header = b"\x00" * 10 + b"SAS FILE" + b"\x00" * 50
        f.write_bytes(header)
        result = sniff_magic_bytes(f)
        assert result is not None
        assert result.file_format == FileFormat.SAS7BDAT

    def test_no_match_returns_none(self, tmp_path: Path):
        f = tmp_path / "random.bin"
        f.write_bytes(b"random binary garbage content" * 5)
        result = sniff_magic_bytes(f)
        assert result is None


class TestTextHeuristicSniffer:
    """Tests for text-based delimiter detection (Step 3)."""

    def test_csv_detection(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("name,age,city\nAlice,30,NYC\nBob,25,LA\nCarol,35,SF\n")
        result = sniff_text_heuristic(f)
        assert result is not None
        assert result.file_type == FileType.DATA
        assert result.file_format == FileFormat.CSV
        assert result.attributes.get("textDelimiter") == ","

    def test_tsv_detection(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("name\tage\tcity\nAlice\t30\tNYC\nBob\t25\tLA\nCarol\t35\tSF\n")
        result = sniff_text_heuristic(f)
        assert result is not None
        assert result.file_type == FileType.DATA
        assert result.file_format == FileFormat.TSV
        assert result.attributes.get("textDelimiter") == "\t"

    def test_prose_returns_none(self, tmp_path: Path):
        f = tmp_path / "essay.txt"
        f.write_text(
            "This is a long paragraph of text that does not contain any tabular data.\n"
            "It is just plain prose written for documentation purposes.\n"
            "There are no delimiters or structured columns here.\n"
        )
        result = sniff_text_heuristic(f)
        assert result is None

    def test_empty_file_returns_none(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        result = sniff_text_heuristic(f)
        assert result is None


class TestSniffFileChain:
    """Integration tests for the full sniffer pipeline."""

    def test_csv_file(self, tmp_path: Path):
        f = tmp_path / "data.csv"
        f.write_text("a,b,c\n1,2,3\n4,5,6\n")
        result = sniff_file(f)
        assert result.file_type == FileType.DATA
        assert result.file_format == FileFormat.CSV
        assert result.mime_type == "text/csv"

    def test_pdf_file(self, tmp_path: Path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 dummy")
        result = sniff_file(f)
        assert result.file_type == FileType.DOCUMENTATION
        assert result.file_format == FileFormat.PDF
        assert result.mime_type == "application/pdf"

    def test_txt_tabular_reclassified(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("x,y,z\n1,2,3\n4,5,6\n7,8,9\n")
        result = sniff_file(f)
        assert result.file_type == FileType.DATA
        assert result.file_format in (FileFormat.CSV, FileFormat.TSV)

    def test_txt_prose_stays_documentation(self, tmp_path: Path):
        f = tmp_path / "readme.txt"
        f.write_text(
            "This is a readme file with some documentation.\n"
            "It explains how to use the software.\n"
            "There is no tabular data here.\n"
        )
        result = sniff_file(f)
        # Should either remain DOCUMENTATION or OTHER — not DATA
        assert result.file_type != FileType.DATA

    def test_unknown_extension_with_parquet_content(self, tmp_path: Path):
        f = tmp_path / "mystery.dat"
        f.write_bytes(b"PAR1" + b"\x00" * 100)
        result = sniff_file(f)
        assert result.file_format == FileFormat.PARQUET

    def test_display_label(self, tmp_path: Path):
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2\n")
        result = sniff_file(f)
        assert result.display_label() == "data/csv"

    def test_undetermined_display_label(self, tmp_path: Path):
        f = tmp_path / "mystery.xyz"
        f.write_text("???")
        result = sniff_file(f)
        assert "/" not in result.display_label() or "undetermined" not in result.display_label()
