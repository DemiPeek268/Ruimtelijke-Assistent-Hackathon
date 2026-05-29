"""Best-effort MLflow side-effect for user feedback.

Isolates every MLflow import and call to one module so the router stays slim
and tests can patch a single namespace. All errors are swallowed — the
Postgres write is the source of truth; MLflow is purely downstream.

Each (trace, user) carries at most ONE `user_thumbs` assessment. Calls are
idempotent: a prior assessment is updated in place (or deleted on clear)
instead of appended, so the MLflow UI doesn't stack repeated up/down clicks.
The advisory lock in the feedback router serializes concurrent clicks on the
same (message_id, user_id), so this helper doesn't need to defend against
already-duplicated assessments on a trace.
"""

import logging
from typing import Literal

import mlflow
from mlflow import MlflowClient
from mlflow.entities import AssessmentSource, Feedback

from app.config import settings

logger = logging.getLogger(__name__)

ASSESSMENT_NAME = "user_thumbs"


def log_feedback_to_mlflow(
    message_id: str,
    rating: Literal["up", "down"] | None,
    user_id: str,
    comment: str | None,
) -> None:
    """Sync a feedback rating onto the trace tagged with `client_request_id == message_id`.

    `rating=None` clears: any prior `user_thumbs` from this user is deleted.
    `rating in {"up", "down"}` either updates the user's existing assessment
    or logs a new one — never appends a second.

    Best-effort: if MLflow is disabled, the experiment is missing, no trace is
    found, or the MLflow server is unreachable, this logs a warning and returns.
    """
    if not settings.MLFLOW_ENABLED:
        return
    try:
        client = MlflowClient()
        experiment = client.get_experiment_by_name(settings.MLFLOW_EXPERIMENT_NAME)
        if experiment is None:
            logger.warning(
                "MLflow experiment %r not found — skipping feedback sync",
                settings.MLFLOW_EXPERIMENT_NAME,
            )
            return

        # `attributes.client_request_id` is the documented filter path for
        # first-class trace fields in MLflow 3.x search syntax. message_id is
        # server-minted as a UUID today; the single-quote doubling is
        # belt-and-braces against a future caller passing arbitrary input.
        escaped_message_id = message_id.replace("'", "''")
        traces = client.search_traces(
            filter_string=f"attributes.client_request_id = '{escaped_message_id}'",
            experiment_ids=[experiment.experiment_id],
            max_results=1,
        )
        if not traces:
            # Divergence between Postgres (has feedback) and MLflow (no trace
            # to attach it to). Worth alerting on, not just a transient warning.
            logger.error(
                "No MLflow trace found for client_request_id=%s — feedback skipped",
                message_id,
            )
            return

        trace = traces[0]
        trace_id = trace.info.trace_id
        prior = _find_user_thumbs(trace.info.assessments or [], user_id)

        prior_id = prior.assessment_id if prior is not None else None

        if rating is None:
            if prior_id is not None:
                mlflow.delete_assessment(trace_id=trace_id, assessment_id=prior_id)
            return

        assessment = Feedback(
            name=ASSESSMENT_NAME,
            value=(rating == "up"),
            source=AssessmentSource(source_type="HUMAN", source_id=user_id),
            rationale=comment,
        )
        if prior_id is None:
            mlflow.log_assessment(trace_id=trace_id, assessment=assessment)
        else:
            mlflow.update_assessment(
                trace_id=trace_id,
                assessment_id=prior_id,
                assessment=assessment,
            )
    except Exception:
        logger.warning(
            "MLflow feedback sync failed for message_id=%s — swallowed",
            message_id,
            exc_info=True,
        )


def _find_user_thumbs(assessments, user_id: str):
    """Return this user's `user_thumbs` assessment on the trace, or None."""
    return next(
        (
            a
            for a in assessments
            if a.name == ASSESSMENT_NAME
            and a.source is not None
            and a.source.source_type == "HUMAN"
            and a.source.source_id == user_id
        ),
        None,
    )
