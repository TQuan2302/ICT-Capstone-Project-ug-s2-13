import pytest

""" 
 Unit testing for detect.py using the pytest framework
 2026 Aidan Matthews - ICT Capstone Project UG-S2-13
"""


def f():
    raise SystemExit(1)


def test_mytest():
    with pytest.raises(SystemExit):
        f()
