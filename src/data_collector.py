"""
RWA 创业信息简报系统
数据收集模块 - 从真实来源收集RWA相关新闻和动态
"""
import re
import time
import hashlib
import logging
import json
import urllib.parse
from difflib import SequenceMatcher
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
    tags: List[str] = field(default_factory=list)
    importance: str = "low"
    importance_score: float = 0.0
    matched_protocols: List[str] = field(default_factory=list)
    matched_regions: List[str] = field(default_factory=list)
    funding_amount: Optional[float] = None
    is_headline: bool = False
    # 资深投研分析
    analysis: str = ""


class DataCollector:
    """多源数据收集器 - 真实数据"""

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
            "treasur", "债券", "yield", "收益", "apy", "institutional", "机构",
            "blackrock", "buidl", "ondo", "centrifuge", "maple", "morpho",
            "hyperliquid", "stork", "goldfinch", "frax", "clearpool",
            "sec", "sfc", "mas", "finma", "mica", "securitize"
        ]

    def collect_all(self, lookback_hours: int = 48) -> List[NewsEvent]:
        """从所有数据源收集真实数据"""
        all_events: List[NewsEvent] = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

        # 1. RSS源（真实新闻）
        rss_events = self._collect_rss_feeds(cutoff_time)
        all_events.extend(rss_events)
        logger.info(f"RSS源收集到 {len(rss_events)} 条新闻")

        # 2. 网页抓取源（无RSS的专业站点）
        scrape_events = self._collect_web_scraped(cutoff_time)
        all_events.extend(scrape_events)
        logger.info(f"网页抓取源收集到 {len(scrape_events)} 条新闻")

        # 3. WebSearch实时搜索（补充RWA专题新闻）
        web_events = self._collect_websearch_rwa()
        all_events.extend(web_events)
        logger.info(f"WebSearch收集到 {len(web_events)} 条新闻")

        # 智能去重（模糊标题相似度 + URL域名）
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
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except Exception as e:
            logger.warning(f"获取RSS失败 {source_name}: {e}")
            return events

        for entry in feed.entries:
            try:
                pub_date = self._parse_entry_date(entry)
                if pub_date and pub_date < cutoff_time:
                    continue
                if not pub_date:
                    pub_date = datetime.now(timezone.utc)

                title = getattr(entry, "title", "").strip()
                summary = getattr(entry, "summary", getattr(entry, "description", "")).strip()
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

    def _collect_web_scraped(self, cutoff_time: datetime) -> List[NewsEvent]:
        """从无RSS的网页源抓取文章列表"""
        events = []
        sources = self.config.get("data_sources", {}).get("web_scrape_sources", [])

        for src in sources:
            try:
                resp = self.session.get(src["url"], timeout=20)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.content, "lxml")

                # 用配置的选择器找文章块
                articles = soup.select(src.get("article_selector", "article"))
                if not articles:
                    # 退而求其次：找所有带链接的标题
                    articles = soup.find_all(["h2", "h3"], limit=15)

                for art in articles[:15]:
                    try:
                        # 提取标题文本
                        title_el = art.select_one(src.get("title_selector", "h2, h3, a"))
                        if not title_el:
                            title_el = art

                        title = title_el.get_text(strip=True)
                        if not title or len(title) < 10:
                            continue

                        # 提取链接
                        link_el = art.find("a")
                        link = ""
                        if link_el and link_el.get("href"):
                            link = urllib.parse.urljoin(src["url"], link_el["href"])

                        # 提取摘要
                        summary = art.get_text(" ", strip=True)[:500]

                        # 尝试提取日期
                        pub_date = datetime.now(timezone.utc)
                        date_el = art.select_one(src.get("date_selector", "time, .date"))
                        if date_el and date_el.get("datetime"):
                            try:
                                pub_date = date_parser.parse(date_el["datetime"])
                            except Exception:
                                pass

                        if pub_date < cutoff_time:
                            continue

                        event_id = self._generate_event_id(title, link or src["url"])
                        raw_content = title + " " + summary

                        events.append(NewsEvent(
                            event_id=event_id,
                            title=title,
                            summary=summary,
                            source=src["name"],
                            url=link or src["url"],
                            published_at=pub_date,
                            raw_content=raw_content
                        ))
                    except Exception:
                        continue

                logger.info(f"网页抓取 [{src['name']}]: 获取 {len(articles)} 篇文章")
            except Exception as e:
                logger.warning(f"网页抓取失败 [{src.get('name')}]: {e}")
                continue

        return events

    def _collect_websearch_rwa(self) -> List[NewsEvent]:
        """
        通过WebSearch API获取实时RWA新闻
        补充RSS源无法覆盖的深度报道
        """
        events = []

        # 预置的WebSearch结果（由main.py在运行前注入）
        # 或通过环境变量传入搜索结果
        websearch_data = os.environ.get("WEBSEARCH_RESULTS", "")
        if websearch_data:
            try:
                results = json.loads(websearch_data)
                events = self._parse_websearch_results(results)
            except Exception as e:
                logger.warning(f"解析WebSearch结果失败: {e}")

        return events

    def _parse_websearch_results(self, results: List[Dict]) -> List[NewsEvent]:
        """解析WebSearch API返回的结果"""
        events = []
        now = datetime.now(timezone.utc)

        for result in results:
            try:
                title = result.get("title", "").strip()
                url = result.get("url", result.get("link", ""))
                snippet = result.get("snippet", result.get("summary", "")).strip()

                # 尝试从内容中提取发布时间
                pub_date = self._extract_date_from_text(snippet) or now

                if not title or not url:
                    continue

                event_id = self._generate_event_id(title, url)
                raw_content = title + " " + snippet

                event = NewsEvent(
                    event_id=event_id,
                    title=title,
                    summary=snippet[:500],
                    source=result.get("source", "WebSearch"),
                    url=url,
                    published_at=pub_date,
                    raw_content=raw_content
                )
                events.append(event)
            except Exception as e:
                logger.debug(f"解析WebSearch条目失败: {e}")
                continue

        return events

    def _extract_date_from_text(self, text: str) -> Optional[datetime]:
        """从文本中提取日期"""
        date_patterns = [
            r'(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})',
            r'(\d{1,2})/(\d{1,2})/(\d{4})',
            r'(\d{4}-\d{2}-\d{2})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return date_parser.parse(match.group(0))
                except Exception:
                    continue
        return None

    def _parse_entry_date(self, entry) -> Optional[datetime]:
        """解析RSS条目的发布时间"""
        date_fields = ["published_parsed", "updated_parsed", "created_parsed"]

        for field_name in date_fields:
            time_struct = getattr(entry, field_name, None)
            if time_struct:
                try:
                    dt = datetime(*time_struct[:6], tzinfo=timezone.utc)
                    return dt
                except Exception:
                    continue

        for field_name in ["published", "updated", "created"]:
            date_str = getattr(entry, field_name, None)
            if date_str:
                try:
                    return date_parser.parse(date_str)
                except Exception:
                    continue

        return None

    def _generate_event_id(self, title: str, url: str) -> str:
        """生成事件唯一ID"""
        raw = (title + "|" + url).encode("utf-8")
        return hashlib.md5(raw).hexdigest()[:12]

    def _deduplicate_events(self, events: List[NewsEvent]) -> List[NewsEvent]:
        """
        智能去重：event_id + 精确标题 + 模糊标题相似度 + URL路径
        """
        seen_ids = {}
        seen_titles = []  # 存 (title_lower, url_path, event) 用于模糊比对

        for event in events:
            title_lower = event.title.lower().strip()

            # 1. event_id 精确去重
            if event.event_id in seen_ids:
                if len(event.raw_content) > len(seen_ids[event.event_id].raw_content):
                    seen_ids[event.event_id] = event
                continue

            # 2. 精确标题匹配
            exact_match = False
            for t, _, _ in seen_titles:
                if t == title_lower:
                    exact_match = True
                    break
            if exact_match:
                continue

            # 3. 模糊标题相似度去重（>75%视为重复）
            fuzzy_match = False
            for t, _, existing_event in seen_titles:
                ratio = SequenceMatcher(None, t, title_lower).ratio()
                if ratio > 0.75:
                    fuzzy_match = True
                    # 保留内容更丰富的那条
                    if len(event.raw_content) > len(existing_event.raw_content):
                        # 替换
                        for i, (st, su, se) in enumerate(seen_titles):
                            if st == t:
                                seen_titles[i] = (title_lower, se.url, event)
                                seen_ids[se.event_id] = event
                    break
            if fuzzy_match:
                continue

            # 4. URL路径去重（同一篇文章不同来源转载）
            url_path = urllib.parse.urlparse(event.url).path.rstrip("/")
            if url_path and len(url_path) > 20:
                url_dup = False
                for _, u, _ in seen_titles:
                    existing_path = urllib.parse.urlparse(u).path.rstrip("/")
                    if existing_path == url_path:
                        url_dup = True
                        break
                if url_dup:
                    continue

            seen_ids[event.event_id] = event
            seen_titles.append((title_lower, event.url, event))

        return list(seen_ids.values())

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
        从文本中提取真实的融资规模（万美元）。
        仅在文本中明确出现融资类语境关键词时才返回金额，
        避免将TVL、市值、交易量、AUM等规模数据误判为融资。
        """
        text_lower = text.lower()

        # ========== 前置条件：必须出现融资类语境词 ==========
        funding_context_keywords = [
            "funding", "seed", "series a", "series b", "series c",
            "raise", "raised", "investment round", "round", "invested",
            "融资", "领投", "跟投", "参投", "种子轮", "天使轮", "Pre-A",
            "Pre-A轮", "A轮", "B轮", "C轮", "D轮", "战略投资", "创投"
        ]

        # 如果连融资语境词都没有，直接跳过（避免把TVL/AUM/市值当融资）
        if not any(kw.lower() in text_lower for kw in funding_context_keywords):
            # 但允许标题或摘要里出现 "$XXM seed" / "$XXM funding" / "完成$XX融资" 的强匹配
            direct_pattern = re.search(
                r'(\$[\d.]+\s*(?:m|million|k))\s*(?:seed|funding|round)',
                text_lower
            )
            zh_pattern = re.search(r'完成\s*([\d.]+\s*(?:万美元|亿美元))\s*融资', text)
            if not direct_pattern and not zh_pattern:
                return None

        amount = None

        # 模式1: $XXM / $XX million
        pattern1 = re.findall(r'\$([\d.]+)\s*(?:m|million|mm)', text_lower)
        if pattern1:
            amount = float(pattern1[0]) * 100

        # 模式2: XX万美元
        if not amount:
            pattern2 = re.findall(r'([\d.]+)\s*万美元', text)
            if pattern2:
                amount = float(pattern2[0])

        # 模式3: XX亿美元
        if not amount:
            pattern3 = re.findall(r'([\d.]+)\s*亿美元', text)
            if pattern3:
                amount = float(pattern3[0]) * 10000

        # 模式4: $XXXK
        if not amount:
            pattern4 = re.findall(r'\$([\d.]+)\s*k', text_lower)
            if pattern4:
                amount = float(pattern4[0]) * 0.1

        # 模式5: $XX billion（融资一般不会到billion，但保留兜底）
        if not amount:
            pattern5 = re.findall(r'\$([\d.]+)\s*billion', text_lower)
            if pattern5:
                amount = float(pattern5[0]) * 10000

        # 合理性上限：单笔融资通常不超过 $50亿，超过视为误判（如TVL）
        if amount is not None and amount > 500000:
            return None

        return amount


# 模块级导入
import os
