import logging

from app.config import settings

logger = logging.getLogger(__name__)


def init_mlflow() -> None:
    """Configure MLflow tracking and enable LangChain autolog."""
    if not settings.MLFLOW_ENABLED:
        logger.info("MLflow tracking disabled (MLFLOW_ENABLED=false)")
        return
    try:
        import mlflow

        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
        mlflow.set_experiment(settings.MLFLOW_EXPERIMENT_NAME)
        mlflow.langchain.autolog(run_tracer_inline=False)
        logger.info(
            "MLflow tracking enabled: %s / %s",
            settings.MLFLOW_TRACKING_URI,
            settings.MLFLOW_EXPERIMENT_NAME,
        )
    except Exception:
        logger.warning("MLflow init failed — tracing disabled", exc_info=True)
