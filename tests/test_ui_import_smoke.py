def test_streamlit_app_imports():
    # 仅做 import 冒烟，确保重构后不会在 import 阶段抛异常
    import src.ui.streamlit_app  # noqa: F401

