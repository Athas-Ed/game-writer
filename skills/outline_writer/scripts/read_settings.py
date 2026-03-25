from src.tools.file_tools import read_settings_bundle


def read_all_settings() -> str:
    # 兼容旧接口：技能内部仍调用 read_all_settings()
    return read_settings_bundle()

if __name__ == "__main__":
    # 测试
    print(read_all_settings())