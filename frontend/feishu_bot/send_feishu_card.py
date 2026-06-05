#!/usr/bin/env python3
"""通过飞书机器人 Webhook 发送 TikTok LIVE Case 卡片消息。

用法示例：
    python3 send_feishu_card.py 1
    python3 send_feishu_card.py 2
    python3 send_feishu_card.py 3
    python3 send_feishu_card.py all  # 发送三案例合集卡片
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List
from urllib import request, error

# TODO: 将这里替换成你自己的飞书机器人 Webhook URL
WEBHOOK_URL = "https://open.larkoffice.com/open-apis/bot/v2/hook/fd51d666-65bb-4140-a183-e5ef5068e475"

# 卡片文件映射。脚本会根据命令行参数读取对应 JSON 文件。
CARD_FILES = {
    "1": "case_01_card.json",
    "2": "case_02_card.json",
    "3": "case_03_card.json",
    "all": "combined_card.json",
}


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="通过飞书机器人 Webhook 发送指定 Case 的交互式卡片。"
    )
    parser.add_argument(
        "case",
        choices=["1", "2", "3", "all"],
        help="要发送的 Case 编号，支持 1 / 2 / 3 / all",
    )
    return parser.parse_args()


def get_target_card_paths(case_value: str) -> List[Path]:
    """根据参数返回要发送的卡片文件路径列表。"""
    base_dir = Path(__file__).resolve().parent
    return [base_dir / CARD_FILES[case_value]]


def load_card_payload(card_path: Path) -> dict:
    """读取完整的 Webhook 消息 JSON。"""
    with card_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if payload.get("msg_type") != "interactive":
        raise ValueError(f"{card_path.name} 缺少正确的 msg_type=interactive")

    if "card" not in payload:
        raise ValueError(f"{card_path.name} 缺少 card 字段")

    return payload


def send_card(webhook_url: str, payload: dict) -> dict:
    """向飞书 Webhook 发送单张卡片。"""
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with request.urlopen(req) as response:
            response_text = response.read().decode("utf-8")
            return json.loads(response_text)
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} 错误：{error_body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"网络请求失败：{exc.reason}") from exc


def main() -> int:
    """程序主入口。"""
    args = parse_args()

    if WEBHOOK_URL == "YOUR_WEBHOOK_URL":
        print("请先在脚本中把 WEBHOOK_URL 替换为真实的飞书机器人 Webhook 地址。", file=sys.stderr)
        return 1

    card_paths = get_target_card_paths(args.case)

    for card_path in card_paths:
        if not card_path.exists():
            print(f"未找到卡片文件：{card_path}", file=sys.stderr)
            return 1

        payload = load_card_payload(card_path)
        result = send_card(WEBHOOK_URL, payload)
        print(f"已发送 {card_path.name}，返回结果：{json.dumps(result, ensure_ascii=False)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
