"""
RWA 创业信息简报系统
数据收集模块 - 从多个来源收集RWA相关新闻和动态
"""
import re
import time
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

import requests
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class NewsEvent:
    """标准化的新闻事件数据结构"""
    event_id: str
    title: str
    summary: str
    source: str
    url: str
    published_at: datetime
    raw_content: str = ""
    # 后续处理会填充的字段
    tags: List[str] = field(default_factory=list)
    importance: str = "low"  # high / medium / low
    importance_score: float = 0.0
    matched_protocols: List[str] = field(default_factory=list)
    matched_regions: List[str] = field(default_factory=list)
    funding_amount: Optional[float] = None  # 融资规模（万美元）
    is_headline: bool = False


class DataCollector:
    """多源数据收集器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        # RWA相关关键词过滤
        self.rwa_keywords = [
            "rwa", "real world asset", "tokeniz", "代币化", "stablecoin", "稳定币",
            "compliance", "合规", "监管", "funding", "融资", "investment", "投资",
            "custody", "托管", "lending", "借贷", "credit", "信贷", "t-bill", "国债",
            "treasur", "债券", "yield", "收益", "apy", "institutional", "机构"
        ]
    
    def collect_all(self, lookback_hours: int = 48) -> List[NewsEvent]:
        """
        从所有数据源收集数据
        
        Args:
            lookback_hours: 回溯多少小时内的新闻
            
        Returns:
            去重后的新闻事件列表
        """
        all_events: List[NewsEvent] = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        
        # 1. RSS源
        rss_events = self._collect_rss_feeds(cutoff_time)
        all_events.extend(rss_events)
        logger.info(f"RSS源收集到 {len(rss_events)} 条新闻")
        
        # 2. 模拟BlockBeats/KuCoin数据（实际部署时接入真实API）
        simulated_events = self._collect_simulated_data(cutoff_time)
        all_events.extend(simulated_events)
        logger.info(f"模拟数据源收集到 {len(simulated_events)} 条新闻")
        
        # 去重
        deduped_events = self._deduplicate_events(all_events)
        logger.info(f"去重后共 {len(deduped_events)} 条新闻")
        
        # 过滤RWA相关内容
        rwa_events = self._filter_rwa_related(deduped_events)
        logger.info(f"RWA相关新闻共 {len(rwa_events)} 条")
        
        return rwa_events
    
    def _collect_rss_feeds(self, cutoff_time: datetime) -> List[NewsEvent]:
        """收集RSS订阅源"""
        events = []
        feeds = self.config.get("data_sources", {}).get("rss_feeds", [])
        
        for feed_config in feeds:
            try:
                events.extend(self._parse_single_feed(feed_config, cutoff_time))
            except Exception as e:
                logger.warning(f"解析RSS源失败 [{feed_config.get('name')}]: {e}")
                continue
        
        return events
    
    def _parse_single_feed(self, feed_config: Dict, cutoff_time: datetime) -> List[NewsEvent]:
        """解析单个RSS源"""
        events = []
        url = feed_config["url"]
        source_name = feed_config.get("name", "Unknown")
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except Exception as e:
            logger.warning(f"获取RSS失败 {source_name}: {e}")
            return events
        
        for entry in feed.entries:
            try:
                # 解析发布时间
                pub_date = self._parse_entry_date(entry)
                if pub_date and pub_date < cutoff_time:
                    continue
                if not pub_date:
                    pub_date = datetime.now(timezone.utc)
                
                title = getattr(entry, "title", "").strip()
                summary = getattr(entry, "summary", getattr(entry, "description", "")).strip()
                # 清理HTML标签
                summary = BeautifulSoup(summary, "lxml").get_text()[:500]
                link = getattr(entry, "link", "")
                
                if not title:
                    continue
                
                event_id = self._generate_event_id(title, link)
                raw_content = title + " " + summary
                
                event = NewsEvent(
                    event_id=event_id,
                    title=title,
                    summary=summary,
                    source=source_name,
                    url=link,
                    published_at=pub_date,
                    raw_content=raw_content
                )
                events.append(event)
                
            except Exception as e:
                logger.debug(f"解析RSS条目失败: {e}")
                continue
        
        return events
    
    def _collect_simulated_data(self, cutoff_time: datetime) -> List[NewsEvent]:
        """
        模拟数据（演示用）
        实际部署时：
        - 接入 BlockBeats API: https://api.theblockbeats.news/
        - 接入 KuCoin Crypto Pulse API
        - 接入各个项目的 Medium/LinkedIn RSS
        """
        simulated_news = [
            {
                "title": "BlackRock扩大BUIDL基金规模，已突破30亿美元",
                "summary": "全球最大资产管理公司贝莱德旗下的BUIDL代币化国债基金规模再创新高，突破30亿美元，显示机构对RWA需求持续增长。",
                "source": "模拟数据源",
                "url": "https://example.com/blackrock-buidl-3b",
                "hours_ago": 2
            },
            {
                "title": "Morpho完成8000万美元B轮融资，a16z领投",
                "summary": "DeFi借贷协议Morpho宣布完成8000万美元B轮融资，a16z领投，本轮融资将用于拓展RWA借贷产品线和机构业务。",
                "source": "模拟数据源",
                "url": "https://example.com/morpho-funding",
                "hours_ago": 5
            },
            {
                "title": "香港证监会发布代币化证券指引，预计Q3正式实施",
                "summary": "香港证监会今日发布证券型代币发行(STO)新指引，明确代币化证券的发行、托管、交易等合规要求，为RWA项目在港发展提供清晰框架。",
                "source": "模拟数据源",
                "url": "https://example.com/hk-sfc-guideline",
                "hours_ago": 8
            },
            {
                "title": "Centrifuge推出新版预言机模块，提升RWA定价精度",
                "summary": "资产代币化协议Centrifuge发布全新预言机集成方案，整合Chainlink和自定义定价源，为真实世界资产提供更精准的链上定价。",
                "source": "模拟数据源",
                "url": "https://example.com/centrifuge-oracle",
                "hours_ago": 12
            },
            {
                "title": "Ondo Finance与渣打银行合作推出代币化现金管理产品",
                "summary": "RWA代币化平台Ondo Finance宣布与渣打银行达成战略合作，联合推出面向机构投资者的代币化现金管理产品，预计年化收益率4.5-5.5%。",
                "source": "模拟数据源",
                "url": "https://example.com/ondo-standard-chartered",
                "hours_ago": 16
            },
            {
                "title": "新加坡MAS完成首个代币化国债回购试点",
                "summary": "新加坡金融管理局(MAS)宣布完成行业首个代币化新加坡国债回购协议试点，多家银行参与，验证了RWA结算效率提升潜力。",
                "source": "模拟数据源",
                "url": "https://example.com/mas-treasury-pilot",
                "hours_ago": 20
            },
            {
                "title": "Goldfinch信贷池新增2亿美元现实世界资产",
                "summary": "去中心化信贷协议Goldfinch宣布其核心信贷池新增加入2亿美元现实世界贷款资产，主要来自东南亚和拉丁美洲的中小企业信贷。",
                "source": "模拟数据源",
                "url": "https://example.com/goldfinch-200m",
                "hours_ago": 24
            },
            {
                "title": "Hyperliquid上线首个代币化国债期货合约",
                "summary": "去中心化衍生品交易所Hyperliquid宣布上线首个代币化短期国债期货产品，为用户提供链上利率对冲工具。",
                "source": "模拟数据源",
                "url": "https://example.com/hyperliquid-tbill-futures",
                "hours_ago": 28
            },
            {
                "title": "Maple Finance完成1500万美元融资，计划拓展美国机构客户",
                "summary": "机构信贷协议Maple Finance完成1500万美元新一轮融资，本轮融资将主要用于美国市场拓展和合规牌照申请。",
                "source": "模拟数据源",
                "url": "https://example.com/maple-funding",
                "hours_ago": 32
            },
            {
                "title": "瑞士FINMA发布DeFi合规报告，认可RWA代币化合规路径",
                "summary": "瑞士金融市场监管局(FINMA)发布最新DeFi行业监管报告，明确RWA代币化项目的合规框架，为瑞士成为RWA中心铺路。",
                "source": "模拟数据源",
                "url": "https://example.com/finma-defi-report",
                "hours_ago": 36
            },
            {
                "title": "Frax推出代币化房地产基金，首付门槛降至1万美元",
                "summary": "算法稳定币协议Frax扩展RWA版图，推出代币化美国商业房地产基金，利用碎片化方式降低投资者参与门槛。",
                "source": "模拟数据源",
                "url": "https://example.com/frax-real-estate",
                "hours_ago": 40
            },
            {
                "title": "Stork预言机新增15种RWA资产喂价",
                "summary": "去中心化预言机网络Stork宣布新增15种真实世界资产价格喂价服务，包括公司债、REITs、大宗商品等。",
                "source": "模拟数据源",
                "url": "https://example.com/stork-rwa-feeds",
                "hours_ago": 44
            }
        ]
        
        events = []
        now = datetime.now(timezone.utc)
        
        for news in simulated_news:
            pub_date = now - timedelta(hours=news["hours_ago"])
            if pub_date < cutoff_time:
                continue
            
            event_id = self._generate_event_id(news["title"], news["url"])
            raw_content = news["title"] + " " + news["summary"]
            
            event = NewsEvent(
                event_id=event_id,
                title=news["title"],
                summary=news["summary"],
                source=news["source"],
                url=news["url"],
                published_at=pub_date,
                raw_content=raw_content
            )
            events.append(event)
        
        return events
    
    def _parse_entry_date(self, entry) -> Optional[datetime]:
        """解析RSS条目的发布时间"""
        date_fields = ["published_parsed", "updated_parsed", "created_parsed"]
        
        for field in date_fields:
            time_struct = getattr(entry, field, None)
            if time_struct:
                try:
                    dt = datetime(*time_struct[:6], tzinfo=timezone.utc)
                    return dt
                except Exception:
                    continue
        
        # 尝试解析字符串格式
        for field in ["published", "updated", "created"]:
            date_str = getattr(entry, field, None)
            if date_str:
                try:
                    return date_parser.parse(date_str)
                except Exception:
                    continue
        
        return None
    
    def _generate_event_id(self, title: str, url: str) -> str:
        """生成事件唯一ID（用于去重）"""
        raw = (title + "|" + url).encode("utf-8")
        return hashlib.md5(raw).hexdigest()[:12]
    
    def _deduplicate_events(self, events: List[NewsEvent]) -> List[NewsEvent]:
        """按event_id去重，保留最新的"""
        seen = {}
        for event in events:
            if event.event_id not in seen:
                seen[event.event_id] = event
            else:
                # 保留内容更丰富的
                if len(event.raw_content) > len(seen[event.event_id].raw_content):
                    seen[event.event_id] = event
        return list(seen.values())
    
    def _filter_rwa_related(self, events: List[NewsEvent]) -> List[NewsEvent]:
        """过滤出RWA相关的新闻"""
        filtered = []
        for event in events:
            content_lower = event.raw_content.lower()
            if any(kw in content_lower for kw in self.rwa_keywords):
                filtered.append(event)
        return filtered
    
    def extract_funding_amount(self, text: str) -> Optional[float]:
        """
        从文本中提取融资规模（万美元）
        匹配模式: "$80M", "8000万美元", "$80 million", "80M USD" 等
        """
        text_lower = text.lower()
        amount = None
        
        # 模式1: $XXM / $XX million
        pattern1 = re.findall(r'\$([\d.]+)\s*(?:m|million|mm)', text_lower)
        if pattern1:
            amount = float(pattern1[0])  # 百万美元 = 万美元*100? 不，$80M = 8000万美元? 不对
            # $80M = 80百万美元 = 8000万美元? 不，$80M = 80,000,000美元 = 8000万美元
            # 实际上用户阈值单位是万美元，所以1M = 100万美元 = 100? 不对，用户配置写的是:
            # CRITICAL: 5000  # >5000万美元，即 >50M USD
            # 所以我们要把金额转换为"万美元"单位
            # $80M = 80 * 100 万美元 = 8000万美元? 不对，1M = 1,000,000美元 = 100万美元
            # 所以 $80M = 80 * 100 = 8000万美元 ✓
            amount = float(pattern1[0]) * 100  # 转成万美元单位
        
        # 模式2: XX万美元
        if not amount:
            pattern2 = re.findall(r'([\d.]+)\s*万美元', text)
            if pattern2:
                amount = float(pattern2[0])
        
        # 模式3: XX亿XX万美元
        if not amount:
            pattern3 = re.findall(r'([\d.]+)\s*亿美元', text)
            if pattern3:
                amount = float(pattern3[0]) * 10000  # 1亿美元 = 10000万美元
        
        # 模式4: $XXXK (千美元)
        if not amount:
            pattern4 = re.findall(r'\$([\d.]+)\s*k', text_lower)
            if pattern4:
                amount = float(pattern4[0]) * 0.1  # $1000K = 100万美元
        
        return amount
