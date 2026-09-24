import pytest

from document.validation import validate_xhtml_syntax


def test_xhtml_validation_maps_doctype_multiline_error_to_source_coordinates():
    source = (
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"\n'
        '  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n'
        "<p>valid</p>\n"
        "<div>valid</div>\n"
        "<p><b>12</p>\n"
    )

    with pytest.raises(ValueError) as caught:
        validate_xhtml_syntax(source)

    assert getattr(caught.value, "line", None) == 5
    assert getattr(caught.value, "column", None) == 11


def test_xhtml_validation_removes_wrapper_prefix_from_first_line_column():
    with pytest.raises(ValueError) as caught:
        validate_xhtml_syntax("<p>汉字<br></p>")

    assert getattr(caught.value, "line", None) == 1
    assert getattr(caught.value, "column", None) == 12


def test_xhtml_validation_preserves_column_after_named_entity():
    with pytest.raises(ValueError) as caught:
        validate_xhtml_syntax("<p>&amp;<b>12</p>")

    assert getattr(caught.value, "column", None) == 16
