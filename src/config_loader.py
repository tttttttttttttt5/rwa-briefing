"""
RWA 创业信息简报系统
配置加载模块
"""
import os
import yaml
from typing import Dict, Any, List


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    加载并验证配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        解析后的配置字典
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    _validate_config(config)
    return config


def _validate_config(config: Dict[str, Any]) -> None:
    """
    验证配置是否完整
    """
    required_keys = [
        "push",
        "WATCHLIST_PROTOCOLS",
        "FUNDING_THRESHOLD",
        "REGIONS_WATCHLIST",
        "NARRATIVE_TAGS",
        "IMPORTANCE_RULES",
        "data_sources"
    ]
    
    for key in required_keys:
        if key not in config:
            raise ValueError(f"缺少必要配置项: {key}")
    
    # 验证推送频率
    valid_freq = ["daily", "major_only", "weekly"]
    if config["push"]["frequency"] not in valid_freq:
        raise ValueError(f"无效的推送频率: {config['push']['frequency']}, 可选: {valid_freq}")


def get_watchlist_protocols(config: Dict[str, Any]) -> List[str]:
    """获取关注的协议名称列表"""
    return [p["name"].lower() for p in config["WATCHLIST_PROTOCOLS"]]


def get_region_codes(config: Dict[str, Any]) -> List[str]:
    """获取关注的监管区域代码列表"""
    return [r["code"].lower() for r in config["REGIONS_WATCHLIST"]]


def get_all_keywords(config: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    获取所有叙事标签的关键词映射
    
    Returns:
        {tag_name: [keyword1, keyword2, ...]}
    """
    result = {}
    for tag_config in config["NARRATIVE_TAGS"]:
        result[tag_config["tag"]] = [
            kw.lower() for kw in tag_config["keywords"]
        ]
    return result
