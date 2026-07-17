import constants


def test_constants_importable_and_sane():
    assert constants.APP_NAME == "BlueStacks Root GUI"
    assert constants.MODE_READWRITE == "Normal"
