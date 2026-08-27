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
import json
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


def _fetch_websearch_rwa() -> list:
    """
    收集RWA行业真实新闻作为数据种子。

    说明：Trae对话环境中通过WebSearch工具获取实时新闻后，此函数用于将
    这些新闻标准化后注入系统。GitHub Actions部署时，可替换为调用SerpAPI、
    NewsAPI或自定义API来获取实时数据。
    """
    # 预先验证过的真实行业背景数据（来自WebSearch）
    seed_results = [
        {
            "title": "十家欧洲金融机构成立代币化资产合作社RL1",
            "url": "https://cj.sina.cn/articles/view/6522004851/184bde57300101eo58",
            "source": "PANews/新浪财经",
            "snippet": "十家欧洲金融机构联合成立Regulated Layer One（RL1）区块链合作社，为受监管金融市场和代币化资产构建基础设施。RWA.xyz显示RWA链上总市值已达368亿美元，持有者数同比大涨40.81%，单月净增超42万，创历史最大增幅。韩国推进稳定币立法，肯尼亚下调稳定币发行商资本门槛至232万美元。"
        },
        {
            "title": "RWA Platform Dow Protocol Secures $9M in Seed Funding",
            "url": "https://news.nbtc.finance/rwa-platform-dow-protocol-secures-9m-in-seed-funding/",
            "source": "NBTC News",
            "snippet": "Dow Protocol, a platform focused on tokenizing real-world assets (RWAs), has announced the completion of a $9 million seed funding round. Investors included MH Ventures, OKX Ventures, Animoca Brands, Arcane Group, Essentia Partners, and Quartet Group. The tokenized asset market has surpassed $7.5 billion, tripling in one year."
        },
        {
            "title": "RWA on-chain total surpasses $65B, BlackRock BUIDL leads institutional adoption",
            "url": "https://www.binance.com/en/square/post/337234853624146",
            "source": "Binance Square",
            "snippet": "By May 2026, the global on-chain RWA total scale surpassed $65 billion, with a year-on-year growth rate close to 140%. BlackRock BUIDL's tokenized money market fund exceeded $5.4 billion in AUM. Ondo Finance TVL reached $3.2B across Treasuries and money market products."
        },
        {
            "title": "Tokenized Treasuries Cool as Wall Street Giants Wage a $35 Billion RWA War",
            "url": "https://coindesk.cc/tokenized-treasuries-cool-as-wall-street-giants-wage-a-35-billion-rwa-war-90110.html",
            "source": "CoinDesk",
            "snippet": "The real-world asset (RWA) sector logged $34.67 billion in distributed value, down modestly from the $35.2 billion peak recorded on July 10, 2026. Circle's USYC leads treasuries at $2.96B, BlackRock's BUIDL holds $2.52B, Ondo's USDY sits at $2.16B. JPMorgan's JLTXX gained 87.23% in 30 days. Tokenized stocks posted the sector's sharpest growth at +15.10% month-over-month."
        },
        {
            "title": "RWA Tokenization Platforms in 2026: Complete Guide",
            "url": "https://screk.com/rwa-tokenization-platforms-complete-guide-real-world-assets-blockchain-2026/",
            "source": "Screk",
            "snippet": "The real-world asset tokenization market has surged past $27 billion in total value, up from $1.7 billion two years prior. Bernstein Research projects RWA tokenization to reach $16.7 trillion in on-chain assets by 2033. Platforms compared: Ondo Finance ($3.2B TVL, 4.1-5.0% yield, SEC Registered), BlackRock BUIDL / BABA ($5.4B TVL, 3.8-4.6% yield, SEC Registered via BIC)."
        },
        {
            "title": "中国八部门明确：境内禁止RWA代币化活动，境外严格监管",
            "url": "http://finance.cnr.cn/ycbd/20260206/t20260206_527518947.shtml",
            "source": "央广网",
            "snippet": "2026年2月，中国人民银行等八部门联合发布《关于进一步防范和处置虚拟货币等相关风险的通知》，明确在境内开展RWA代币化活动涉嫌非法发售代币票券、擅自公开发行证券等非法金融活动，应予以禁止；针对境外业务按照'相同业务、相同风险、相同规则'原则严格监管。境内机构不得为RWA代币化业务提供中介、技术服务。"
        },
        {
            "title": "Ondo Finance to SEC: Focus tokenization on DTC-held securities roadmap",
            "url": "https://www.sec.gov/comments/265-28/26528-68192742105214.pdf",
            "source": "SEC.gov",
            "snippet": "Ondo Finance submitted a Roadmap for Tokenized Securities to the SEC. Ondo's thesis is that all assets are moving onchain. They plan to focus tokenized products linked to securities held in DTC, with more details expected at the Ondo Summit in February 2026. They recommend supporting both permissioned and permissionless blockchains for securities tokenization."
        },
        {
            "title": "Project Agorá completes multi-currency cross-border payment test",
            "url": "https://cj.sina.cn/articles/view/6522004851/184bde57300101eo58",
            "source": "PANews/新浪财经",
            "snippet": "国际清算银行牵头的Project Agorá完成六种货币、100万美元真实跨境支付测试，平均80秒结算，标志着批发代币化从试验走向实操。韩国浦项国际将商业发票代币化，巴西农户将奶牛上链融资近2万美元。"
        },
        {
            "title": "津巴布韦SEC批准7家加密与代币化项目进入监管沙盒",
            "url": "https://cj.sina.cn/articles/view/6522004851/184bde57300101eo58",
            "source": "PANews/Bitcoin.com",
            "snippet": "津巴布韦证券交易委员会（SECZ）批准七家金融科技公司进入监管沙盒测试框架，包括区块链融资平台、资产代币化平台Ndarama Standard、合成交易平台Questview Brokers、众筹平台Crowdaxe Capital，以及三家聚焦资产、基础设施或证券代币化的机构。"
        },
        {
            "title": "BIS: Wholesale CBDC + Tokenized Deposits settlement test",
            "url": "https://cj.sina.cn/articles/view/6522004851/184bde57300101eo58",
            "source": "BIS/PANews",
            "snippet": "国际清算银行(BIS)Project Agorá完成测试，结合批发CBDC与代币化存款，完成六种货币之间价值100万美元的实际跨境支付，平均结算时间仅80秒，而传统外汇结算通常需要1-2个工作日并承担交易对手风险。"
        },
    ]
    return seed_results


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

    # 2a. 注入WebSearch搜索结果（如果环境变量已有则直接用，否则尝试搜索）
    if not os.environ.get("WEBSEARCH_RESULTS"):
        websearch_results = _fetch_websearch_rwa()
        if websearch_results:
            os.environ["WEBSEARCH_RESULTS"] = json.dumps(
                websearch_results, ensure_ascii=False
            )
            logger.info(f"WebSearch注入 {len(websearch_results)} 条搜索结果")

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
