"""
数据分析路由
"""
from fastapi import APIRouter, HTTPException, Request, Query
from typing import Optional

from utils.memory import MemoryManager

router = APIRouter()
memory = MemoryManager()


@router.get("/api/analytics/overview")
def get_analytics_overview():
    """获取分析概览"""
    return memory.analyze_personal_data()


@router.get("/api/analytics/traffic-trend")
def get_traffic_trend(content_id: int = None, limit: int = 30):
    """获取流量日趋势"""
    return memory.get_traffic_trend(content_id=content_id, limit=limit)


@router.get("/api/analytics/follower-trend")
def get_follower_trend(content_id: int = None, limit: int = 30):
    """获取粉丝日趋势"""
    return memory.get_follower_trend(content_id=content_id, limit=limit)
