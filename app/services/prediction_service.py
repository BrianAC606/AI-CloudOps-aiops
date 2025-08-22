#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI-CloudOps-aiops
Author: Bamboo
Email: bamboocloudops@gmail.com
License: Apache 2.0
Description: AI-CloudOps智能预测服务 - 提供四种资源预测能力
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.common.exceptions import PredictionError, ValidationError
from app.core.prediction import (
    AnomalyDetector,
    CostAnalyzer,
    FeatureExtractor,
    IntelligentPredictor,
    IntelligentReportGenerator,
    ModelManager,
    PredictionAnalyzer,
    ScalingAdvisor,
    UnifiedPredictor,
)
from app.models import (
    AnomalyPrediction,
    CostAnalysis,
    PredictionDataPoint,
    PredictionGranularity,
    PredictionType,
    ResourceConstraints,
    ResourceUtilization,
    ScalingRecommendation,
)
from app.services.base import BaseService, HealthCheckMixin

logger = logging.getLogger("aiops.services.prediction")


class PredictionService(BaseService, HealthCheckMixin):
    """统一预测服务 - 支持QPS、CPU、内存、磁盘多维度预测"""

    def __init__(self) -> None:
        super().__init__("prediction")
        # 基础预测组件
        self._predictor: Optional[UnifiedPredictor] = None
        self._feature_extractor: Optional[FeatureExtractor] = None
        self._anomaly_detector: Optional[AnomalyDetector] = None
        self._scaling_advisor: Optional[ScalingAdvisor] = None
        self._cost_analyzer: Optional[CostAnalyzer] = None
        self._model_manager: Optional[ModelManager] = None

        # AI预测组件
        self._intelligent_predictor: Optional[IntelligentPredictor] = None
        self._prediction_analyzer: Optional[PredictionAnalyzer] = None
        self._report_generator: Optional[IntelligentReportGenerator] = None

        self._initialized = False

    async def _do_initialize(self) -> None:
        """初始化预测服务组件"""
        try:
            from app.core.prediction import ModelManager

            self._model_manager = ModelManager()
            await self._model_manager.initialize()

            # 初始化特征提取器
            self._feature_extractor = FeatureExtractor()

            # 初始化核心预测器
            self._predictor = UnifiedPredictor(
                model_manager=self._model_manager,
                feature_extractor=self._feature_extractor,
            )
            await self._predictor.initialize()

            # 初始化异常检测器
            self._anomaly_detector = AnomalyDetector()

            # 初始化扩缩容顾问
            self._scaling_advisor = ScalingAdvisor()

            # 初始化成本分析器
            self._cost_analyzer = CostAnalyzer()

            # 初始化AI增强组件
            try:
                # 智能预测引擎
                self._intelligent_predictor = IntelligentPredictor(
                    model_manager=self._model_manager,
                    feature_extractor=self._feature_extractor,
                )
                await self._intelligent_predictor.initialize()

                # 预测分析器
                self._prediction_analyzer = PredictionAnalyzer()

                # 报告生成器
                self._report_generator = IntelligentReportGenerator()

                self.logger.info("AI增强组件初始化完成")

            except Exception as ai_e:
                self.logger.warning(
                    f"AI增强组件初始化失败: {str(ai_e)}，将使用基础预测模式"
                )
                self._intelligent_predictor = None
                self._prediction_analyzer = None
                self._report_generator = None

            self._initialized = True
            self.logger.info("预测服务所有组件初始化完成")

        except Exception as e:
            self.logger.error(f"预测服务初始化失败: {str(e)}")
            self._initialized = False
            raise PredictionError(f"服务初始化失败: {str(e)}")

    async def _do_health_check(self) -> bool:
        """健康检查"""
        try:
            if not self._initialized:
                return False

            # 检查模型管理器
            if not self._model_manager or not await self._model_manager.is_healthy():
                return False

            # 检查预测器
            if not self._predictor or not await self._predictor.is_healthy():
                return False

            return True

        except Exception as e:
            self.logger.warning(f"健康检查失败: {str(e)}")
            return False

    def _ensure_initialized(self) -> None:
        """确保服务已初始化"""
        if not self._initialized:
            raise PredictionError("预测服务未初始化，请先调用 initialize()")

    async def predict_qps(
        self,
        current_qps: float,
        metric_query: Optional[str] = None,
        prediction_hours: int = 24,
        granularity: str = "hour",
        resource_constraints: Optional[Dict] = None,
        include_confidence: bool = True,
        include_anomaly_detection: bool = True,
        consider_historical_pattern: bool = True,
        target_utilization: float = 0.7,
        sensitivity: float = 0.8,
    ) -> Dict[str, Any]:
        """QPS负载预测"""
        try:
            self._ensure_initialized()
            # 验证参数
            self._validate_qps_params(current_qps, prediction_hours)

            # 获取历史数据
            historical_data = await self._fetch_historical_data(
                PredictionType.QPS, metric_query, hours=48
            )

            # 执行预测
            predictions = await self._predictor.predict(
                prediction_type=PredictionType.QPS,
                current_value=current_qps,
                historical_data=historical_data,
                prediction_hours=prediction_hours,
                granularity=PredictionGranularity(granularity),
                consider_pattern=consider_historical_pattern,
            )

            # 生成扩缩容建议
            scaling_recommendations = (
                await self._scaling_advisor.generate_recommendations(
                    predictions=predictions,
                    prediction_type=PredictionType.QPS,
                    target_utilization=target_utilization,
                    constraints=(
                        ResourceConstraints(**resource_constraints)
                        if resource_constraints
                        else None
                    ),
                )
            )

            # 异常检测
            anomaly_predictions = []
            if include_anomaly_detection:
                anomaly_predictions = await self._anomaly_detector.detect_anomalies(
                    predictions=predictions, sensitivity=sensitivity
                )

            # 成本分析
            cost_analysis = None
            if resource_constraints:
                cost_analysis = await self._cost_analyzer.analyze_cost(
                    predictions=predictions,
                    scaling_recommendations=scaling_recommendations,
                    constraints=ResourceConstraints(**resource_constraints),
                )

            # 构建响应
            return self._build_prediction_response(
                prediction_type=PredictionType.QPS,
                current_value=current_qps,
                predictions=predictions,
                scaling_recommendations=scaling_recommendations,
                anomaly_predictions=anomaly_predictions,
                cost_analysis=cost_analysis,
                prediction_hours=prediction_hours,
                granularity=granularity,
                include_confidence=include_confidence,
            )

        except ValidationError:
            # 参数验证错误直接透传
            raise
        except Exception as e:
            self.logger.error(f"QPS预测失败: {str(e)}")
            raise PredictionError(f"QPS预测失败: {str(e)}")

    async def predict_cpu_utilization(
        self,
        current_cpu_percent: float,
        metric_query: Optional[str] = None,
        prediction_hours: int = 24,
        granularity: str = "hour",
        resource_constraints: Optional[Dict] = None,
        include_confidence: bool = True,
        include_anomaly_detection: bool = True,
        consider_historical_pattern: bool = True,
        target_utilization: float = 0.7,
        sensitivity: float = 0.8,
    ) -> Dict[str, Any]:
        """CPU使用率预测"""
        try:
            self._ensure_initialized()
            # 验证参数
            self._validate_utilization_params(current_cpu_percent, prediction_hours)

            # 获取历史数据
            historical_data = await self._fetch_historical_data(
                PredictionType.CPU, metric_query, hours=48
            )

            # 执行预测
            predictions = await self._predictor.predict(
                prediction_type=PredictionType.CPU,
                current_value=current_cpu_percent,
                historical_data=historical_data,
                prediction_hours=prediction_hours,
                granularity=PredictionGranularity(granularity),
                consider_pattern=consider_historical_pattern,
            )

            # 生成扩缩容建议
            scaling_recommendations = (
                await self._scaling_advisor.generate_recommendations(
                    predictions=predictions,
                    prediction_type=PredictionType.CPU,
                    target_utilization=target_utilization,
                    constraints=(
                        ResourceConstraints(**resource_constraints)
                        if resource_constraints
                        else None
                    ),
                )
            )

            # 异常检测
            anomaly_predictions = []
            if include_anomaly_detection:
                anomaly_predictions = await self._anomaly_detector.detect_anomalies(
                    predictions=predictions, sensitivity=sensitivity
                )

            # 成本分析
            cost_analysis = None
            if resource_constraints:
                cost_analysis = await self._cost_analyzer.analyze_cost(
                    predictions=predictions,
                    scaling_recommendations=scaling_recommendations,
                    constraints=ResourceConstraints(**resource_constraints),
                )

            # 构建响应
            return self._build_prediction_response(
                prediction_type=PredictionType.CPU,
                current_value=current_cpu_percent,
                predictions=predictions,
                scaling_recommendations=scaling_recommendations,
                anomaly_predictions=anomaly_predictions,
                cost_analysis=cost_analysis,
                prediction_hours=prediction_hours,
                granularity=granularity,
                include_confidence=include_confidence,
            )

        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"CPU预测失败: {str(e)}")
            raise PredictionError(f"CPU预测失败: {str(e)}")

    async def predict_memory_utilization(
        self,
        current_memory_percent: float,
        metric_query: Optional[str] = None,
        prediction_hours: int = 24,
        granularity: str = "hour",
        resource_constraints: Optional[Dict] = None,
        include_confidence: bool = True,
        include_anomaly_detection: bool = True,
        consider_historical_pattern: bool = True,
        target_utilization: float = 0.7,
        sensitivity: float = 0.8,
    ) -> Dict[str, Any]:
        """内存使用率预测"""
        try:
            self._ensure_initialized()
            # 验证参数
            self._validate_utilization_params(current_memory_percent, prediction_hours)

            # 获取历史数据
            historical_data = await self._fetch_historical_data(
                PredictionType.MEMORY, metric_query, hours=48
            )

            # 执行预测
            predictions = await self._predictor.predict(
                prediction_type=PredictionType.MEMORY,
                current_value=current_memory_percent,
                historical_data=historical_data,
                prediction_hours=prediction_hours,
                granularity=PredictionGranularity(granularity),
                consider_pattern=consider_historical_pattern,
            )

            # 生成扩缩容建议
            scaling_recommendations = (
                await self._scaling_advisor.generate_recommendations(
                    predictions=predictions,
                    prediction_type=PredictionType.MEMORY,
                    target_utilization=target_utilization,
                    constraints=(
                        ResourceConstraints(**resource_constraints)
                        if resource_constraints
                        else None
                    ),
                )
            )

            # 异常检测
            anomaly_predictions = []
            if include_anomaly_detection:
                anomaly_predictions = await self._anomaly_detector.detect_anomalies(
                    predictions=predictions, sensitivity=sensitivity
                )

            # 成本分析
            cost_analysis = None
            if resource_constraints:
                cost_analysis = await self._cost_analyzer.analyze_cost(
                    predictions=predictions,
                    scaling_recommendations=scaling_recommendations,
                    constraints=ResourceConstraints(**resource_constraints),
                )

            # 构建响应
            return self._build_prediction_response(
                prediction_type=PredictionType.MEMORY,
                current_value=current_memory_percent,
                predictions=predictions,
                scaling_recommendations=scaling_recommendations,
                anomaly_predictions=anomaly_predictions,
                cost_analysis=cost_analysis,
                prediction_hours=prediction_hours,
                granularity=granularity,
                include_confidence=include_confidence,
            )

        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"内存预测失败: {str(e)}")
            raise PredictionError(f"内存预测失败: {str(e)}")

    async def predict_disk_utilization(
        self,
        current_disk_percent: float,
        metric_query: Optional[str] = None,
        prediction_hours: int = 24,
        granularity: str = "hour",
        resource_constraints: Optional[Dict] = None,
        include_confidence: bool = True,
        include_anomaly_detection: bool = True,
        consider_historical_pattern: bool = True,
        target_utilization: float = 0.7,
        sensitivity: float = 0.8,
    ) -> Dict[str, Any]:
        """磁盘使用率预测"""
        try:
            self._ensure_initialized()
            # 验证参数
            self._validate_utilization_params(current_disk_percent, prediction_hours)

            # 获取历史数据
            historical_data = await self._fetch_historical_data(
                PredictionType.DISK, metric_query, hours=48
            )

            # 执行预测
            predictions = await self._predictor.predict(
                prediction_type=PredictionType.DISK,
                current_value=current_disk_percent,
                historical_data=historical_data,
                prediction_hours=prediction_hours,
                granularity=PredictionGranularity(granularity),
                consider_pattern=consider_historical_pattern,
            )

            # 生成扩缩容建议
            scaling_recommendations = (
                await self._scaling_advisor.generate_recommendations(
                    predictions=predictions,
                    prediction_type=PredictionType.DISK,
                    target_utilization=target_utilization,
                    constraints=(
                        ResourceConstraints(**resource_constraints)
                        if resource_constraints
                        else None
                    ),
                )
            )

            # 异常检测
            anomaly_predictions = []
            if include_anomaly_detection:
                anomaly_predictions = await self._anomaly_detector.detect_anomalies(
                    predictions=predictions, sensitivity=sensitivity
                )

            # 成本分析
            cost_analysis = None
            if resource_constraints:
                cost_analysis = await self._cost_analyzer.analyze_cost(
                    predictions=predictions,
                    scaling_recommendations=scaling_recommendations,
                    constraints=ResourceConstraints(**resource_constraints),
                )

            # 构建响应
            return self._build_prediction_response(
                prediction_type=PredictionType.DISK,
                current_value=current_disk_percent,
                predictions=predictions,
                scaling_recommendations=scaling_recommendations,
                anomaly_predictions=anomaly_predictions,
                cost_analysis=cost_analysis,
                prediction_hours=prediction_hours,
                granularity=granularity,
                include_confidence=include_confidence,
            )

        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"磁盘预测失败: {str(e)}")
            raise PredictionError(f"磁盘预测失败: {str(e)}")

    # AI增强预测方法

    async def predict_with_ai_analysis(
        self,
        prediction_type: str,
        current_value: float,
        metric_query: Optional[str] = None,
        prediction_hours: int = 24,
        granularity: str = "hour",
        resource_constraints: Optional[Dict] = None,
        enable_ai_insights: bool = True,
        report_style: str = "professional",
        target_utilization: float = 0.7,
        sensitivity: float = 0.8,
    ) -> Dict[str, Any]:
        """AI增强预测分析 - 结合大模型的全流程预测"""
        try:
            self._ensure_initialized()

            # 验证参数
            pred_type = PredictionType(prediction_type)
            if pred_type == PredictionType.QPS:
                self._validate_qps_params(current_value, prediction_hours)
            else:
                self._validate_utilization_params(current_value, prediction_hours)

            # 检查AI增强组件是否可用
            if not self._intelligent_predictor:
                self.logger.warning("AI增强组件不可用，降级到基础预测")
                return await self._fallback_to_basic_prediction(
                    pred_type,
                    current_value,
                    metric_query,
                    prediction_hours,
                    granularity,
                    resource_constraints,
                    target_utilization,
                    sensitivity,
                )

            # 获取历史数据
            historical_data = await self._fetch_historical_data(
                pred_type, metric_query, hours=48
            )

            # 执行AI增强预测
            ai_prediction_result = (
                await self._intelligent_predictor.predict_with_ai_analysis(
                    prediction_type=pred_type,
                    current_value=current_value,
                    historical_data=historical_data,
                    prediction_hours=prediction_hours,
                    granularity=PredictionGranularity(granularity),
                    consider_pattern=True,
                    enable_ai_insights=enable_ai_insights,
                    report_style=report_style,
                )
            )

            # 增强结果（添加扩缩容建议和成本分析）
            enhanced_result = await self._enhance_ai_prediction_result(
                ai_prediction_result, resource_constraints, target_utilization
            )

            return enhanced_result

        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"AI增强预测失败: {str(e)}")
            # 降级到基础预测
            return await self._fallback_to_basic_prediction(
                PredictionType(prediction_type),
                current_value,
                metric_query,
                prediction_hours,
                granularity,
                resource_constraints,
                target_utilization,
                sensitivity,
            )

    async def predict_multi_dimension_with_correlation(
        self,
        prediction_configs: List[Dict[str, Any]],
        enable_correlation_analysis: bool = True,
        report_style: str = "professional",
    ) -> Dict[str, Any]:
        """多维度预测与关联分析"""
        try:
            self._ensure_initialized()

            if not self._intelligent_predictor:
                raise PredictionError("AI增强组件不可用，无法执行多维度关联分析")

            # 验证配置
            validated_configs = []
            for config in prediction_configs:
                pred_type = PredictionType(config["prediction_type"])
                current_value = config["current_value"]

                # 验证参数
                if pred_type == PredictionType.QPS:
                    self._validate_qps_params(
                        current_value, config.get("prediction_hours", 24)
                    )
                else:
                    self._validate_utilization_params(
                        current_value, config.get("prediction_hours", 24)
                    )

                # 获取历史数据
                historical_data = await self._fetch_historical_data(
                    pred_type, config.get("metric_query"), hours=48
                )
                config["historical_data"] = historical_data
                validated_configs.append(config)

            # 执行多维度预测
            result = await self._intelligent_predictor.predict_multi_dimension_with_correlation(
                prediction_configs=validated_configs,
                enable_correlation_analysis=enable_correlation_analysis,
                report_style=report_style,
            )

            return result

        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"多维度预测失败: {str(e)}")
            raise PredictionError(f"多维度预测失败: {str(e)}")

    async def generate_prediction_report(
        self,
        analysis_id: str,
        report_type: str = "comprehensive",  # comprehensive, executive, action_plan, risk_assessment
        report_style: str = "professional",
    ) -> Dict[str, Any]:
        """基于分析ID生成定制化报告"""
        try:
            self._ensure_initialized()

            if not self._report_generator:
                raise PredictionError("报告生成器不可用")

            # 从缓存获取分析结果（这里简化处理）
            # 实际应用中应该有完整的分析结果缓存机制

            return {
                "analysis_id": analysis_id,
                "report_type": report_type,
                "report_style": report_style,
                "status": "report_generation_not_implemented_for_cache_lookup",
                "message": "报告生成功能需要完整的分析上下文，请使用预测方法中的集成报告功能",
            }

        except Exception as e:
            self.logger.error(f"生成预测报告失败: {str(e)}")
            raise PredictionError(f"生成预测报告失败: {str(e)}")

    async def _enhance_ai_prediction_result(
        self,
        ai_result: Dict[str, Any],
        resource_constraints: Optional[Dict] = None,
        target_utilization: float = 0.7,
    ) -> Dict[str, Any]:
        """增强AI预测结果 - 添加扩缩容建议和成本分析"""
        try:
            # 获取预测数据
            predictions = ai_result.get("predicted_data", [])
            if not predictions:
                return ai_result

            # 转换为PredictionDataPoint对象
            prediction_points = [
                PredictionDataPoint(**pred) if isinstance(pred, dict) else pred
                for pred in predictions
            ]

            # 生成扩缩容建议
            scaling_recommendations = []
            cost_analysis = None

            if self._scaling_advisor:
                try:
                    scaling_recommendations = (
                        await self._scaling_advisor.generate_recommendations(
                            predictions=prediction_points,
                            prediction_type=PredictionType(
                                ai_result.get("prediction_type")
                            ),
                            target_utilization=target_utilization,
                            constraints=(
                                ResourceConstraints(**resource_constraints)
                                if resource_constraints
                                else None
                            ),
                        )
                    )
                except Exception as e:
                    self.logger.warning(f"生成扩缩容建议失败: {str(e)}")

            # 成本分析
            if self._cost_analyzer and resource_constraints:
                try:
                    cost_analysis = await self._cost_analyzer.analyze_cost(
                        predictions=prediction_points,
                        scaling_recommendations=scaling_recommendations,
                        constraints=ResourceConstraints(**resource_constraints),
                    )
                except Exception as e:
                    self.logger.warning(f"成本分析失败: {str(e)}")

            # 更新结果
            ai_result.update(
                {
                    "scaling_recommendations": [
                        r.model_dump() for r in scaling_recommendations
                    ],
                    "cost_analysis": (
                        cost_analysis.model_dump() if cost_analysis else None
                    ),
                    "enhancement_timestamp": datetime.now(),
                }
            )

            return ai_result

        except Exception as e:
            self.logger.error(f"增强AI预测结果失败: {str(e)}")
            return ai_result

    async def _fallback_to_basic_prediction(
        self,
        prediction_type: PredictionType,
        current_value: float,
        metric_query: Optional[str],
        prediction_hours: int,
        granularity: str,
        resource_constraints: Optional[Dict],
        target_utilization: float,
        sensitivity: float,
    ) -> Dict[str, Any]:
        """降级到基础预测"""

        self.logger.info("执行基础预测作为AI增强预测的降级方案")

        # 根据预测类型调用相应的基础预测方法
        if prediction_type == PredictionType.QPS:
            result = await self.predict_qps(
                current_qps=current_value,
                metric_query=metric_query,
                prediction_hours=prediction_hours,
                granularity=granularity,
                resource_constraints=resource_constraints,
                target_utilization=target_utilization,
                sensitivity=sensitivity,
            )
        elif prediction_type == PredictionType.CPU:
            result = await self.predict_cpu_utilization(
                current_cpu_percent=current_value,
                metric_query=metric_query,
                prediction_hours=prediction_hours,
                granularity=granularity,
                resource_constraints=resource_constraints,
                target_utilization=target_utilization,
                sensitivity=sensitivity,
            )
        elif prediction_type == PredictionType.MEMORY:
            result = await self.predict_memory_utilization(
                current_memory_percent=current_value,
                metric_query=metric_query,
                prediction_hours=prediction_hours,
                granularity=granularity,
                resource_constraints=resource_constraints,
                target_utilization=target_utilization,
                sensitivity=sensitivity,
            )
        else:  # DISK
            result = await self.predict_disk_utilization(
                current_disk_percent=current_value,
                metric_query=metric_query,
                prediction_hours=prediction_hours,
                granularity=granularity,
                resource_constraints=resource_constraints,
                target_utilization=target_utilization,
                sensitivity=sensitivity,
            )

        # 添加降级标记
        result.update(
            {
                "ai_enhanced": False,
                "fallback_mode": True,
                "fallback_reason": "AI增强组件不可用",
                "ai_insights": [
                    "当前使用基础预测模式",
                    "AI增强功能暂时不可用",
                    "预测结果基于传统算法生成",
                ],
            }
        )

        return result

    async def get_service_health_info(self) -> Dict[str, Any]:
        """获取服务健康信息"""
        try:
            models_info = (
                await self._model_manager.get_models_info()
                if self._model_manager
                else []
            )

            return {
                "service_status": (
                    "healthy" if await self.health_check() else "unhealthy"
                ),
                "model_status": (
                    "loaded"
                    if self._model_manager and self._model_manager.models_loaded
                    else "not_loaded"
                ),
                "models_loaded": models_info,
                "supported_prediction_types": [t.value for t in PredictionType],
                "last_prediction_time": getattr(self, "_last_prediction_time", None),
                "total_predictions": getattr(self, "_total_predictions", 0),
                "error_rate": 0.0,
                "average_response_time_ms": getattr(self, "_avg_response_time", None),
                "resource_usage": await self._get_resource_usage(),
                "timestamp": datetime.now(),
            }

        except Exception as e:
            self.logger.error(f"获取健康信息失败: {str(e)}")
            return {
                "service_status": "error",
                "model_status": "unknown",
                "error": str(e),
                "timestamp": datetime.now(),
            }

    async def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        try:
            if not self._model_manager:
                return {"models": [], "status": "not_initialized"}

            return await self._model_manager.get_detailed_info()

        except Exception as e:
            self.logger.error(f"获取模型信息失败: {str(e)}")
            return {"models": [], "status": "error", "error_message": str(e)}

    # 私有辅助方法

    def _validate_qps_params(self, qps: float, hours: int) -> None:
        """验证QPS预测参数"""
        if qps < 0 or qps > 100000:
            raise ValidationError("current_qps", "QPS值应在0-100000之间")
        self._validate_hours(hours)

    def _validate_utilization_params(self, percent: float, hours: int) -> None:
        """验证利用率预测参数"""
        if percent < 0 or percent > 100:
            raise ValidationError("utilization", "利用率应在0-100%之间")
        self._validate_hours(hours)

    def _validate_hours(self, hours: int) -> None:
        """验证预测时长"""
        from app.config.settings import config

        min_hours = config.prediction.min_prediction_hours
        max_hours = config.prediction.max_prediction_hours

        if hours < min_hours or hours > max_hours:
            raise ValidationError(
                "prediction_hours", f"预测时长应在{min_hours}-{max_hours}小时之间"
            )

    async def _fetch_historical_data(
        self, prediction_type: PredictionType, metric_query: Optional[str], hours: int
    ) -> List[Dict[str, Any]]:
        """获取历史数据"""
        import numpy as np
        import pandas as pd

        # 首先尝试从Prometheus获取真实数据
        try:
            prometheus_data = await self._get_prometheus_data(
                prediction_type, metric_query, hours
            )
            if prometheus_data:
                self.logger.info(
                    f"成功从Prometheus获取{len(prometheus_data)}条历史数据"
                )
                return prometheus_data
        except Exception as e:
            self.logger.warning(f"从Prometheus获取数据失败: {str(e)}，回落到模拟数据")

        # 回落到模拟数据
        self.logger.info(f"使用模拟历史数据进行{prediction_type.value}预测")
        return self._generate_mock_historical_data(prediction_type, hours)

    async def _get_prometheus_data(
        self, prediction_type: PredictionType, custom_query: Optional[str], hours: int
    ) -> Optional[List[Dict[str, Any]]]:
        """从Prometheus获取真实数据"""
        from app.services.prometheus import PrometheusService

        prom_service = PrometheusService()

        # 检查Prometheus连接
        if not prom_service.is_healthy():
            self.logger.warning("Prometheus服务不可用")
            return None

        # 确定查询语句
        query = custom_query or self._get_default_query(prediction_type)
        if not query:
            return None

        # 计算时间范围
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        # 查询数据
        df = await prom_service.query_range(
            query=query,
            start_time=start_time,
            end_time=end_time,
            step="1h",  # 使用小时级步长
        )

        if df is None or df.empty:
            self.logger.warning(f"无法从Prometheus获取{prediction_type.value}数据")
            return None

        # 转换为预测服务所需的格式
        return self._convert_prometheus_data(df)

    def _get_default_query(self, prediction_type: PredictionType) -> Optional[str]:
        """获取默认的Prometheus查询语句 - 使用node_exporter标准指标"""
        default_queries = {
            PredictionType.QPS: (
                # 使用网络接收字节数作为QPS的替代指标 (每秒请求数的近似值)
                'rate(node_network_receive_bytes_total{device!="lo"}[5m])'
            ),
            PredictionType.CPU: (
                # CPU使用率：100 - 空闲CPU百分比
                '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
            ),
            PredictionType.MEMORY: (
                # 内存使用率：(总内存 - 可用内存) / 总内存 * 100
                "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100"
            ),
            PredictionType.DISK: (
                # 磁盘使用率：(总空间 - 可用空间) / 总空间 * 100
                '(1 - (node_filesystem_avail_bytes{fstype!="tmpfs"} / node_filesystem_size_bytes{fstype!="tmpfs"})) * 100'
            ),
        }

        return default_queries.get(prediction_type)

    def _convert_prometheus_data(self, df) -> List[Dict[str, Any]]:
        """转换Prometheus数据格式"""
        import numpy as np
        import pandas as pd

        data = []

        # 按时间排序
        df_sorted = df.sort_index()

        for timestamp, row in df_sorted.iterrows():
            # 取平均值作为主要指标
            value = row.get("value", 0)
            if pd.isna(value) or not np.isfinite(value):
                value = 0

            data.append({"timestamp": timestamp.isoformat(), "value": float(value)})

        return data

    def _generate_mock_historical_data(
        self, prediction_type: PredictionType, hours: int
    ) -> List[Dict[str, Any]]:
        """生成模拟历史数据"""
        import numpy as np

        now = datetime.now()
        data = []

        for i in range(hours):
            timestamp = now - timedelta(hours=hours - i)

            # 根据预测类型生成不同的模拟数据
            if prediction_type == PredictionType.QPS:
                base_value = 100
                hour_factor = 0.5 + 0.5 * np.sin(2 * np.pi * timestamp.hour / 24)
                value = base_value * hour_factor + np.random.normal(0, 10)
            elif prediction_type == PredictionType.CPU:
                base_value = 50
                hour_factor = 0.7 + 0.3 * np.sin(2 * np.pi * timestamp.hour / 24)
                value = base_value * hour_factor + np.random.normal(0, 5)
            elif prediction_type == PredictionType.MEMORY:
                base_value = 60
                value = base_value + np.random.normal(0, 3)
            else:  # DISK
                base_value = 40 + i * 0.1  # 缓慢增长
                value = base_value + np.random.normal(0, 1)

            data.append({"timestamp": timestamp.isoformat(), "value": max(0, value)})

        return data

    def _build_prediction_response(
        self,
        prediction_type: PredictionType,
        current_value: float,
        predictions: List[PredictionDataPoint],
        scaling_recommendations: List[ScalingRecommendation],
        anomaly_predictions: List[AnomalyPrediction],
        cost_analysis: Optional[CostAnalysis],
        prediction_hours: int,
        granularity: str,
        include_confidence: bool,
    ) -> Dict[str, Any]:
        """构建预测响应"""
        # 生成资源利用率预测
        resource_utilization = self._generate_resource_utilization(
            predictions, prediction_type
        )

        # 生成模式分析
        pattern_analysis = self._analyze_patterns(predictions)

        # 生成趋势洞察
        trend_insights = self._generate_insights(
            predictions, scaling_recommendations, anomaly_predictions
        )

        # 生成预测摘要
        prediction_summary = {
            "max_value": max(p.predicted_value for p in predictions),
            "min_value": min(p.predicted_value for p in predictions),
            "avg_value": sum(p.predicted_value for p in predictions) / len(predictions),
            "trend": self._detect_trend(predictions),
            "peak_time": self._find_peak_time(predictions),
        }

        return {
            "prediction_type": prediction_type,
            "prediction_hours": prediction_hours,
            "granularity": granularity,
            "current_value": current_value,
            "predicted_data": [p.model_dump() for p in predictions],
            "resource_utilization": [r.model_dump() for r in resource_utilization],
            "scaling_recommendations": [
                s.model_dump() for s in scaling_recommendations
            ],
            "anomaly_predictions": [a.model_dump() for a in anomaly_predictions],
            "cost_analysis": cost_analysis.model_dump() if cost_analysis else None,
            "pattern_analysis": pattern_analysis,
            "trend_insights": trend_insights,
            "model_accuracy": 0.85,  # 这里应该从模型获取实际准确率
            "prediction_summary": prediction_summary,
            "timestamp": datetime.now(),
        }

    def _generate_resource_utilization(
        self, predictions: List[PredictionDataPoint], prediction_type: PredictionType
    ) -> List[ResourceUtilization]:
        """生成资源利用率预测"""
        utilizations = []
        for pred in predictions:
            util = ResourceUtilization(
                timestamp=pred.timestamp, predicted_load=pred.predicted_value
            )

            if prediction_type == PredictionType.CPU:
                util.cpu_utilization = pred.predicted_value
            elif prediction_type == PredictionType.MEMORY:
                util.memory_utilization = pred.predicted_value
            elif prediction_type == PredictionType.DISK:
                util.disk_utilization = pred.predicted_value

            utilizations.append(util)
        return utilizations

    def _analyze_patterns(
        self, predictions: List[PredictionDataPoint]
    ) -> Dict[str, Any]:
        """分析预测模式"""
        values = [p.predicted_value for p in predictions]
        return {
            "has_periodicity": self._check_periodicity(values),
            "volatility": self._calculate_volatility(values),
            "seasonality": self._detect_seasonality(predictions),
        }

    def _generate_insights(
        self,
        predictions: List[PredictionDataPoint],
        scaling_recommendations: List[ScalingRecommendation],
        anomaly_predictions: List[AnomalyPrediction],
    ) -> List[str]:
        """生成趋势洞察"""
        insights = []

        # 趋势洞察
        trend = self._detect_trend(predictions)
        if trend == "increasing":
            insights.append("资源使用呈上升趋势，建议提前规划扩容")
        elif trend == "decreasing":
            insights.append("资源使用呈下降趋势，可考虑优化成本")

        # 扩缩容洞察
        if scaling_recommendations:
            scale_up_count = sum(
                1 for r in scaling_recommendations if r.action.value == "scale_up"
            )
            if scale_up_count > 0:
                insights.append(
                    f"未来{len(predictions)}个时间点中有{scale_up_count}个需要扩容"
                )

        # 异常洞察
        if anomaly_predictions:
            high_risk = [
                a
                for a in anomaly_predictions
                if a.impact_level == "high" or a.impact_level == "critical"
            ]
            if high_risk:
                insights.append(f"检测到{len(high_risk)}个高风险异常点，需要重点关注")

        return insights

    def _detect_trend(self, predictions: List[PredictionDataPoint]) -> str:
        """检测趋势"""
        if not predictions:
            return "stable"

        values = [p.predicted_value for p in predictions]
        first_half_avg = sum(values[: len(values) // 2]) / (len(values) // 2)
        second_half_avg = sum(values[len(values) // 2 :]) / (
            len(values) - len(values) // 2
        )

        diff_percent = (second_half_avg - first_half_avg) / first_half_avg * 100

        if diff_percent > 10:
            return "increasing"
        elif diff_percent < -10:
            return "decreasing"
        else:
            return "stable"

    def _find_peak_time(
        self, predictions: List[PredictionDataPoint]
    ) -> Optional[datetime]:
        """找出峰值时间"""
        if not predictions:
            return None
        max_pred = max(predictions, key=lambda p: p.predicted_value)
        return max_pred.timestamp

    def _check_periodicity(self, values: List[float]) -> bool:
        """检查周期性"""
        # 简单的周期性检测逻辑
        if len(values) < 24:
            return False
        # 这里可以实现更复杂的周期性检测算法
        return True

    def _calculate_volatility(self, values: List[float]) -> float:
        """计算波动性"""
        if len(values) < 2:
            return 0.0
        import numpy as np

        return float(np.std(values))

    def _detect_seasonality(
        self, predictions: List[PredictionDataPoint]
    ) -> Dict[str, Any]:
        """检测季节性"""
        return {
            "daily_pattern": True,
            "weekly_pattern": False,
            "monthly_pattern": False,
        }

    async def _get_resource_usage(self) -> Dict[str, float]:
        """获取资源使用情况"""
        # 这里应该获取实际的资源使用情况
        return {"cpu_percent": 15.0, "memory_percent": 25.0, "disk_percent": 10.0}

    def is_initialized(self) -> bool:
        """检查服务是否已初始化"""
        return self._initialized

    async def cleanup(self) -> None:
        """清理资源"""
        try:
            self._initialized = False
            self._predictor = None
            self._feature_extractor = None
            self._anomaly_detector = None
            self._scaling_advisor = None
            self._cost_analyzer = None
            self._model_manager = None
            self.logger.info("预测服务资源已清理")
        except Exception as e:
            self.logger.error(f"清理资源失败: {str(e)}")
