import pytest

from number7.config import get_settings
from number7.data.audit import audit_report
from number7.data.bridge import make_client

pytestmark = pytest.mark.vm


def test_norgate_audit_all_green():
    report = audit_report(make_client(get_settings()))
    assert all(report.values()), report
