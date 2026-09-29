from dataclasses import fields
from importlib import import_module
from importlib.util import find_spec
import json
from pathlib import Path


_STUB_MODULES = (
    "app.commands",
    "core.pipeline",
    "document.attribute_scanner",
    "document.metadata",
    "document.protected_content",
    "document.ruby",
    "document.svg",
    "document.text_targets",
    "document.xhtml_processor",
    "opencc_backend.interface",
    "sigil.preferences",
    "transforms.annotations",
)

_UNUSED_SYMBOLS = {
    "rules.importers": (
        "parse_rules", "import_tsv", "import_csv", "import_json", "import_opencc_txt",
    ),
    "rules.exporters": (
        "export_json", "export_tsv", "export_csv", "export_opencc_txt",
    ),
    "rules.store": ("save_ruleset", "load_ruleset"),
    "rules.precedence": ("precedence_key",),
    "rules.validators": ("ValidationIssue",),
    "rules.models": ("_new_id", "RuleSnapshot.build", "RuleSnapshot.from_rules"),
    "rules.conflicts": ("detect_conflicts",),
    "core.classifier": ("comparative_classification",),
    "core.diagnostics": ("diagnose_script", "diagnostic_schema_version"),
    "core.converter": ("Converter",),
    "document.diagnostics": ("inline_boundary_codes", "find_inline_boundaries"),
    "document.tokenizer": ("tokenizer_strategy", "_split_entity_boundaries"),
    "document.xml_processor": ("processor_name",),
    "transforms.punctuation": ("transform_punctuation",),
    "transforms.quotations": ("convert_quotations",),
    "logging_ext.report": ("report_schema_version", "validate_report"),
    "logging_ext.retention": ("cleanup_history",),
    "logging_ext.history": ("HistoryStore.report_inputs",),
    "app.profiles": ("load_profile",),
    "app.errors": ("ConversionError", "VerificationError"),
}

_UNUSED_I18N_KEYS = {
    "rules.default_settings",
    "scope.run_summary_documents",
    "scope.selected_file",
    "history.select",
    "history.status.partial_failure",
    "history.status.failed",
    "history.status.cancelled",
    "result.status.cancelled",
    "rules.new_ruleset",
    "rules.opencc_label",
    "rules.pre_rules_label",
    "rules.post_rules_label",
    "rules.transfer_group",
    "preview.apply_decisions",
    "rules.confidence.medium",
}


def test_simp04_removes_unreferenced_modules_symbols_and_i18n_keys():
    for module in _STUB_MODULES:
        assert find_spec(module) is None, module

    for module_name, names in _UNUSED_SYMBOLS.items():
        module = import_module(module_name)
        for name in names:
            owner, _, attribute = name.rpartition(".")
            target = getattr(module, owner) if owner else module
            assert not hasattr(target, attribute or name), f"{module_name}.{name}"

    compiled = import_module("rules.compiled")
    assert "index" not in {item.name for item in fields(compiled.CompiledOverlay)}

    root = Path(__file__).resolve().parents[2]
    from tools.validate_artifact import _I18N_REQUIRED_KEYS, _REQUIRED_MEMBERS

    assert _UNUSED_I18N_KEYS.isdisjoint(_I18N_REQUIRED_KEYS)
    assert "OpenCCForSigil/resources/schemas/profile.schema.json" not in _REQUIRED_MEMBERS
    for locale in ("en", "zh-Hans", "zh-Hant"):
        catalog = json.loads(
            (root / "plugin/OpenCCForSigil/resources/i18n" / f"{locale}.json")
            .read_text(encoding="utf-8")
        )
        assert _UNUSED_I18N_KEYS.isdisjoint(catalog), locale
