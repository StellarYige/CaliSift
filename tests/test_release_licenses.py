from scripts.collect_licenses import is_license_text


def test_compound_dependency_notices_are_collected():
    for filename in (
        "onnxruntime/ThirdPartyNotices.txt",
        "licenses/LICENSE.APACHE",
        "licenses/LICENSE.BSD",
        "licenses/LICENSE_GEOS",
        "licenses/LICENSE_win32",
        "LICENCE.python",
        "COPYING.LESSER",
        "NOTICE",
    ):
        assert is_license_text(filename), filename


def test_pyobjc_copying_extension_is_not_a_license():
    for filename in (
        "PyObjCTest/copying.cpython-311-darwin.so",
        "PyObjCTest/copying.py",
        "LICENSE.dll",
        "COPYING.o",
        "licensing_helper.py",
    ):
        assert not is_license_text(filename), filename
