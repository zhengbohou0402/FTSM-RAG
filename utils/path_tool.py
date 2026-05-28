"""
为整个工程提供统一的绝对路径工具。
Provide unified absolute-path utilities for the whole project.

打包后（PyInstaller frozen 模式）：
- get_project_root() 返回 exe 同级目录（可写），用于数据库、配置、用户数据
- get_bundle_root() 返回 _MEIPASS 临时解压目录（只读），用于读取 bundled 资源
- get_abs_path() 智能 fallback：先找 exe 同级，找不到就回退到 bundle
"""
import os
import sys


def get_project_root() -> str:
    """
    运行时可写根目录。
    - 源码模式：工程根目录
    - 打包模式：exe 所在目录（用户数据写在这里）
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    return os.path.dirname(current_dir)


def get_bundle_root() -> str:
    """
    只读 bundle 根。
    - 源码模式：与 project_root 相同
    - 打包模式：_MEIPASS 临时解压目录（只读）
    """
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", get_project_root())
    return get_project_root()


def get_abs_path(relative_path: str) -> str:
    """
    返回相对路径对应的绝对路径。
    打包模式下优先返回可写目录下的路径；若该路径不存在则回退到 bundle 只读目录。
    写场景调用方可以直接使用返回值（若不存在会走可写路径）。
    """
    writable = os.path.join(get_project_root(), relative_path)
    if os.path.exists(writable):
        return writable
    bundle = os.path.join(get_bundle_root(), relative_path)
    if os.path.exists(bundle):
        return bundle
    return writable


if __name__ == '__main__':
    print(get_abs_path("config/config.txt"))
