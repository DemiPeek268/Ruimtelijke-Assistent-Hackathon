"""Tests for the MLflow feedback helper.

The helper is a thin wrapper around `MlflowClient.search_traces` plus
`mlflow.log_assessment / update_assessment / delete_assessment`. It keeps
each (trace, user) bound to AT MOST ONE `user_thumbs` assessment — re-clicks
update or delete, never append. The advisory lock in the router prevents
concurrent clicks from inserting duplicates, so the helper itself doesn't
need to self-heal.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


def _trace(trace_id: str = "tr-abc123", assessments: list | None = None):
    """Build the minimal trace shape the helper reads.

    `trace.info.trace_id` and `trace.info.assessments` are the only fields
    touched by the helper.
    """
    return SimpleNamespace(
        info=SimpleNamespace(trace_id=trace_id, assessments=assessments or []),
    )


def _existing_thumbs(
    *, assessment_id: str = "asmt-1", user_id: str = "user-oid-a", value: bool = True
):
    """Build a SimpleNamespace mimicking an MLflow Feedback assessment from `user_id`."""
    return SimpleNamespace(
        assessment_id=assessment_id,
        name="user_thumbs",
        value=value,
        source=SimpleNamespace(source_type="HUMAN", source_id=user_id),
    )


class TestLogFeedbackToMlflow:
    def test_first_click_logs_new_assessment(self):
        """No prior assessment → mlflow.log_assessment is called once."""
        from app.mlflow_monitoring import feedback as helper

        with (
            patch.object(helper, "settings") as mock_settings,
            patch.object(helper, "MlflowClient") as MockClient,
            patch.object(helper, "mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_settings.MLFLOW_EXPERIMENT_NAME = "exp"
            client = MockClient.return_value
            client.get_experiment_by_name.return_value = SimpleNamespace(
                experiment_id="42"
            )
            client.search_traces.return_value = [_trace("tr-1", assessments=[])]

            helper.log_feedback_to_mlflow(
                message_id="msg-xyz",
                rating="up",
                user_id="user-oid-a",
                comment=None,
            )

            mock_mlflow.log_assessment.assert_called_once()
            mock_mlflow.update_assessment.assert_not_called()
            mock_mlflow.delete_assessment.assert_not_called()
            kwargs = mock_mlflow.log_assessment.call_args.kwargs
            assert kwargs["trace_id"] == "tr-1"
            assert kwargs["assessment"].name == "user_thumbs"
            assert kwargs["assessment"].value is True
            assert kwargs["assessment"].source.source_id == "user-oid-a"
            assert kwargs["assessment"].rationale is None

    def test_thumbs_down_with_comment_passes_rationale(self):
        """rating='down' + comment='X' → assessment.value=False, rationale='X'."""
        from app.mlflow_monitoring import feedback as helper

        with (
            patch.object(helper, "settings") as mock_settings,
            patch.object(helper, "MlflowClient") as MockClient,
            patch.object(helper, "mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_settings.MLFLOW_EXPERIMENT_NAME = "exp"
            client = MockClient.return_value
            client.get_experiment_by_name.return_value = SimpleNamespace(
                experiment_id="42"
            )
            client.search_traces.return_value = [_trace("tr-2")]

            helper.log_feedback_to_mlflow(
                message_id="msg-xyz",
                rating="down",
                user_id="user-oid-b",
                comment="te weinig context",
            )

            assessment = mock_mlflow.log_assessment.call_args.kwargs["assessment"]
            assert assessment.value is False
            assert assessment.rationale == "te weinig context"

    def test_flip_updates_existing_assessment_in_place(self):
        """Prior up → click down: update_assessment called with same id, NOT log_assessment.

        This is the regression fix — without dedup, MLflow stacked thumbs on
        every click (1 up + 2 downs instead of just the current state).
        """
        from app.mlflow_monitoring import feedback as helper

        prior = _existing_thumbs(
            assessment_id="asmt-old", user_id="user-oid-a", value=True
        )

        with (
            patch.object(helper, "settings") as mock_settings,
            patch.object(helper, "MlflowClient") as MockClient,
            patch.object(helper, "mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_settings.MLFLOW_EXPERIMENT_NAME = "exp"
            client = MockClient.return_value
            client.get_experiment_by_name.return_value = SimpleNamespace(
                experiment_id="42"
            )
            client.search_traces.return_value = [_trace("tr-flip", assessments=[prior])]

            helper.log_feedback_to_mlflow(
                message_id="msg-flip",
                rating="down",
                user_id="user-oid-a",
                comment=None,
            )

            mock_mlflow.update_assessment.assert_called_once()
            mock_mlflow.log_assessment.assert_not_called()
            kwargs = mock_mlflow.update_assessment.call_args.kwargs
            assert kwargs["trace_id"] == "tr-flip"
            assert kwargs["assessment_id"] == "asmt-old"
            assert kwargs["assessment"].value is False

    def test_clear_deletes_prior_assessment(self):
        """rating=None + prior exists → delete_assessment(prior_id), no new log."""
        from app.mlflow_monitoring import feedback as helper

        prior = _existing_thumbs(assessment_id="asmt-to-remove", user_id="user-oid-a")

        with (
            patch.object(helper, "settings") as mock_settings,
            patch.object(helper, "MlflowClient") as MockClient,
            patch.object(helper, "mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_settings.MLFLOW_EXPERIMENT_NAME = "exp"
            client = MockClient.return_value
            client.get_experiment_by_name.return_value = SimpleNamespace(
                experiment_id="42"
            )
            client.search_traces.return_value = [
                _trace("tr-clear", assessments=[prior])
            ]

            helper.log_feedback_to_mlflow(
                message_id="msg-clear",
                rating=None,
                user_id="user-oid-a",
                comment=None,
            )

            mock_mlflow.delete_assessment.assert_called_once_with(
                trace_id="tr-clear", assessment_id="asmt-to-remove"
            )
            mock_mlflow.log_assessment.assert_not_called()
            mock_mlflow.update_assessment.assert_not_called()

    def test_clear_with_no_prior_is_a_noop(self):
        """rating=None + no prior assessment → nothing called."""
        from app.mlflow_monitoring import feedback as helper

        with (
            patch.object(helper, "settings") as mock_settings,
            patch.object(helper, "MlflowClient") as MockClient,
            patch.object(helper, "mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_settings.MLFLOW_EXPERIMENT_NAME = "exp"
            client = MockClient.return_value
            client.get_experiment_by_name.return_value = SimpleNamespace(
                experiment_id="42"
            )
            client.search_traces.return_value = [_trace("tr-x", assessments=[])]

            helper.log_feedback_to_mlflow(
                message_id="msg-x",
                rating=None,
                user_id="u",
                comment=None,
            )

            mock_mlflow.delete_assessment.assert_not_called()
            mock_mlflow.log_assessment.assert_not_called()
            mock_mlflow.update_assessment.assert_not_called()

    def test_other_users_prior_does_not_block_new_log(self):
        """A user_thumbs from a different user must NOT be treated as the current user's prior."""
        from app.mlflow_monitoring import feedback as helper

        other = _existing_thumbs(
            assessment_id="asmt-other", user_id="someone-else", value=False
        )

        with (
            patch.object(helper, "settings") as mock_settings,
            patch.object(helper, "MlflowClient") as MockClient,
            patch.object(helper, "mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_settings.MLFLOW_EXPERIMENT_NAME = "exp"
            client = MockClient.return_value
            client.get_experiment_by_name.return_value = SimpleNamespace(
                experiment_id="42"
            )
            client.search_traces.return_value = [
                _trace("tr-other", assessments=[other])
            ]

            helper.log_feedback_to_mlflow(
                message_id="msg-q",
                rating="up",
                user_id="user-oid-a",
                comment=None,
            )

            mock_mlflow.log_assessment.assert_called_once()
            mock_mlflow.update_assessment.assert_not_called()

    def test_searches_with_client_request_id_filter_scoped_to_experiment(self):
        """search_traces is filtered to our experiment by client_request_id."""
        from app.mlflow_monitoring import feedback as helper

        with (
            patch.object(helper, "settings") as mock_settings,
            patch.object(helper, "MlflowClient") as MockClient,
            patch.object(helper, "mlflow"),
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_settings.MLFLOW_EXPERIMENT_NAME = "exp"
            client = MockClient.return_value
            client.get_experiment_by_name.return_value = SimpleNamespace(
                experiment_id="42"
            )
            client.search_traces.return_value = [_trace("tr-3")]

            helper.log_feedback_to_mlflow(
                message_id="msg-search-me",
                rating="up",
                user_id="u",
                comment=None,
            )

            kwargs = client.search_traces.call_args.kwargs
            assert "msg-search-me" in kwargs["filter_string"]
            assert "client_request_id" in kwargs["filter_string"]
            assert kwargs["experiment_ids"] == ["42"]
            assert kwargs["max_results"] == 1

    def test_filter_string_escapes_single_quotes_in_message_id(self):
        """A pathological message_id containing a single quote must not break
        the filter string (defense-in-depth — message_id is server-minted today,
        but the helper should be safe if called from elsewhere later)."""
        from app.mlflow_monitoring import feedback as helper

        with (
            patch.object(helper, "settings") as mock_settings,
            patch.object(helper, "MlflowClient") as MockClient,
            patch.object(helper, "mlflow"),
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_settings.MLFLOW_EXPERIMENT_NAME = "exp"
            client = MockClient.return_value
            client.get_experiment_by_name.return_value = SimpleNamespace(
                experiment_id="42"
            )
            client.search_traces.return_value = [_trace("tr-quoted")]

            helper.log_feedback_to_mlflow(
                message_id="msg-'OR-1=1",
                rating="up",
                user_id="u",
                comment=None,
            )

            # The filter must use MLflow's standard single-quote escape (doubled
            # single quotes), so the value is exactly one well-formed literal.
            filt = client.search_traces.call_args.kwargs["filter_string"]
            # Doubled-up single quotes for the embedded quote.
            assert "msg-''OR-1=1" in filt
            # Filter is well-formed: exactly one opening and one closing literal.
            assert filt.count("'") % 2 == 0
            # Raw value containing a stray single quote is NOT present unescaped.
            assert "msg-'OR-1=1" not in filt.replace("''", "")

    def test_no_trace_found_skips_all_mlflow_writes(self):
        """If search returns empty, neither log/update/delete is called."""
        from app.mlflow_monitoring import feedback as helper

        with (
            patch.object(helper, "settings") as mock_settings,
            patch.object(helper, "MlflowClient") as MockClient,
            patch.object(helper, "mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_settings.MLFLOW_EXPERIMENT_NAME = "exp"
            client = MockClient.return_value
            client.get_experiment_by_name.return_value = SimpleNamespace(
                experiment_id="42"
            )
            client.search_traces.return_value = []

            helper.log_feedback_to_mlflow(
                message_id="msg-orphan",
                rating="up",
                user_id="u",
                comment=None,
            )

            mock_mlflow.log_assessment.assert_not_called()
            mock_mlflow.update_assessment.assert_not_called()
            mock_mlflow.delete_assessment.assert_not_called()

    def test_disabled_setting_short_circuits(self):
        """MLFLOW_ENABLED=False → no MlflowClient instantiation, no MLflow writes."""
        from app.mlflow_monitoring import feedback as helper

        with (
            patch.object(helper, "settings") as mock_settings,
            patch.object(helper, "MlflowClient") as MockClient,
            patch.object(helper, "mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = False

            helper.log_feedback_to_mlflow(
                message_id="msg-x",
                rating="up",
                user_id="u",
                comment=None,
            )

            MockClient.assert_not_called()
            mock_mlflow.log_assessment.assert_not_called()

    def test_mlflow_exception_is_swallowed(self):
        """Any exception from MLflow APIs must NOT propagate — feedback POST already committed."""
        from app.mlflow_monitoring import feedback as helper

        with (
            patch.object(helper, "settings") as mock_settings,
            patch.object(helper, "MlflowClient") as MockClient,
            patch.object(helper, "mlflow"),
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_settings.MLFLOW_EXPERIMENT_NAME = "exp"
            MockClient.side_effect = RuntimeError("mlflow server down")

            helper.log_feedback_to_mlflow(
                message_id="msg-x",
                rating="up",
                user_id="u",
                comment=None,
            )

    def test_missing_experiment_skips_silently(self):
        """If the experiment lookup returns None, helper bails out cleanly."""
        from app.mlflow_monitoring import feedback as helper

        with (
            patch.object(helper, "settings") as mock_settings,
            patch.object(helper, "MlflowClient") as MockClient,
            patch.object(helper, "mlflow") as mock_mlflow,
        ):
            mock_settings.MLFLOW_ENABLED = True
            mock_settings.MLFLOW_EXPERIMENT_NAME = "exp"
            client = MockClient.return_value
            client.get_experiment_by_name.return_value = None

            helper.log_feedback_to_mlflow(
                message_id="msg-x",
                rating="up",
                user_id="u",
                comment=None,
            )

            client.search_traces.assert_not_called()
            mock_mlflow.log_assessment.assert_not_called()
