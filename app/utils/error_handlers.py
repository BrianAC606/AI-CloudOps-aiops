#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI-CloudOps-aiops
Author: Bamboo
Email: bamboocloudops@gmail.com
License: Apache 2.0
Description: 统一错误处理工具 - 提供标准化的错误处理、日志记录和响应格式化功能
"""


import asyncio
import logging
import traceback
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

from app.constants import (
    ERROR_MESSAGES,
    HTTP_STATUS_BAD_REQUEST,
    HTTP_STATUS_INTERNAL_ERROR,
    HTTP_STATUS_NOT_FOUND,
    HTTP_STATUS_UNAUTHORIZED,
    SUCCESS_MESSAGES,
)


class AICloudOpsError(Exception):
    """
    AI-CloudOps 基础异常类

    Args:
        message: 错误消息
        error_code: 错误代码
        details: 详细错误信息
    """

    def __init__(
        self, message: str, error_code: str = "UNKNOWN", details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = datetime.now()
        super().__init__(self.message)


class ValidationError(AICloudOpsError):
    """
    输入验证错误

    Args:
        message: 错误消息
        field: 出错的字段名
        value: 无效的字段值
    """

    def __init__(self, message: str, field: Optional[str] = None, value: Optional[Any] = None):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["invalid_value"] = str(value)
        super().__init__(message, "VALIDATION_ERROR", details)


class ServiceError(AICloudOpsError):
    """
    服务层错误

    Args:
        message: 错误消息
        service: 服务名称
        operation: 操作名称
    """

    def __init__(self, message: str, service: str, operation: Optional[str] = None):
        details = {"service": service}
        if operation:
            details["operation"] = operation
        super().__init__(message, "SERVICE_ERROR", details)


class ConfigurationError(AICloudOpsError):
    """
    配置错误

    Args:
        message: 错误消息
        config_key: 配置键名
    """

    def __init__(self, message: str, config_key: Optional[str] = None):
        details = {}
        if config_key:
            details["config_key"] = config_key
        super().__init__(message, "CONFIGURATION_ERROR", details)


class ExternalServiceError(AICloudOpsError):
    """
    外部服务错误

    Args:
        message: 错误消息
        service: 外部服务名称
        status_code: HTTP状态码
    """

    def __init__(self, message: str, service: str, status_code: Optional[int] = None):
        details = {"external_service": service}
        if status_code:
            details["status_code"] = status_code
        super().__init__(message, "EXTERNAL_SERVICE_ERROR", details)


class ErrorHandler:
    """
    统一错误处理器

    Args:
        logger: 日志记录器实例
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def log_and_return_error(
        self, error: Exception, context: str, include_traceback: bool = True
    ) -> Tuple[str, Dict[str, Any]]:
        """
        记录错误并返回格式化的错误信息

        Args:
            error: 异常对象
            context: 错误上下文
            include_traceback: 是否包含堆栈信息

        Returns:
            Tuple[str, Dict[str, Any]]: 错误消息和详细信息
        """

        error_id = f"error_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        # 构建错误详情
        error_details = {
            "error_id": error_id,
            "error_type": type(error).__name__,
            "context": context,
            "timestamp": datetime.now().isoformat(),
        }

        # 如果是自定义异常，添加额外信息
        if isinstance(error, AICloudOpsError):
            error_details.update({"error_code": error.error_code, "details": error.details})

        # 记录日志
        log_message = f"[{error_id}] {context}: {str(error)}"

        if include_traceback:
            self.logger.error(log_message, exc_info=True)
            error_details["traceback"] = traceback.format_exc()
        else:
            self.logger.error(log_message)

        return str(error), error_details

    def handle_validation_error(
        self, error: Exception, context: str = ""
    ) -> Tuple[Dict[str, Any], int]:
        """
        处理验证错误

        Args:
            error: 异常对象
            context: 错误上下文

        Returns:
            Tuple[Dict[str, Any], int]: 错误响应和HTTP状态码
        """
        message, details = self.log_and_return_error(error, f"Validation error: {context}", False)

        return {
            "code": HTTP_STATUS_BAD_REQUEST,
            "message": ERROR_MESSAGES.get("invalid_input", message),
            "data": {},
            "error_details": details,
        }, HTTP_STATUS_BAD_REQUEST

    def handle_service_error(
        self, error: Exception, context: str = ""
    ) -> Tuple[Dict[str, Any], int]:
        """
        处理服务错误

        Args:
            error: 异常对象
            context: 错误上下文

        Returns:
            Tuple[Dict[str, Any], int]: 错误响应和HTTP状态码
        """
        message, details = self.log_and_return_error(error, f"Service error: {context}")

        return {
            "code": HTTP_STATUS_INTERNAL_ERROR,
            "message": ERROR_MESSAGES.get("internal_error", message),
            "data": {},
            "error_details": details,
        }, HTTP_STATUS_INTERNAL_ERROR

    def handle_not_found_error(
        self, resource: str, identifier: str = ""
    ) -> Tuple[Dict[str, Any], int]:
        """
        处理资源未找到错误

        Args:
            resource: 资源类型
            identifier: 资源标识符

        Returns:
            Tuple[Dict[str, Any], int]: 错误响应和HTTP状态码
        """
        message = f"{resource} not found"
        if identifier:
            message += f": {identifier}"

        self.logger.warning(message)

        return {
            "code": HTTP_STATUS_NOT_FOUND,
            "message": ERROR_MESSAGES.get("not_found", message),
            "data": {},
            "error_details": {
                "resource": resource,
                "identifier": identifier,
                "timestamp": datetime.now().isoformat(),
            },
        }, HTTP_STATUS_NOT_FOUND


def error_handler(
    logger: Optional[logging.Logger] = None,
    return_exceptions: bool = False,
    default_return_value: Any = None,
) -> Callable:
    """
    错误处理装饰器

    Args:
        logger: 日志记录器实例
        return_exceptions: 是否返回异常而不是抛出
        default_return_value: 出现异常时的默认返回值

    Returns:
        Callable: 装饰后的函数
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            handler = ErrorHandler(logger)
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if return_exceptions:
                    return default_return_value
                error_msg, details = handler.log_and_return_error(e, f"Function {func.__name__}")
                raise ServiceError(error_msg, func.__name__)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            handler = ErrorHandler(logger)
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if return_exceptions:
                    return default_return_value
                error_msg, details = handler.log_and_return_error(e, f"Function {func.__name__}")
                raise ServiceError(error_msg, func.__name__)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def retry_on_exception(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    logger: Optional[logging.Logger] = None,
) -> Callable:
    """
    重试装饰器

    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff_factor: 延迟时间的增长因子
        exceptions: 需要捕获的异常类型
        logger: 日志记录器实例

    Returns:
        Callable: 装饰后的函数
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            _logger = logger or logging.getLogger(func.__module__)
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        _logger.error(
                            f"Function {func.__name__} failed after {max_retries} retries: {str(e)}"
                        )
                        raise

                    retry_delay = delay * (backoff_factor**attempt)
                    _logger.warning(
                        f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {retry_delay}s: {str(e)}"
                    )
                    await asyncio.sleep(retry_delay)

            raise last_exception

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            import time

            _logger = logger or logging.getLogger(func.__module__)
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        _logger.error(
                            f"Function {func.__name__} failed after {max_retries} retries: {str(e)}"
                        )
                        raise

                    retry_delay = delay * (backoff_factor**attempt)
                    _logger.warning(
                        f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {retry_delay}s: {str(e)}"
                    )
                    time.sleep(retry_delay)

            raise last_exception

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> None:
    """
    验证必填字段是否存在

    Args:
        data: 要验证的数据字典
        required_fields: 必填字段列表

    Raises:
        ValidationError: 如果缺少必填字段
    """
    missing_fields = []

    for field in required_fields:
        if field not in data or data[field] is None:
            missing_fields.append(field)

    if missing_fields:
        raise ValidationError(
            f"缺少必填字段: {', '.join(missing_fields)}", field=", ".join(missing_fields)
        )


def validate_field_type(
    data: Dict[str, Any], field: str, expected_type: Type, required: bool = True
) -> None:
    """
    验证字段类型是否正确

    Args:
        data: 要验证的数据字典
        field: 字段名称
        expected_type: 期望的字段类型
        required: 字段是否必需

    Raises:
        ValidationError: 如果字段类型不正确或必填字段缺失
    """
    if field not in data or data[field] is None:
        if required:
            raise ValidationError(f"缺少必填字段: {field}", field=field)
        return

    if not isinstance(data[field], expected_type):
        raise ValidationError(
            f"字段 {field} 类型应为 {expected_type.__name__}，当前为 {type(data[field]).__name__}",
            field=field,
            value=data[field],
        )


def validate_field_range(
    data: Dict[str, Any],
    field: str,
    min_value: Optional[Union[int, float]] = None,
    max_value: Optional[Union[int, float]] = None,
) -> None:
    """
    验证数值字段是否在指定范围内

    Args:
        data: 要验证的数据字典
        field: 字段名称
        min_value: 最小值
        max_value: 最大值

    Raises:
        ValidationError: 如果字段值不在指定范围内
    """
    if field not in data or data[field] is None:
        return

    value = data[field]
    if not isinstance(value, (int, float)):
        raise ValidationError(
            f"字段 {field} 应为数值类型，当前为 {type(value).__name__}", field=field, value=value
        )

    if min_value is not None and value < min_value:
        raise ValidationError(
            f"字段 {field} 值应大于等于 {min_value}，当前为 {value}", field=field, value=value
        )

    if max_value is not None and value > max_value:
        raise ValidationError(
            f"字段 {field} 值应小于等于 {max_value}，当前为 {value}", field=field, value=value
        )


def safe_cast(value: Any, target_type: Type, default: Any = None) -> Any:
    """
    安全地转换值类型，转换失败时返回默认值

    Args:
        value: 要转换的值
        target_type: 目标类型
        default: 转换失败时的默认值

    Returns:
        Any: 转换后的值或默认值
    """
    try:
        return target_type(value)
    except (ValueError, TypeError):
        return default


class ContextualLogger:
    """
    上下文感知日志记录器，自动添加上下文信息

    Args:
        logger: 基础日志记录器
        context: 上下文信息字典
    """

    def __init__(self, logger: logging.Logger, context: Dict[str, Any]):
        self.logger = logger
        self.context = context

    def _format_message(self, message: str) -> str:
        """
        格式化日志消息，添加上下文信息

        Args:
            message: 原始消息

        Returns:
            str: 添加上下文后的消息
        """
        context_str = " ".join(f"{k}={v}" for k, v in self.context.items())
        return f"{message} [{context_str}]"

    def debug(self, message: str, **kwargs: Any) -> None:
        """输出调试级别日志"""
        self.logger.debug(self._format_message(message), **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """输出信息级别日志"""
        self.logger.info(self._format_message(message), **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """输出警告级别日志"""
        self.logger.warning(self._format_message(message), **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """输出错误级别日志"""
        self.logger.error(self._format_message(message), **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """输出严重错误级别日志"""
        self.logger.critical(self._format_message(message), **kwargs)


def create_contextual_logger(logger: logging.Logger, **context: Any) -> ContextualLogger:
    """
    创建上下文感知日志记录器

    Args:
        logger: 基础日志记录器
        **context: 上下文信息

    Returns:
        ContextualLogger: 上下文感知日志记录器实例
    """
    return ContextualLogger(logger, context)
