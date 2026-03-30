from src.ui.scheme_options import assistant_message_dict, extract_scheme_options, message_scheme_options


def test_extract_scheme_options_three_plans():
    text = """已执行技能，生成 3 个大纲方案：

方案1:
悬疑走向，主角发现信是假的。

方案2:
温情走向，信来自旧友。

方案3:
奇幻走向，信是传送门钥匙。
"""
    opts = extract_scheme_options(text)
    assert opts is not None
    assert len(opts) == 3
    assert opts[0]["id"] == "1" and "悬疑" in opts[0]["preview"]
    assert opts[2]["label"] == "方案3"


def test_extract_scheme_options_single_plan_returns_none():
    assert extract_scheme_options("方案1:\n只有一条") is None


def test_assistant_message_dict_attaches_cache():
    text = "方案1:\nA\n\n方案2:\nB\n"
    msg = assistant_message_dict(text)
    assert msg["scheme_options"] is not None
    assert message_scheme_options(msg) is not None
