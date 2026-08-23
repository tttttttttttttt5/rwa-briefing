"""
RWA 创业信息简报系统
AI事件分析模块 - 叙事标签匹配 + 重要程度判断
"""
import re
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter, defaultdict

from .data_collector import NewsEvent, DataCollector


class EventClassifier:
    """
    事件分类器：
    1. 匹配叙事标签
    2. 检测融资规模
    3. 匹配关注的协议/机构/地区
    4. 根据权重计算重要程度得分
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.data_collector = DataCollector(config)
        
        # 从配置中加载各维度数据
        self.watchlist_protocols = [
            p["name"].lower() for p in config["WATCHLIST_PROTOCOLS"]
        ]
        self.protocol_details = {
            p["name"].lower(): p for p in config["WATCHLIST_PROTOCOLS"]
        }
        
        self.regions = config["REGIONS_WATCHLIST"]
        self.region_keywords = self._build_region_keywords()
        
        self.narrative_tags = config["NARRATIVE_TAGS"]
        self.tag_keywords = self._build_tag_keywords()
        
        self.funding_threshold = config["FUNDING_THRESHOLD"]
        self.importance_rules = config["IMPORTANCE_RULES"]
        self.big_institutions = [
            inst.lower() for inst in self.importance_rules["BIG_INSTITUTIONS"]
        ]
        
        # 趋势数据存储路径
        self.trend_data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "tag_trends.json"
        )
    
    def _build_region_keywords(self) -> Dict[str, List[str]]:
        """构建监管区域关键词映射"""
        keyword_map = {
            "HK": ["香港", "hong kong", "hkma", "sfc", "证监会"],
            "SG": ["新加坡", "singapore", "mas", "monetary authority"],
            "CH": ["瑞士", "switzerland", "swiss", "finma"],
            "US": ["美国", "us", "sec", "美国证监会", "美联储", "fed", "treasury"],
            "EU": ["欧盟", "european union", "eu", "mica", "esma", "ecb"],
            "JP": ["日本", "japan", "fsa", "金融厅"],
            "KR": ["韩国", "korea", "fsc", "金融委员会"],
            "AE": ["迪拜", "dubai", "uae", "abu dhabi", "dfsa", "adgm"]
        }
        return keyword_map
    
    def _build_tag_keywords(self) -> Dict[str, List[str]]:
        """构建叙事标签关键词映射"""
        result = {}
        for tag_config in self.narrative_tags:
            result[tag_config["tag"]] = [
                kw.lower() for kw in tag_config["keywords"]
            ]
        return result
    
    # ============== 主流程 ==============
    
    def process_events(self, events: List[NewsEvent]) -> List[NewsEvent]:
        """
        处理所有事件：打标签、匹配、评分、排序
        
        Args:
            events: 原始新闻事件列表
            
        Returns:
            处理后的事件列表（按重要程度降序排列）
        """
        for event in events:
            self._process_single_event(event)
        
        # 标记头条（高优先级的前几条）
        self._mark_headlines(events)
        
        # 按重要程度排序
        events.sort(
            key=lambda e: (-self._importance_rank(e.importance), -e.importance_score, -e.published_at.timestamp())
        )
        
        return events
    
    def _process_single_event(self, event: NewsEvent) -> None:
        """处理单个事件的完整流程"""
        content = event.raw_content.lower()
        title = event.title.lower()
        
        # 1. 提取融资规模
        event.funding_amount = self.data_collector.extract_funding_amount(event.raw_content)
        
        # 2. 匹配关注的协议
        event.matched_protocols = self._match_protocols(content)
        
        # 3. 匹配监管区域
        event.matched_regions = self._match_regions(content)
        
        # 4. 匹配叙事标签
        event.tags = self._match_narrative_tags(content, title)
        
        # 5. 计算重要程度得分
        score, importance = self._calculate_importance(event)
        event.importance_score = score
        event.importance = importance
    
    # ============== 各维度匹配 ==============
    
    def _match_protocols(self, content: str) -> List[str]:
        """匹配关注的协议"""
        matched = []
        for protocol in self.watchlist_protocols:
            # 简单的子串匹配（实际可增强为模糊匹配）
            if protocol in content:
                matched.append(protocol)
        return matched
    
    def _match_regions(self, content: str) -> List[str]:
        """匹配监管区域"""
        matched = []
        for region in self.regions:
            code = region["code"]
            keywords = self.region_keywords.get(code, [])
            region_name = region["name"].lower()
            # 检查区域名 + 自定义关键词
            region_hit = region_name in content
            keyword_hit = any(kw.lower() in content for kw in keywords)
            if region_hit or keyword_hit:
                matched.append(code)
        return matched
    
    def _match_narrative_tags(self, content: str, title: str) -> List[str]:
        """
        匹配叙事标签
        标题中出现的关键词权重更高
        """
        tag_scores: Dict[str, float] = defaultdict(float)
        
        for tag, keywords in self.tag_keywords.items():
            for kw in keywords:
                if kw in title:
                    tag_scores[tag] += 3.0  # 标题命中权重高
                if kw in content:
                    tag_scores[tag] += 1.0
        
        # 得分>0的标签都保留，按得分排序
        matched_tags = [
            tag for tag, score in sorted(tag_scores.items(), key=lambda x: -x[1])
            if score > 0
        ]
        return matched_tags
    
    # ============== 重要程度评分 ==============
    
    def _calculate_importance(self, event: NewsEvent) -> Tuple[float, str]:
        """
        计算单个事件的重要程度得分
        
        评分维度 (配置化权重):
        - 命中关注协议 (watchlist_protocol)
        - 融资规模 (funding_threshold)
        - 监管区域新政策 (region_policy)
        - 大机构动向 (big_institution)
        - 当前热门叙事 (narrative_trend)
        """
        weights = self.importance_rules["weights"]
        thresholds = self.importance_rules["thresholds"]
        content = event.raw_content.lower()
        
        total_score = 0.0
        
        # 1. 命中关注协议
        if event.matched_protocols:
            # 检查是否有priority_boost
            boost = any(
                self.protocol_details.get(p, {}).get("priority_boost", False)
                for p in event.matched_protocols
            )
            protocol_score = weights["watchlist_protocol"]
            if boost:
                protocol_score *= 1.2  # 高优先级协议加分
            total_score += min(protocol_score, weights["watchlist_protocol"] * 1.2)
        
        # 2. 融资规模评分
        if event.funding_amount is not None:
            funding_score = self._score_funding(event.funding_amount)
            total_score += funding_score
        
        # 3. 监管区域政策 (同时命中"合规"标签 + 关注区域)
        has_compliance_tag = "合规" in event.tags or "stablecoin" in " ".join(event.tags).lower()
        if event.matched_regions and (has_compliance_tag or self._looks_like_policy(event)):
            # 根据区域优先级打分
            region_max_priority = 0.0
            for code in event.matched_regions:
                region_config = next(
                    (r for r in self.regions if r["code"] == code), None
                )
                if region_config:
                    prio_map = {"high": 1.0, "medium": 0.7, "low": 0.4}
                    region_max_priority = max(
                        region_max_priority,
                        prio_map.get(region_config.get("priority", "medium"), 0.7)
                    )
            total_score += weights["region_policy"] * region_max_priority
        
        # 4. 大机构动向
        if any(inst in content for inst in self.big_institutions):
            total_score += weights["big_institution"]
        
        # 5. 当前热门叙事 (基于历史趋势)
        trend_score = self._score_narrative_trend(event.tags)
        total_score += trend_score * weights["narrative_trend"] / 100
        
        # 映射到等级
        if total_score >= thresholds["HIGH"]:
            importance = "high"
        elif total_score >= thresholds["MEDIUM"]:
            importance = "medium"
        else:
            importance = "low"
        
        return round(total_score, 2), importance
    
    def _score_funding(self, amount_usd_wan: float) -> float:
        """
        根据融资规模计算得分 (0 ~ weights["funding_threshold"])
        
        Args:
            amount_usd_wan: 融资规模（万美元）
        """
        max_score = self.importance_rules["weights"]["funding_threshold"]
        
        critical = self.funding_threshold["CRITICAL"]  # >5000万美元
        major = self.funding_threshold["MAJOR"]         # >1000万美元
        moderate = self.funding_threshold["MODERATE"]   # >300万美元
        
        if amount_usd_wan >= critical:
            return max_score  # 满分
        elif amount_usd_wan >= major:
            # major ~ critical 线性映射 75% ~ 100%
            ratio = (amount_usd_wan - major) / max((critical - major), 1)
            return max_score * (0.75 + 0.25 * min(ratio, 1.0))
        elif amount_usd_wan >= moderate:
            # moderate ~ major 线性映射 40% ~ 75%
            ratio = (amount_usd_wan - moderate) / max((major - moderate), 1)
            return max_score * (0.40 + 0.35 * min(ratio, 1.0))
        else:
            # < moderate 按比例给基础分 (0 ~ 40%)
            ratio = min(amount_usd_wan / max(moderate, 1), 1.0)
            return max_score * 0.40 * ratio
    
    def _looks_like_policy(self, event: NewsEvent) -> bool:
        """判断事件看起来是否像监管政策新闻"""
        policy_keywords = [
            "指引", "规定", "规则", "法案", "政策", "监管", "征求意见",
            "guideline", "regulation", "rule", "bill", "policy", "framework",
            "批准", "牌照", "许可", "approve", "license", "permission",
            "sfc", "mas", "finma", "sec", "mica"
        ]
        content = event.raw_content.lower()
        return any(kw.lower() in content for kw in policy_keywords)
    
    def _score_narrative_trend(self, tags: List[str]) -> float:
        """
        根据历史趋势对叙事标签打分 (0~100)
        使用过去30天的标签频率变化趋势
        """
        if not tags:
            return 0.0
        
        trend_data = self._load_trend_data()
        if not trend_data:
            # 没有历史数据时给一个中等分
            return 50.0 if "代币化" in tags or "合规" in tags else 30.0
        
        recent_counts = trend_data.get("recent", {})  # 最近7天
        older_counts = trend_data.get("older", {})    # 更早的23天
        
        scores = []
        for tag in tags:
            recent = recent_counts.get(tag, 0)
            older_per_day = older_counts.get(tag, 0) / 23.0 if older_counts else 0
            recent_per_day = recent / 7.0 if recent else 0
            
            if older_per_day > 0:
                # 增长率
                growth_rate = (recent_per_day - older_per_day) / older_per_day
                # 映射到分数，100%增长=100分
                score = min(100, max(0, 50 + growth_rate * 50))
            elif recent_per_day > 0:
                score = 70.0  # 新兴热门标签
            else:
                score = 20.0
            scores.append(score)
        
        return sum(scores) / len(scores) if scores else 0.0
    
    def _importance_rank(self, importance: str) -> int:
        """用于排序的重要程度等级"""
        rank_map = {"high": 3, "medium": 2, "low": 1}
        return rank_map.get(importance, 0)
    
    def _mark_headlines(self, events: List[NewsEvent]) -> None:
        """标记头条（高优先级的前N条）"""
        high_events = [e for e in events if e.importance == "high"]
        # 高优先级事件的前3条，或者评分>=90的
        headline_count = min(3, len(high_events))
        high_events.sort(key=lambda e: -e.importance_score)
        for i, e in enumerate(high_events):
            if i < headline_count or e.importance_score >= 90:
                e.is_headline = True
    
    # ============== 趋势数据管理 ==============
    
    def update_trend_data(self, events: List[NewsEvent]) -> None:
        """
        更新标签趋势数据
        存储过去30天的标签出现频率
        """
        lookback_days = self.config.get("trend_analysis", {}).get("lookback_days", 30)
        now = datetime.now(timezone.utc)
        
        # 加载现有数据
        trend_data = self._load_trend_data()
        history = trend_data.get("history", [])  # [{date: "YYYY-MM-DD", tags: {"tag": count}}]
        
        # 统计今天的标签
        today_str = now.strftime("%Y-%m-%d")
        today_tags = Counter()
        for event in events:
            for tag in event.tags:
                today_tags[tag] += 1
        
        # 更新历史
        # 移除同日数据
        history = [h for h in history if h["date"] != today_str]
        history.append({"date": today_str, "tags": dict(today_tags)})
        
        # 只保留lookback_days天
        history.sort(key=lambda x: x["date"], reverse=True)
        history = history[:lookback_days]
        
        # 计算最近7天 vs 更早23天
        recent = Counter()
        older = Counter()
        for i, day in enumerate(history):
            tags = day["tags"]
            if i < 7:
                for tag, cnt in tags.items():
                    recent[tag] += cnt
            else:
                for tag, cnt in tags.items():
                    older[tag] += cnt
        
        new_trend_data = {
            "updated_at": now.isoformat(),
            "lookback_days": lookback_days,
            "history": history,
            "recent": dict(recent),
            "older": dict(older)
        }
        
        self._save_trend_data(new_trend_data)
    
    def get_trend_summary(self) -> Dict[str, Any]:
        """
        获取标签趋势汇总，用于简报展示
        
        Returns:
            {
                "trending_up": [(tag, growth_rate, recent_count)],
                "trending_down": [(tag, growth_rate, recent_count)],
                "top_tags": [(tag, total_count)]
            }
        """
        trend_cfg = self.config.get("trend_analysis", {})
        up_threshold = trend_cfg.get("trend_up_threshold", 50) / 100.0
        down_threshold = trend_cfg.get("trend_down_threshold", -30) / 100.0
        
        trend_data = self._load_trend_data()
        if not trend_data:
            return {"trending_up": [], "trending_down": [], "top_tags": []}
        
        recent = trend_data.get("recent", {})
        older = trend_data.get("older", {})
        
        trending_up = []
        trending_down = []
        all_tags = set(list(recent.keys()) + list(older.keys()))
        
        growth_rates = {}
        for tag in all_tags:
            r = recent.get(tag, 0)
            o = older.get(tag, 0)
            r_per_day = r / 7.0
            o_per_day = o / 23.0 if o > 0 else 0
            
            if o_per_day > 0:
                growth = (r_per_day - o_per_day) / o_per_day
            elif r_per_day > 0:
                growth = 2.0  # 视为新出现的热门
            else:
                growth = 0.0
            
            growth_rates[tag] = (growth, r)
            
            if growth >= up_threshold:
                trending_up.append((tag, growth, r))
            elif growth <= down_threshold:
                trending_down.append((tag, growth, r))
        
        # 排序
        trending_up.sort(key=lambda x: -x[1])
        trending_down.sort(key=lambda x: x[1])
        top_tags = sorted(
            [(tag, r) for tag, (g, r) in growth_rates.items()],
            key=lambda x: -x[1]
        )[:10]
        
        return {
            "trending_up": trending_up[:5],
            "trending_down": trending_down[:3],
            "top_tags": top_tags
        }
    
    def _load_trend_data(self) -> Dict[str, Any]:
        """加载趋势历史数据"""
        try:
            if os.path.exists(self.trend_data_path):
                with open(self.trend_data_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载趋势数据失败: {e}")
        return {}
    
    def _save_trend_data(self, data: Dict[str, Any]) -> None:
        """保存趋势历史数据"""
        os.makedirs(os.path.dirname(self.trend_data_path), exist_ok=True)
        try:
            with open(self.trend_data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存趋势数据失败: {e}")
