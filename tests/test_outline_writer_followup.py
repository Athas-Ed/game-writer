from src.services.skills_service import (
    augment_user_input_if_implicit_dialogue_scheme_pick,
    assistant_message_is_dialogue_voice_two_schemes,
    dialogue_voice_scheme_pick_payload,
    outline_writer_request_is_selection_followup,
)


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


def test_dialogue_streamlit_pick_not_outline_selection():
    """对白两套方案按钮含【对白】，不得被当成大纲选型续写。"""
    text = (
        "我选择方案1，请根据上一轮助手回复继续："
        "【对白】对选定方案润色、扩写。"
        "不要使用 outline-writer / 大纲写手。"
    )
    assert dialogue_voice_scheme_pick_payload(text) is True
    assert outline_writer_request_is_selection_followup(text) is False


def test_assistant_dialogue_voice_detection():
    assert assistant_message_is_dialogue_voice_two_schemes("已执行技能 dialogue-voice，生成 2 组对白方案：") is True
    assert assistant_message_is_dialogue_voice_two_schemes("方案1:\na\n方案2:\nb\n方案3:\nc") is False


def test_augment_implicit_dialogue_scheme_pick():
    hist = [
        {
            "role": "assistant",
            "content": "已执行技能 dialogue-voice，生成 2 组对白方案（语气/节奏不同）：\n\n方案1:\nA\n\n方案2:\nB",
        }
    ]
    raw = "我选择方案1，请润色扩展。"
    out = augment_user_input_if_implicit_dialogue_scheme_pick(raw, hist)
    assert out.startswith(raw)
    assert "【对白】【由系统根据上一轮助手输出自动标注】" in out
    assert "outline-writer" in out and "大纲写手" in out


def test_no_augment_when_last_not_dialogue_voice():
    hist = [{"role": "assistant", "content": "方案1：……\n方案2：……\n方案3：……"}]
    raw = "我选择方案1"
    assert augment_user_input_if_implicit_dialogue_scheme_pick(raw, hist) == raw


def test_no_augment_without_history():
    assert augment_user_input_if_implicit_dialogue_scheme_pick("我选择方案1", None) == "我选择方案1"
