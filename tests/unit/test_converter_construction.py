from tools.differential_jieba_test import _convert_cases


class _Converter:
    def __init__(self, config, owner):
        self.config = config
        self.owner = owner

    def convert(self, source):
        return f"{self.config}:{source}"


class _Module:
    def __init__(self):
        self.constructions = []

    def OpenCC(self, config):
        self.constructions.append(config)
        return _Converter(config, self)


def test_differential_reuses_one_converter_per_config():
    module = _Module()
    cases = [
        {"config": "s2t_jieba", "source": "a"},
        {"config": "s2t_jieba", "source": "b"},
        {"config": "tw2sp_jieba", "source": "c"},
        {"config": "s2t_jieba", "source": "d"},
    ]

    outputs = _convert_cases(module, cases)

    assert outputs == [
        "s2t_jieba:a",
        "s2t_jieba:b",
        "tw2sp_jieba:c",
        "s2t_jieba:d",
    ]
    assert module.constructions == ["s2t_jieba", "tw2sp_jieba"]
