import unittest
from datetime import timedelta
from typing import Any, List
from unittest import mock

import pytest
from airflow.exceptions import AirflowException, AirflowSkipException, TaskDeferred
from airflow.models import DAG, DagRun, TaskInstance
from airflow.models.variable import Variable
from airflow.utils import timezone
from parameterized import parameterized

from astronomer.providers.amazon.aws.sensors.s3 import (
    S3KeySensorAsync,
    S3KeySizeSensorAsync,
    S3KeysUnchangedSensorAsync,
    S3PrefixSensorAsync,
)
from astronomer.providers.amazon.aws.triggers.s3 import (
    S3KeysUnchangedTrigger,
    S3KeyTrigger,
)

MODULE = "astronomer.providers.amazon.aws.sensors.s3"


class TestS3KeySensorAsync:
    @mock.patch(f"{MODULE}.S3KeySensorAsync.defer")
    @mock.patch(f"{MODULE}.S3KeySensorAsync.poke", return_value=True)
    def test_finish_before_deferred(self, mock_poke, mock_defer, context):
        """Assert task is not deferred when it receives a finish status before deferring"""
        sensor = S3KeySensorAsync(task_id="s3_key_sensor", bucket_key="file_in_bucket")
        sensor.execute(context)
        assert not mock_defer.called

    @mock.patch(f"{MODULE}.S3KeySensorAsync.poke", return_value=False)
    def test_bucket_name_none_and_bucket_key_as_relative_path(self, mock_poke, context):
        """
        Test if exception is raised when bucket_name is None
        and bucket_key is provided with one of the two keys as relative path rather than s3:// url.
        """
        sensor = S3KeySensorAsync(task_id="s3_key_sensor", bucket_key="file_in_bucket")
        with pytest.raises(TaskDeferred):
            sensor.execute(context)

    @mock.patch(f"{MODULE}.S3KeySensorAsync.poke", return_value=False)
    @mock.patch("astronomer.providers.amazon.aws.hooks.s3.S3HookAsync.get_head_object")
    def test_bucket_name_none_and_bucket_key_is_list_and_contain_relative_path(
        self, mock_head_object, mock_poke, context
    ):
        """
        Test if exception is raised when bucket_name is None
        and bucket_key is provided with one of the two keys as relative path rather than s3:// url.
        :return:
        """
        mock_head_object.return_value = {"ContentLength": 0}
        sensor = S3KeySensorAsync(
            task_id="s3_key_sensor", bucket_key=["s3://test_bucket/file", "file_in_bucket"]
        )
        with pytest.raises(TaskDeferred):
            sensor.execute(context)

    @mock.patch(f"{MODULE}.S3KeySensorAsync.poke", return_value=False)
    def test_bucket_name_provided_and_bucket_key_is_s3_url(self, mock_poke, context):
        """
        Test if exception is raised when bucket_name is provided
        while bucket_key is provided as a full s3:// url.
        :return:
        """
        op = S3KeySensorAsync(
            task_id="s3_key_sensor", bucket_key="s3://test_bucket/file", bucket_name="test_bucket"
        )
        with pytest.raises(TaskDeferred):
            op.execute(context)

    @parameterized.expand(
        [
            ["s3://bucket/key", None],
            ["key", "bucket"],
        ]
    )
    @mock.patch(f"{MODULE}.S3KeySensorAsync.poke", return_value=False)
    @mock.patch("airflow.providers.amazon.aws.sensors.s3.S3Hook")
    def test_s3_key_sensor_async(self, key, bucket, mock_hook, mock_poke):
        """
        Asserts that a task is deferred and an S3KeyTrigger will be fired
        when the S3KeySensorAsync is executed.
        """
        mock_hook.check_for_key.return_value = False

        sensor = S3KeySensorAsync(
            task_id="s3_key_sensor_async",
            bucket_key=key,
            bucket_name=bucket,
        )

        with pytest.raises(TaskDeferred) as exc:
            sensor.execute(context=None)

        assert isinstance(exc.value.trigger, S3KeyTrigger), "Trigger is not a S3KeyTrigger"

    @parameterized.expand(
        [
            ["s3://bucket/key", None],
            ["key", "bucket"],
        ]
    )
    @mock.patch(f"{MODULE}.S3KeySensorAsync.poke", return_value=False)
    @mock.patch("airflow.providers.amazon.aws.sensors.s3.S3Hook")
    def test_s3_key_sensor_execute_complete_success(self, key, bucket, mock_poke, mock_hook):
        """
        Asserts that a task is completed with success status.
        """
        mock_hook.check_for_key.return_value = False

        sensor = S3KeySensorAsync(
            task_id="s3_key_sensor_async",
            bucket_key=key,
            bucket_name=bucket,
        )
        assert sensor.execute_complete(context={}, event={"status": "success"}) is None

    @parameterized.expand(
        [
            ["key", "bucket"],
        ]
    )
    @mock.patch(f"{MODULE}.S3KeySensorAsync.poke", return_value=False)
    def test_s3_key_sensor_execute_complete_success_with_keys(self, key, bucket, mock_poke):
        """
        Asserts that a task is completed with success status and check function
        """

        def check_fn(files: List[Any]) -> bool:
            return all(f.get("Size", 0) > 0 for f in files)

        sensor = S3KeySensorAsync(
            task_id="s3_key_sensor_async",
            bucket_key=key,
            bucket_name=bucket,
            check_fn=check_fn,
        )
        assert (
            sensor.execute_complete(context={}, event={"status": "running", "files": [{"Size": 10}]}) is None
        )

    @mock.patch(f"{MODULE}.S3KeySensorAsync._defer")
    def test_s3_key_sensor_re_defer(self, mock_defer):
        def check_fn(files: List[Any]) -> bool:
            return False

        sensor = S3KeySensorAsync(
            task_id="s3_key_sensor_async",
            bucket_key="key",
            bucket_name="bucket",
            check_fn=check_fn,
        )
        sensor.execute_complete(context={}, event={"status": "running", "files": [{"Size": 10}]})

        mock_defer.assert_called_once()

    @parameterized.expand(
        [
            ["s3://bucket/key", None],
            ["key", "bucket"],
        ]
    )
    @mock.patch(f"{MODULE}.S3KeySensorAsync.poke", return_value=False)
    @mock.patch("airflow.providers.amazon.aws.sensors.s3.S3Hook")
    def test_s3_key_sensor_execute_complete_error(self, key, bucket, mock_hook, mock_poke):
        """
        Asserts that a task is completed with error status.
        """
        mock_hook.check_for_key.return_value = False

        sensor = S3KeySensorAsync(
            task_id="s3_key_sensor_async",
            bucket_key=key,
            bucket_name=bucket,
        )
        with pytest.raises(AirflowException):
            sensor.execute_complete(
                context={}, event={"status": "error", "message": "mocked error", "soft_fail": False}
            )

    @parameterized.expand(
        [
            ["s3://bucket/key", None],
            ["key", "bucket"],
        ]
    )
    @mock.patch(f"{MODULE}.S3KeySensorAsync.poke", return_value=False)
    @mock.patch("airflow.providers.amazon.aws.sensors.s3.S3Hook")
    @mock.patch.object(S3KeySensorAsync, "defer")
    @mock.patch("astronomer.providers.amazon.aws.sensors.s3.S3KeyTrigger")
    def test_s3_key_sensor_async_with_mock_defer(
        self, key, bucket, mock_trigger, mock_defer, mock_hook, mock_poke
    ):
        """
        Asserts that a task is deferred and an S3KeyTrigger will be fired
        when the S3KeySensorAsync is executed.
        """
        mock_hook.check_for_key.return_value = False

        sensor = S3KeySensorAsync(
            task_id="s3_key_sensor_async",
            bucket_key=key,
            bucket_name=bucket,
        )

        sensor.execute(context=None)

        mock_defer.assert_called()
        mock_defer.assert_called_once_with(
            timeout=timedelta(days=7), trigger=mock_trigger.return_value, method_name="execute_complete"
        )

    @mock.patch(f"{MODULE}.S3KeySensorAsync.poke", return_value=False)
    @mock.patch("airflow.providers.amazon.aws.sensors.s3.S3Hook.check_for_key")
    def test_parse_bucket_key_from_jinja(self, mock_check, mock_poke):
        mock_check.return_value = False

        Variable.set("test_bucket_key", "s3://bucket/key")

        execution_date = timezone.datetime(2020, 1, 1)

        dag = DAG("test_s3_key", start_date=execution_date)
        op = S3KeySensorAsync(
            task_id="s3_key_sensor",
            bucket_key="s3://bucket/key",
            bucket_name=None,
            dag=dag,
        )

        dag_run = DagRun(dag_id=dag.dag_id, execution_date=execution_date, run_id="test")
        ti = TaskInstance(task=op)
        ti.dag_run = dag_run
        context = ti.get_template_context()
        ti.render_templates(context)

        assert op.bucket_key == ["s3://bucket/key"]
        assert op.bucket_name is None

    @mock.patch(f"{MODULE}.S3KeySensorAsync.poke", return_value=False)
    @mock.patch("airflow.providers.amazon.aws.sensors.s3.S3Hook")
    def test_s3_key_sensor_with_wildcard_async(self, mock_hook, mock_poke, context):
        """
        Asserts that a task with wildcard=True is deferred and an S3KeyTrigger will be fired
        when the S3KeySensorAsync is executed.
        """
        mock_hook.check_for_key.return_value = False

        sensor = S3KeySensorAsync(
            task_id="s3_key_sensor_async", bucket_key="s3://test_bucket/file", wildcard_match=True
        )

        with pytest.raises(TaskDeferred) as exc:
            sensor.execute(context)

        assert isinstance(exc.value.trigger, S3KeyTrigger), "Trigger is not a S3KeyTrigger"

    def test_soft_fail(self):
        """Raise AirflowSkipException in case soft_fail is true"""
        sensor = S3KeySensorAsync(
            task_id="s3_key_sensor_async", bucket_key="key", bucket_name="bucket", soft_fail=True
        )
        with pytest.raises(AirflowSkipException):
            sensor.execute_complete(
                context={}, event={"status": "error", "message": "mocked error", "soft_fail": True}
            )

    @pytest.mark.parametrize(
        "soft_fail,exception",
        [
            (True, AirflowSkipException),
            (False, Exception),
        ],
    )
    @mock.patch(f"{MODULE}.S3KeySensorAsync.poke")
    def test_execute_handle_exception(self, mock_poke, soft_fail, exception):
        mock_poke.side_effect = Exception()
        sensor = S3KeySensorAsync(
            task_id="s3_key_sensor_async", bucket_key="key", bucket_name="bucket", soft_fail=soft_fail
        )
        with pytest.raises(exception):
            sensor.execute(context={})


class TestS3KeysUnchangedSensorAsync:
    @mock.patch(f"{MODULE}.S3KeysUnchangedSensorAsync.defer")
    @mock.patch(f"{MODULE}.S3KeysUnchangedSensorAsync.poke", return_value=True)
    def test_s3_keys_unchanged_sensor_async_finish_before_deferred(self, mock_poke, mock_defer, context):
        """Assert task is not deferred when it receives a finish status before deferring"""
        S3KeysUnchangedSensorAsync(
            task_id="s3_keys_unchanged_sensor", bucket_name="test_bucket", prefix="test"
        )
        assert not mock_defer.called

    @mock.patch(f"{MODULE}.S3KeysUnchangedSensorAsync.poke", return_value=False)
    @mock.patch("airflow.providers.amazon.aws.sensors.s3.S3Hook")
    def test_s3_keys_unchanged_sensor_check_trigger_instance(self, mock_hook, mock_poke, context):
        """
        Asserts that a task is deferred and an S3KeysUnchangedTrigger will be fired
        when the S3KeysUnchangedSensorAsync is executed.
        """
        mock_hook.check_for_key.return_value = False

        sensor = S3KeysUnchangedSensorAsync(
            task_id="s3_keys_unchanged_sensor", bucket_name="test_bucket", prefix="test"
        )

        with pytest.raises(TaskDeferred) as exc:
            sensor.execute(context)

        assert isinstance(
            exc.value.trigger, S3KeysUnchangedTrigger
        ), "Trigger is not a S3KeysUnchangedTrigger"

    @parameterized.expand([["bucket", "test"]])
    @mock.patch(f"{MODULE}.S3KeysUnchangedSensorAsync.poke", return_value=False)
    @mock.patch("airflow.providers.amazon.aws.sensors.s3.S3Hook")
    def test_s3_keys_unchanged_sensor_execute_complete_success(self, bucket, prefix, mock_hook, mock_poke):
        """
        Asserts that a task completed with success status
        """
        mock_hook.check_for_key.return_value = False

        sensor = S3KeysUnchangedSensorAsync(
            task_id="s3_keys_unchanged_sensor",
            bucket_name=bucket,
            prefix=prefix,
        )
        assert sensor.execute_complete(context={}, event={"status": "success"}) is None

    @parameterized.expand([["bucket", "test"]])
    @mock.patch(f"{MODULE}.S3KeysUnchangedSensorAsync.poke", return_value=False)
    @mock.patch("airflow.providers.amazon.aws.sensors.s3.S3Hook")
    def test_s3_keys_unchanged_sensor_execute_complete_error(self, bucket, prefix, mock_hook, mock_poke):
        """
        Asserts that a task is completed with error.
        """
        mock_hook.check_for_key.return_value = False

        sensor = S3KeysUnchangedSensorAsync(
            task_id="s3_keys_unchanged_sensor",
            bucket_name=bucket,
            prefix=prefix,
        )
        with pytest.raises(AirflowException):
            sensor.execute_complete(context={}, event={"status": "error", "message": "Mocked error"})

    @mock.patch(f"{MODULE}.S3KeysUnchangedSensorAsync.poke", return_value=False)
    def test_s3_keys_unchanged_sensor_raise_value_error(self, mock_poke):
        """
        Test if the S3KeysUnchangedTrigger raises Value error for negative inactivity_period.
        """
        with pytest.raises(ValueError):
            S3KeysUnchangedSensorAsync(
                task_id="s3_keys_unchanged_sensor",
                bucket_name="test_bucket",
                prefix="test",
                inactivity_period=-100,
            )


class TestS3KeySizeSensorAsync(unittest.TestCase):
    def test_deprecation_warnings_generated(self):
        with pytest.warns(expected_warning=DeprecationWarning):
            S3KeySizeSensorAsync(task_id="s3_size_sensor", bucket_key="s3://test_bucket/file")


class TestS3PrefixSensorAsync(unittest.TestCase):
    def test_deprecation_warnings_generated(self):
        with pytest.warns(expected_warning=DeprecationWarning):
            S3PrefixSensorAsync(
                task_id="check_s3_prefix_sensor",
                bucket_name="test_bucket",
                prefix="test",
            )
