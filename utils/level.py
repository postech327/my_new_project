def calculate_level(points: int) -> int:
    """
    기본 레벨 공식
    100점당 1레벨 상승
    """
    return 1 + (points // 100)