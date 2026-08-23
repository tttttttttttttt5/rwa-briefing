#!/usr/bin/env python3
"""
RWA 创业信息简报系统 - 主入口脚本

用法:
    python main.py                      # 按config.yaml配置的频率模式运行
    python main.py --mode daily         # 强制每日简报模式
    python main.py --mode major_only    # 强制重大事件模式
    python main.py --mode weekly        # 强制每周汇总模式
    python main.py --dry-run            # 只生成简报不发邮件
    python main.py --config custom.yaml # 指定自定义配置文件
"""

import sys
import os
import argparse
import logging
from datetime import datetime, timezone, timedelta

# 确保src目录在路径中
sys.path.insert(
    0,
    os.path.dirname(os.path.abspath(__file__))
)

from src.config_loader import load_config
from src.data_collector import DataCollector
from src.event_classifier import EventClassifier
from src.briefing_generator import BriefingGenerator
from src.email_sender import EmailSender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("main")


def parse_args():
    parser = argparse.ArgumentParser(description="RWA创业信息简报系统")
    parser.add_argument(
        "--mode",
        choices=["daily", "major_only", "weekly"],
        default=None,
        help="推送模式（不指定则使用config.yaml中的配置）"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="配置文件路径（默认: config.yaml）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行模式：生成简报但不发送邮件"
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=48,
        help="回溯采集多少小时内的新闻（默认48小时）"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    # ========== 1. 加载配置 ==========
    logger.info(f"=" * 60)
    logger.info(f"RWA创业信息简报系统启动")
    logger.info(f"=" * 60)
    logger.info(f"配置文件: {args.config}")
    
    try:
        config = load_config(args.config)
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        sys.exit(1)
    
    # 确定运行模式
    mode = args.mode or config["push"].get("frequency", "daily")
    logger.info(f"运行模式: {mode}")
    
    # ========== 2. 数据收集 ==========
    logger.info(f"回溯时间: {args.lookback_hours}小时")
    logger.info("开始数据收集...")
    
    collector = DataCollector(config)
    raw_events = collector.collect_all(lookback_hours=args.lookback_hours)
    
    if not raw_events:
        logger.warning("未采集到任何新闻事件，退出")
        sys.exit(0)
    
    logger.info(f"数据收集完成，共 {len(raw_events)} 条RWA相关新闻")
    
    # ========== 3. 事件分析与分类 ==========
    logger.info("开始事件AI分析（标签匹配 + 重要程度评分）...")
    
    classifier = EventClassifier(config)
    processed_events = classifier.process_events(raw_events)
    
    # 分类统计
    high_count = len([e for e in processed_events if e.importance == "high"])
    medium_count = len([e for e in processed_events if e.importance == "medium"])
    low_count = len([e for e in processed_events if e.importance == "low"])
    headlines = len([e for e in processed_events if e.is_headline])
    
    logger.info(
        f"分析完成: 🔴高{high_count} 🟡中{medium_count} 🟢低{low_count} "
        f"| 头条{headlines}条"
    )
    
    # ========== 4. 更新趋势数据 ==========
    logger.info("更新标签趋势历史数据...")
    classifier.update_trend_data(processed_events)
    trend_summary = classifier.get_trend_summary()
    
    if trend_summary.get("trending_up"):
        up_tags = [t[0] for t in trend_summary["trending_up"]]
        logger.info(f"🔥 上升趋势标签: {', '.join(up_tags)}")
    
    # ========== 5. 生成简报 ==========
    logger.info("生成Markdown简报...")
    
    generator = BriefingGenerator(config)
    markdown_content = generator.generate(processed_events, trend_summary, mode)
    
    # 保存简报到本地（无论是否发送邮件）
    output_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "output"
    )
    os.makedirs(output_dir, exist_ok=True)
    
    now_bj = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
    md_filename = f"briefing_{mode}_{now_bj.strftime('%Y%m%d_%H%M')}.md"
    md_filepath = os.path.join(output_dir, md_filename)
    
    with open(md_filepath, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    
    logger.info(f"简报已保存: {md_filepath}")
    
    # ========== 6. 发送邮件 ==========
    if args.dry_run:
        logger.info("=== 试运行模式 (dry-run) ===")
        logger.info("简报预览:")
        logger.info("=" * 60)
        print(markdown_content[:3000])
        if len(markdown_content) > 3000:
            print("\n... (内容过长，已截断，完整内容请查看 output/latest.md)")
        logger.info("=" * 60)
        logger.info("试运行模式，未发送邮件")
    else:
        logger.info("准备发送邮件...")
        sender = EmailSender(config)
        
        if sender.should_send(processed_events):
            success = sender.send(markdown_content, mode)
            if success:
                logger.info("✅ 简报推送流程完成")
            else:
                logger.warning("⚠️ 邮件发送失败（已保存本地备份）")
        else:
            logger.info("本期不满足推送条件（如'仅重大事件'模式下无重大事件），跳过邮件发送")
    
    logger.info(f"=" * 60)
    logger.info(f"系统运行完成")
    logger.info(f"=" * 60)


if __name__ == "__main__":
    main()
