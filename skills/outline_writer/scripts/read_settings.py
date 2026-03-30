from src.tools.file_tools import read_settings_bundle
from src.tools.setting_context import read_settings_for_retrieval


def read_all_settings() -> str:
    """整包读取设定（兼容旧接口与脚本直接调试）。"""
    return read_settings_bundle()


def read_settings_for_outline(user_plot_line: str) -> str:
    """大纲生成专用，等价于 read_settings_for_retrieval（剧情句作检索种子）。"""
    return read_settings_for_retrieval(user_plot_line)


if __name__ == "__main__":
    print(read_all_settings())
