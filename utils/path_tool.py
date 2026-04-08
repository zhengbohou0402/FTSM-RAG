"""
为整个工程提供统一的绝对路径工具。
Provide unified absolute-path utilities for the whole project.
"""
import os


def get_project_root() -> str:
    """
    获取工程所在的根目录。
    Get the project root directory.

    :return: 根目录字符串。/ Root directory as a string.
    """
    # 当前文件的绝对路径。/ Absolute path of the current file.
    current_file = os.path.abspath(__file__)
    # 先获取当前文件所在目录的绝对路径。/ First get the absolute path of the current file's directory.
    current_dir = os.path.dirname(current_file)
    # 再向上一层得到工程根目录。/ Then move one level up to get the project root.
    project_root = os.path.dirname(current_dir)

    return project_root


def get_abs_path(relative_path: str) -> str:
    """
    传入相对路径，返回对应的绝对路径。
    Convert a relative path to its absolute path.

    :param relative_path: 相对路径。/ Relative path.
    :return: 绝对路径。/ Absolute path.
    """
    project_root = get_project_root()
    return os.path.join(project_root, relative_path)


if __name__ == '__main__':
    print(get_abs_path("config/config.txt"))
