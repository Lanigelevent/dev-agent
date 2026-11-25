from calc import add, label


def test_add():
    assert add(2, 3) == 5


def test_label():
    assert label("Ada") == "Hello Ada"
