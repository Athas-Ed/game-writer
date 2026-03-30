from src.services.skills_service import outline_writer_request_is_selection_followup


def test_followup_detects_scheme_button_phrase():
    text = (
        "我选择方案3，请根据上一轮助手回复继续："
        "展开该方案细节（或按上一轮说明保存/细化）。"
    )
    assert outline_writer_request_is_selection_followup(text) is True


def test_followup_detects_expand_selected():
    assert outline_writer_request_is_selection_followup("我要方案2，请展开该方案") is True


def test_not_followup_for_full_story():
    long = "世界观：西幻\n" * 30 + "第一幕：……\n"
    assert outline_writer_request_is_selection_followup(long) is False
