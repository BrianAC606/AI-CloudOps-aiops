#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
服务工厂模块。

提供对服务实例的单例管理、懒加载初始化、健康检查与统一清理能力。
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Type, TypeVar, cast

from app.services.base import BaseService

logger = logging.getLogger("aiops.services.factory")

TService = TypeVar("TService", bound=BaseService)


class ServiceFactory:
    """服务工厂，提供服务的单例、懒加载与生命周期管理。

    - 通过名称管理服务实例，默认单例
    - 首次获取时创建实例并以协程方式触发 `initialize`
    - 提供健康检查聚合与统一清理
    """

    _instances: Dict[str, BaseService] = {}
    _locks: Dict[str, asyncio.Lock] = {}

    @classmethod
    def _get_lock(cls, name: str) -> asyncio.Lock:
        if name not in cls._locks:
            cls._locks[name] = asyncio.Lock()
        return cls._locks[name]

    @classmethod
    async def get_service(cls, name: str, service_cls: Type[TService]) -> TService:
        """获取指定服务的单例实例。

        首次调用会创建实例并以后台任务方式触发 `initialize()`。

        Args:
            name: 服务名称（作为单例键）。
            service_cls: 服务类，需继承 `BaseService`。

        Returns:
            已存在或新创建的服务实例。
        """
        if name in cls._instances:
            return cast(TService, cls._instances[name])

        async with cls._get_lock(name):
            if name in cls._instances:
                return cast(TService, cls._instances[name])

            instance: TService = service_cls()
            cls._instances[name] = instance

            # 懒初始化：不强制等待初始化完成
            try:
                asyncio.create_task(instance.initialize())
            except Exception as e:
                logger.warning("服务 %s 初始化任务创建失败: %s", name, e)

            return instance

    @classmethod
    def peek(cls, name: str) -> Optional[BaseService]:
        """获取已存在的服务实例，不创建新实例。

        Args:
            name: 服务名称。

        Returns:
            若存在返回实例，否则返回 None。
        """
        return cls._instances.get(name)

    @classmethod
    async def ensure_initialized(cls, name: str) -> bool:
        """确保已存在的服务完成初始化。

        若服务未注册则返回 False；若初始化成功返回 True。

        Args:
            name: 服务名称。

        Returns:
            是否确认初始化完成。
        """
        service = cls._instances.get(name)
        if not service:
            return False
        try:
            await service.initialize()
            return True
        except Exception as e:
            logger.error("确保服务 %s 初始化失败: %s", name, e)
            return False

    @classmethod
    async def health(cls) -> Dict[str, Any]:
        """获取所有管理服务的健康状态聚合信息。

        Returns:
            包含每个服务的初始化与健康状态，以及总体状态的字典。
        """
        status: Dict[str, Any] = {"services": {}, "overall": "unknown"}
        healthy_count = 0
        total = 0

        for name, service in list(cls._instances.items()):
            try:
                total += 1
                is_healthy = await service.health_check()
                status["services"][name] = {
                    "initialized": service.is_initialized(),
                    "healthy": bool(is_healthy),
                }
                if is_healthy:
                    healthy_count += 1
            except Exception as e:
                status["services"][name] = {
                    "initialized": service.is_initialized(),
                    "healthy": False,
                    "error": str(e),
                }

        if total == 0:
            status["overall"] = "empty"
        elif healthy_count == total:
            status["overall"] = "healthy"
        elif healthy_count > 0:
            status["overall"] = "degraded"
        else:
            status["overall"] = "unhealthy"

        return status

    @classmethod
    async def cleanup_all(cls) -> Dict[str, Any]:
        """清理并关闭所有管理的服务。

        Returns:
            清理结果与总体成功标记。
        """
        results: Dict[str, Any] = {"results": {}, "success": True}

        for name, service in list(cls._instances.items()):
            try:
                await service.cleanup()
                results["results"][name] = {"success": True}
            except Exception as e:
                results["results"][name] = {"success": False, "error": str(e)}
                results["success"] = False

        # 清理内部状态
        cls._instances.clear()
        cls._locks.clear()

        return results
