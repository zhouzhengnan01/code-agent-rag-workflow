"""
基础测试文件
包含简单的数学运算函数及其测试
"""


def add(a, b):
    """加法"""
    return a + b


def subtract(a, b):
    """减法"""
    return a - b


def multiply(a, b):
    """乘法"""
    return a * b


def divide(a, b):
    """除法"""
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b


def test_add():
    """测试加法"""
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0
    print("✓ 加法测试通过")


def test_subtract():
    """测试减法"""
    assert subtract(5, 3) == 2
    assert subtract(0, 5) == -5
    assert subtract(-1, -1) == 0
    print("✓ 减法测试通过")


def test_multiply():
    """测试乘法"""
    assert multiply(2, 3) == 6
    assert multiply(-2, 3) == -6
    assert multiply(0, 5) == 0
    print("✓ 乘法测试通过")


def test_divide():
    """测试除法"""
    assert divide(6, 2) == 3
    assert divide(5, 2) == 2.5
    assert divide(-6, 2) == -3
    
    # 测试除以零的情况
    try:
        divide(1, 0)
        assert False, "应该抛出异常"
    except ValueError as e:
        assert str(e) == "除数不能为零"
    
    print("✓ 除法测试通过")


def run_all_tests():
    """运行所有测试"""
    print("开始运行测试...")
    print("=" * 50)
    
    test_add()
    test_subtract()
    test_multiply()
    test_divide()
    
    print("=" * 50)
    print("✓ 所有测试通过！")


if __name__ == "__main__":
    run_all_tests()
