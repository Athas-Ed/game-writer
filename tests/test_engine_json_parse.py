import json

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


def test_parse_final_unwraps_nested_protocol_json():
    inner_str = json.dumps({"type": "final", "output": "大纲已成功保存。"}, ensure_ascii=False)
    outer = json.dumps({"type": "final", "output": inner_str}, ensure_ascii=False)
    d = _parse_llm_decision(outer)
    assert d["type"] == "final"
    assert d["output"] == "大纲已成功保存。"
    assert '{"type":"final"' not in d["output"]


def test_parse_action_tolerates_trailing_extra_brace():
    """模型多打一个 } 时，应用配平截取，仍应识别为 action 而非把整个响应当 final。"""
    core = '{"type":"action","tool":"WriteFile","input":"data/x.md|hello"}'
    d = _parse_llm_decision(core + "\n}")
    assert d["type"] == "action"
    assert d["tool"] == "WriteFile"
    assert d["input"] == "data/x.md|hello"


def test_parse_action_with_prefix_and_trailing_garbage():
    d = _parse_llm_decision('好的\n{"type":"action","tool":"ReadFile","input":"data/a.md"}\n谢谢')
    assert d["type"] == "action"
    assert d["tool"] == "ReadFile"

