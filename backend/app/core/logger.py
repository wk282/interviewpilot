import sys
import os
from loguru import logger

# ==========================================
# 知识点讲解:
# loguru 是目前 Python 生态中最流行、最现代化的第三方日志库。
# 相比于标准库的 logging 需要繁琐地配置 Handler 和 Formatter，
# loguru 开箱即用，自带极度优雅的彩色控制台输出，并且支持按大小/时间自动切割文件（Rotation）。
# 
# ⚠️ 注意：使用前需要在终端安装依赖：pip install loguru
# ==========================================

def setup_logger():
    """
    配置并返回全局单例的 loguru logger。
    其实 loguru 的核心设计理念是“开箱即用的单例”，你不需要到处实例化它。
    """
    # 1. 先移除 loguru 默认的控制台输出，避免和我们自定义的输出重复
    logger.remove()

    # [新加入的代码]：解决 Windows 环境默认使用 GBK 编码导致打印 Emoji 时抛出 UnicodeEncodeError 的报错
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # 2. 重新添加控制台输出 (添加彩色支持和精细化格式)
    # <green>、<cyan> 等标签会自动为终端文字上色，找报错的时候极度直观！
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )

    # 3. 添加本地文件输出
    # 【知识点】：如果只写 log_dir = "logs"（相对路径），它是基于你“在终端执行 python 命令时所在的路径”来创建的。
    # 这在企业级开发中是大忌（如果切换目录运行，日志位置就变了）。
    # 企业级做法：基于当前文件（__file__）的绝对路径，反推项目根目录。
    # 当前文件在 app/core/logger.py，向上退三层就是 ResearchPilot 根目录。
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    log_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # 4. loguru 的企业级杀手功能：自动轮转（Rotation）与保留策略（Retention）
    # rotation="10 MB": 单个日志文件一旦超过 10MB，就自动切分，打包新建一个文件
    # retention="7 days": 历史日志文件最多保留 7 天，过期的自动删除（再也不用写定时脚本清磁盘了！）
    process_role = "celery" if any("celery" in argument.lower() for argument in sys.argv) else "app"
    logger.add(
        os.path.join(log_dir, f"{process_role}_{{time:YYYY-MM-DD}}.log"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="INFO",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )
    
    return logger

# 在本模块被加载时就直接执行配置
setup_logger()

# 对外暴露配好的单例 logger
# 在其他所有的文件里，以后再也不用繁琐的 getLogger 了
# 只需要：from app.core.logger import logger
# 然后直接：logger.info("企业级 VLM 解析启动！")
