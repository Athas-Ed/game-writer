from src.core.policy import should_short_circuit_for_preferences


def test_short_circuit_disabled_prefs_detects_improvement_intent():
    assert should_short_circuit_for_preferences("以后都要给我四个方案", prefs_enabled=False) is True


def test_short_circuit_enabled_prefs_never_short_circuits():
    assert should_short_circuit_for_preferences("以后都要给我四个方案", prefs_enabled=True) is False


def test_short_circuit_disabled_prefs_normal_query_not_short_circuit():
    assert should_short_circuit_for_preferences("帮我写一个角色设定", prefs_enabled=False) is False

