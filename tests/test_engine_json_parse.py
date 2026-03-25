from src.core.engine import _parse_llm_decision


def test_parse_final_json():
    d = _parse_llm_decision('{"type":"final","output":"ok"}')
    assert d["type"] == "final"
    assert d["output"] == "ok"


def test_parse_action_json():
    d = _parse_llm_decision('{"type":"action","tool":"ReadFile","input":"data/x.md"}')
    assert d["type"] == "action"
    assert d["tool"] == "ReadFile"
    assert d["input"] == "data/x.md"


def test_parse_invalid_json_falls_back_to_final_text():
    d = _parse_llm_decision("not json at all")
    assert d["type"] == "final"
    assert "not json" in d["output"]


def test_parse_json_with_wrapped_text_extracts_object():
    # 模拟“模型输出夹杂前后文本”的情况：中间应是可解析 JSON 对象
    text = "some prefix\n{\"type\":\"final\",\"output\":\"hi\"}\ntrailer"
    d = _parse_llm_decision(text)
    assert d["type"] == "final"
    assert d["output"] == "hi"

