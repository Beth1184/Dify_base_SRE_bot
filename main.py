"""服务入口：启动飞书长连接客户端。

运行方式：
    python main.py

流程：加载配置 → 校验配置 → 初始化服务 → 注册事件处理器 → 建立 WebSocket 长连接（阻塞）。
"""
from __future__ import annotations

import logging

import lark_oapi as lark

from config import config
from feishu_handler import build_event_handler, init_services, resolve_domain


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main() -> None:
    setup_logging()

    missing = config.validate()
    if missing:
        logging.error(
            "缺少必要配置：%s，请先填写项目根目录的 .env 文件（可参考 .env.example）",
            ", ".join(missing),
        )
        return

    init_services()

    event_handler = build_event_handler()
    domain = resolve_domain(config.FEISHU_DOMAIN)

    kwargs = {"event_handler": event_handler, "log_level": lark.LogLevel.INFO}
    if domain is not None:
        kwargs["domain"] = domain

    cli = lark.ws.Client(config.FEISHU_APP_ID, config.FEISHU_APP_SECRET, **kwargs)
    logging.info("SRE 运维助手已启动，正在建立飞书长连接...")
    cli.start()


if __name__ == "__main__":
    main()
