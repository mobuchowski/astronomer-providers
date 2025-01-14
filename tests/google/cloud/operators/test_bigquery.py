from unittest import mock
from unittest.mock import MagicMock

import pytest
from airflow.exceptions import AirflowException, TaskDeferred
from airflow.utils.timezone import datetime
from google.cloud.exceptions import Conflict

from astronomer.providers.google.cloud.operators.bigquery import (
    BigQueryCheckOperatorAsync,
    BigQueryGetDataOperatorAsync,
    BigQueryInsertJobOperatorAsync,
    BigQueryIntervalCheckOperatorAsync,
    BigQueryValueCheckOperatorAsync,
)
from astronomer.providers.google.cloud.triggers.bigquery import (
    BigQueryCheckTrigger,
    BigQueryGetDataTrigger,
    BigQueryInsertJobTrigger,
    BigQueryIntervalCheckTrigger,
    BigQueryValueCheckTrigger,
)
from tests.utils.airflow_util import create_context

TEST_DATASET_LOCATION = "EU"
TEST_GCP_PROJECT_ID = "test-project"
TEST_DATASET = "test-dataset"
TEST_TABLE = "test-table"


class TestBigQueryInsertJobOperatorAsync:
    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryInsertJobOperatorAsync.defer")
    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_bigquery_insert_job_operator_async_finish_before_deferred(self, mock_hook, mock_defer):
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"

        configuration = {
            "query": {
                "query": "SELECT * FROM any",
                "useLegacySql": False,
            }
        }
        mock_hook.return_value.insert_job.return_value = MagicMock(job_id=real_job_id, error_result=False)
        mock_hook.return_value.insert_job.return_value.running.return_value = False

        op = BigQueryInsertJobOperatorAsync(
            task_id="insert_query_job",
            configuration=configuration,
            location=TEST_DATASET_LOCATION,
            job_id=job_id,
            project_id=TEST_GCP_PROJECT_ID,
        )

        op.execute(create_context(op))
        assert not mock_defer.called

    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_bigquery_insert_job_operator_async(self, mock_hook):
        """
        Asserts that a task is deferred and a BigQueryInsertJobTrigger will be fired
        when the BigQueryInsertJobOperatorAsync is executed.
        """
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"

        configuration = {
            "query": {
                "query": "SELECT * FROM any",
                "useLegacySql": False,
            }
        }
        mock_hook.return_value.insert_job.return_value = MagicMock(job_id=real_job_id, error_result=False)

        op = BigQueryInsertJobOperatorAsync(
            task_id="insert_query_job",
            configuration=configuration,
            location=TEST_DATASET_LOCATION,
            job_id=job_id,
            project_id=TEST_GCP_PROJECT_ID,
        )

        with pytest.raises(TaskDeferred) as exc:
            op.execute(create_context(op))

        assert isinstance(
            exc.value.trigger, BigQueryInsertJobTrigger
        ), "Trigger is not a BigQueryInsertJobTrigger"

    def test_bigquery_insert_job_operator_execute_failure(self, context):
        """Tests that an AirflowException is raised in case of error event"""
        configuration = {
            "query": {
                "query": "SELECT * FROM any",
                "useLegacySql": False,
            }
        }
        job_id = "123456"

        operator = BigQueryInsertJobOperatorAsync(
            task_id="insert_query_job",
            configuration=configuration,
            location=TEST_DATASET_LOCATION,
            job_id=job_id,
            project_id=TEST_GCP_PROJECT_ID,
        )

        with pytest.raises(AirflowException):
            operator.execute_complete(
                context=None, event={"status": "error", "message": "test failure message"}
            )

    def test_bigquery_insert_job_operator_execute_complete(self):
        """Asserts that logging occurs as expected"""
        configuration = {
            "query": {
                "query": "SELECT * FROM any",
                "useLegacySql": False,
            }
        }
        job_id = "123456"

        operator = BigQueryInsertJobOperatorAsync(
            task_id="insert_query_job",
            configuration=configuration,
            location=TEST_DATASET_LOCATION,
            job_id=job_id,
            project_id=TEST_GCP_PROJECT_ID,
        )
        with mock.patch.object(operator.log, "info") as mock_log_info:
            operator.execute_complete(
                context=create_context(operator),
                event={"status": "success", "message": "Job completed", "job_id": job_id},
            )
        mock_log_info.assert_called_with(
            "%s completed with response %s ", "insert_query_job", "Job completed"
        )

    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_bigquery_insert_job_operator_with_job_id_generate(self, mock_hook):
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"

        configuration = {
            "query": {
                "query": "SELECT * FROM any",
                "useLegacySql": False,
            }
        }

        mock_hook.return_value.insert_job.side_effect = Conflict("any")
        job = MagicMock(
            job_id=real_job_id,
            error_result=False,
            state="PENDING",
            done=lambda: False,
        )
        mock_hook.return_value.get_job.return_value = job

        op = BigQueryInsertJobOperatorAsync(
            task_id="insert_query_job",
            configuration=configuration,
            location=TEST_DATASET_LOCATION,
            job_id=job_id,
            project_id=TEST_GCP_PROJECT_ID,
            reattach_states={"PENDING"},
        )

        with pytest.raises(TaskDeferred):
            op.execute(create_context(op))

        mock_hook.return_value.generate_job_id.assert_called_once_with(
            job_id=job_id,
            dag_id="adhoc_airflow",
            task_id="insert_query_job",
            logical_date=datetime(2022, 1, 1, 1, 0),
            configuration=configuration,
            force_rerun=True,
        )

    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_execute_reattach(self, mock_hook):
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"
        mock_hook.return_value.generate_job_id.return_value = f"{job_id}_{hash_}"

        configuration = {
            "query": {
                "query": "SELECT * FROM any",
                "useLegacySql": False,
            }
        }

        mock_hook.return_value.insert_job.side_effect = Conflict("any")
        job = MagicMock(
            job_id=real_job_id,
            error_result=False,
            state="PENDING",
            done=lambda: False,
        )
        mock_hook.return_value.get_job.return_value = job

        op = BigQueryInsertJobOperatorAsync(
            task_id="insert_query_job",
            configuration=configuration,
            location=TEST_DATASET_LOCATION,
            job_id=job_id,
            project_id=TEST_GCP_PROJECT_ID,
            reattach_states={"PENDING"},
        )

        with pytest.raises(TaskDeferred):
            op.execute(create_context(op))

        mock_hook.return_value.get_job.assert_called_once_with(
            location=TEST_DATASET_LOCATION,
            job_id=real_job_id,
            project_id=TEST_GCP_PROJECT_ID,
        )

        job._begin.assert_called_once_with()

    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_execute_force_rerun(self, mock_hook):
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"
        mock_hook.return_value.generate_job_id.return_value = f"{job_id}_{hash_}"

        configuration = {
            "query": {
                "query": "SELECT * FROM any",
                "useLegacySql": False,
            }
        }

        mock_hook.return_value.insert_job.side_effect = Conflict("any")
        job = MagicMock(
            job_id=real_job_id,
            error_result=False,
            state="DONE",
            done=lambda: False,
        )
        mock_hook.return_value.get_job.return_value = job

        op = BigQueryInsertJobOperatorAsync(
            task_id="insert_query_job",
            configuration=configuration,
            location=TEST_DATASET_LOCATION,
            job_id=job_id,
            project_id=TEST_GCP_PROJECT_ID,
            reattach_states={"PENDING"},
        )

        with pytest.raises(AirflowException) as exc:
            op.execute(create_context(op))

        expected_exception_msg = (
            f"Job with id: {real_job_id} already exists and is in {job.state} state. "
            f"If you want to force rerun it consider setting `force_rerun=True`."
            f"Or, if you want to reattach in this scenario add {job.state} to `reattach_states`"
        )

        assert str(exc.value) == expected_exception_msg

        mock_hook.return_value.get_job.assert_called_once_with(
            location=TEST_DATASET_LOCATION,
            job_id=real_job_id,
            project_id=TEST_GCP_PROJECT_ID,
        )


class TestBigQueryCheckOperatorAsync:
    @mock.patch("airflow.providers.google.cloud.operators.bigquery.BigQueryCheckOperator.execute")
    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryCheckOperatorAsync.defer")
    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_bigquery_check_operator_async_finish_before_deferred(self, mock_hook, mock_defer, mock_execute):
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"

        mock_hook.return_value.insert_job.return_value = MagicMock(job_id=real_job_id, error_result=False)
        mock_hook.return_value.insert_job.return_value.running.return_value = False

        op = BigQueryCheckOperatorAsync(
            task_id="bq_check_operator_job",
            sql="SELECT * FROM any",
            location=TEST_DATASET_LOCATION,
        )
        op.execute(create_context(op))
        assert not mock_defer.called
        assert mock_execute.called

    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_bigquery_check_operator_async(self, mock_hook):
        """
        Asserts that a task is deferred and a BigQueryCheckTrigger will be fired
        when the BigQueryCheckOperatorAsync is executed.
        """
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"

        mock_hook.return_value.insert_job.return_value = MagicMock(job_id=real_job_id, error_result=False)

        op = BigQueryCheckOperatorAsync(
            task_id="bq_check_operator_job",
            sql="SELECT * FROM any",
            location=TEST_DATASET_LOCATION,
        )

        with pytest.raises(TaskDeferred) as exc:
            op.execute(create_context(op))

        assert isinstance(exc.value.trigger, BigQueryCheckTrigger), "Trigger is not a BigQueryCheckTrigger"

    def test_bigquery_check_operator_execute_failure(self, context):
        """Tests that an AirflowException is raised in case of error event"""

        operator = BigQueryCheckOperatorAsync(
            task_id="bq_check_operator_execute_failure",
            sql="SELECT * FROM any",
            location=TEST_DATASET_LOCATION,
        )

        with pytest.raises(AirflowException):
            operator.execute_complete(
                context=None, event={"status": "error", "message": "test failure message"}
            )

    def test_bigquery_check_op_execute_complete_with_no_records(self):
        """Asserts that exception is raised with correct expected exception message"""

        operator = BigQueryCheckOperatorAsync(
            task_id="bq_check_operator_execute_complete",
            sql="SELECT * FROM any",
            location=TEST_DATASET_LOCATION,
        )

        with pytest.raises(AirflowException) as exc:
            operator.execute_complete(context=None, event={"status": "success", "records": None})

        expected_exception_msg = "The query returned None"

        assert str(exc.value) == expected_exception_msg

    def test_bigquery_check_op_execute_complete_with_non_boolean_records(self):
        """Executing a sql which returns a non-boolean value should raise exception"""

        test_sql = "SELECT * FROM any"

        operator = BigQueryCheckOperatorAsync(
            task_id="bq_check_operator_execute_complete", sql=test_sql, location=TEST_DATASET_LOCATION
        )

        expected_exception_msg = f"Test failed.\nQuery:\n{test_sql}\nResults:\n{[20, False]!s}"

        with pytest.raises(AirflowException) as exc:
            operator.execute_complete(context=None, event={"status": "success", "records": [20, False]})

        assert str(exc.value) == expected_exception_msg

    def test_bigquery_check_operator_execute_complete(self):
        """Asserts that logging occurs as expected"""

        operator = BigQueryCheckOperatorAsync(
            task_id="bq_check_operator_execute_complete",
            sql="SELECT * FROM any",
            location=TEST_DATASET_LOCATION,
        )

        with mock.patch.object(operator.log, "info") as mock_log_info:
            operator.execute_complete(context=None, event={"status": "success", "records": [20]})
        mock_log_info.assert_called_with("Success.")


class TestBigQueryIntervalCheckOperatorAsync:
    def test_bigquery_interval_check_operator_execute_complete(self):
        """Asserts that logging occurs as expected"""

        operator = BigQueryIntervalCheckOperatorAsync(
            task_id="bq_interval_check_operator_execute_complete",
            table="test_table",
            metrics_thresholds={"COUNT(*)": 1.5},
            location=TEST_DATASET_LOCATION,
        )

        with mock.patch.object(operator.log, "info") as mock_log_info:
            operator.execute_complete(context=None, event={"status": "success", "message": "Job completed"})
        mock_log_info.assert_called_with(
            "%s completed with response %s ", "bq_interval_check_operator_execute_complete", "success"
        )

    def test_bigquery_interval_check_operator_execute_failure(self, context):
        """Tests that an AirflowException is raised in case of error event"""

        operator = BigQueryIntervalCheckOperatorAsync(
            task_id="bq_interval_check_operator_execute_complete",
            table="test_table",
            metrics_thresholds={"COUNT(*)": 1.5},
            location=TEST_DATASET_LOCATION,
        )

        with pytest.raises(AirflowException):
            operator.execute_complete(
                context=None, event={"status": "error", "message": "test failure message"}
            )

    @mock.patch("airflow.providers.google.cloud.operators.bigquery.BigQueryIntervalCheckOperator.execute")
    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryIntervalCheckOperator.defer")
    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_bigquery_interval_check_operator_async_finish_before_defer(
        self, mock_hook, mock_defer, mock_execute
    ):
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"

        mock_hook.return_value.insert_job.return_value = MagicMock(job_id=real_job_id, error_result=False)
        mock_hook.return_value.insert_job.return_value.running.return_value = False

        op = BigQueryIntervalCheckOperatorAsync(
            task_id="bq_interval_check_operator_execute_complete",
            table="test_table",
            metrics_thresholds={"COUNT(*)": 1.5},
            location=TEST_DATASET_LOCATION,
        )

        op.execute(create_context(op))
        assert not mock_defer.called
        assert mock_execute.called

    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_bigquery_interval_check_operator_async(self, mock_hook):
        """
        Asserts that a task is deferred and a BigQueryIntervalCheckTrigger will be fired
        when the BigQueryIntervalCheckOperatorAsync is executed.
        """
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"

        mock_hook.return_value.insert_job.return_value = MagicMock(job_id=real_job_id, error_result=False)

        op = BigQueryIntervalCheckOperatorAsync(
            task_id="bq_interval_check_operator_execute_complete",
            table="test_table",
            metrics_thresholds={"COUNT(*)": 1.5},
            location=TEST_DATASET_LOCATION,
        )

        with pytest.raises(TaskDeferred) as exc:
            op.execute(create_context(op))

        assert isinstance(
            exc.value.trigger, BigQueryIntervalCheckTrigger
        ), "Trigger is not a BigQueryIntervalCheckTrigger"


class TestBigQueryGetDataOperatorAsync:
    @mock.patch("airflow.providers.google.cloud.operators.bigquery.BigQueryGetDataOperator.execute")
    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryGetDataOperatorAsync.defer")
    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_bigquery_get_data_operator_async_finish_before_deferred(
        self, mock_hook, mock_defer, mock_execute
    ):
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"

        mock_hook.return_value.insert_job.return_value = MagicMock(job_id=real_job_id, error_result=False)
        mock_hook.return_value.insert_job.return_value.running.return_value = False

        op = BigQueryGetDataOperatorAsync(
            task_id="get_data_from_bq",
            dataset_id=TEST_DATASET,
            table_id=TEST_TABLE,
            max_results=100,
            selected_fields="value,name",
        )

        op.execute(create_context(op))
        assert not mock_defer.called
        assert mock_execute.called

    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_bigquery_get_data_operator_async_with_selected_fields(self, mock_hook):
        """
        Asserts that a task is deferred and a BigQuerygetDataTrigger will be fired
        when the BigQuerygetDataOperatorAsync is executed.
        """
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"

        mock_hook.return_value.insert_job.return_value = MagicMock(job_id=real_job_id, error_result=False)

        op = BigQueryGetDataOperatorAsync(
            task_id="get_data_from_bq",
            dataset_id=TEST_DATASET,
            table_id=TEST_TABLE,
            max_results=100,
            selected_fields="value,name",
        )

        with pytest.raises(TaskDeferred) as exc:
            op.execute(create_context(op))

        assert isinstance(
            exc.value.trigger, BigQueryGetDataTrigger
        ), "Trigger is not a BigQueryGetDataTrigger"

    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_bigquery_get_data_operator_async_without_selected_fields(self, mock_hook):
        """
        Asserts that a task is deferred and a BigQuerygetDataTrigger will be fired
        when the BigQuerygetDataOperatorAsync is executed.
        """
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"

        mock_hook.return_value.insert_job.return_value = MagicMock(job_id=real_job_id, error_result=False)

        op = BigQueryGetDataOperatorAsync(
            task_id="get_data_from_bq",
            dataset_id=TEST_DATASET,
            table_id=TEST_TABLE,
            max_results=100,
        )

        with pytest.raises(TaskDeferred) as exc:
            op.execute(create_context(op))

        assert isinstance(
            exc.value.trigger, BigQueryGetDataTrigger
        ), "Trigger is not a BigQueryGetDataTrigger"

    def test_bigquery_get_data_operator_execute_failure(self, context):
        """Tests that an AirflowException is raised in case of error event"""

        operator = BigQueryGetDataOperatorAsync(
            task_id="get_data_from_bq",
            dataset_id=TEST_DATASET,
            table_id="any",
            max_results=100,
        )

        with pytest.raises(AirflowException):
            operator.execute_complete(
                context=None, event={"status": "error", "message": "test failure message"}
            )

    def test_bigquery_get_data_op_execute_complete_with_records(self):
        """Asserts that exception is raised with correct expected exception message"""

        operator = BigQueryGetDataOperatorAsync(
            task_id="get_data_from_bq",
            dataset_id=TEST_DATASET,
            table_id="any",
            max_results=100,
        )

        with mock.patch.object(operator.log, "info") as mock_log_info:
            operator.execute_complete(context=None, event={"status": "success", "records": [20]})
        mock_log_info.assert_called_with("Total extracted rows: %s", 1)


class TestBigQueryValueCheckOperatorAsync:
    def _get_value_check_async_operator(self, use_legacy_sql: bool = False):
        """Helper function to initialise BigQueryValueCheckOperatorAsync operator"""
        query = "SELECT COUNT(*) FROM Any"
        pass_val = 2

        return BigQueryValueCheckOperatorAsync(
            task_id="check_value",
            sql=query,
            pass_value=pass_val,
            use_legacy_sql=use_legacy_sql,
        )

    @mock.patch("airflow.providers.google.cloud.operators.bigquery.BigQueryValueCheckOperator.execute")
    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryValueCheckOperatorAsync.defer")
    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_bigquery_value_check_async_finish_before_deferred(self, mock_hook, mock_defer, mock_execute):
        operator = self._get_value_check_async_operator(True)
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"
        mock_hook.return_value.insert_job.return_value = MagicMock(job_id=real_job_id, error_result=False)
        mock_hook.return_value.insert_job.return_value.running.return_value = False

        operator.execute(create_context(operator))
        assert not mock_defer.called
        assert mock_execute.called

    @mock.patch("astronomer.providers.google.cloud.operators.bigquery.BigQueryHook")
    def test_bigquery_value_check_async(self, mock_hook):
        """
        Asserts that a task is deferred and a BigQueryValueCheckTrigger will be fired
        when the BigQueryValueCheckOperatorAsync is executed.
        """
        operator = self._get_value_check_async_operator(True)
        job_id = "123456"
        hash_ = "hash"
        real_job_id = f"{job_id}_{hash_}"
        mock_hook.return_value.insert_job.return_value = MagicMock(job_id=real_job_id, error_result=False)
        with pytest.raises(TaskDeferred) as exc:
            operator.execute(create_context(operator))

        assert isinstance(
            exc.value.trigger, BigQueryValueCheckTrigger
        ), "Trigger is not a BigQueryValueCheckTrigger"

    def test_bigquery_value_check_operator_execute_complete_success(self):
        """Tests response message in case of success event"""
        operator = self._get_value_check_async_operator()

        assert (
            operator.execute_complete(context=None, event={"status": "success", "message": "Job completed!"})
            is None
        )

    def test_bigquery_value_check_operator_execute_complete_failure(self):
        """Tests that an AirflowException is raised in case of error event"""
        operator = self._get_value_check_async_operator()

        with pytest.raises(AirflowException):
            operator.execute_complete(
                context=None, event={"status": "error", "message": "test failure message"}
            )

    @pytest.mark.parametrize(
        "kwargs, expected",
        [
            ({"sql": "SELECT COUNT(*) from Any"}, "missing keyword argument 'pass_value'"),
            ({"pass_value": "Any"}, "missing keyword argument 'sql'"),
        ],
    )
    def test_bigquery_value_check_missing_param(self, kwargs, expected):
        """Assert the exception if require param not pass to BigQueryValueCheckOperatorAsync operator"""
        with pytest.raises(AirflowException) as missing_param:
            BigQueryValueCheckOperatorAsync(**kwargs)
        assert missing_param.value.args[0] == expected

    def test_bigquery_value_check_empty(self):
        """Assert the exception if require param not pass to BigQueryValueCheckOperatorAsync operator"""
        expected, expected1 = (
            "missing keyword arguments 'sql', 'pass_value'",
            "missing keyword arguments 'pass_value', 'sql'",
        )
        with pytest.raises(AirflowException) as missing_param:
            BigQueryValueCheckOperatorAsync(kwargs={})
        assert (missing_param.value.args[0] == expected) or (missing_param.value.args[0] == expected1)
