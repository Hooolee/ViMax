from typing import List, Dict, Any, Literal

from interfaces import ShotDescription, Camera


ShotSizeRank = {
    "extreme_long": 0,
    "long": 1,
    "medium_long": 2,
    "medium": 3,
    "medium_close": 4,
    "close_up": 5,
    "extreme_close_up": 6,
}

AngleRank = {
    "worm_eye": 0,
    "low": 1,
    "eye_level": 2,
    "high": 3,
    "bird_eye": 4,
    "dutch": 5,  # dutch is special; treat as drastic change
}


def check_continuity(
    shots: List[ShotDescription],
    camera_tree: List[Camera],
) -> Dict[str, Any]:
    """
    Basic continuity checks for 180-degree rule and 30-degree rule.

    Returns a report dict:
    {
      'passed': bool,
      'violations': [
         { 'shot_idx': int, 'type': '180_rule'|'30_degree', 'message': str, 'suggestion': str }
      ]
    }
    """

    violations: List[Dict[str, Any]] = []

    # 1) 180-degree rule: avoid flipping left/right screen direction between adjacent shots
    def is_lr_dir(d: str) -> bool:
        return d in ("L_to_R", "R_to_L")

    for i in range(len(shots) - 1):
        a, b = shots[i], shots[i + 1]
        if is_lr_dir(a.screen_direction) and is_lr_dir(b.screen_direction):
            if a.screen_direction != b.screen_direction:
                # potential axis jump
                # soft-allow if explicit transition aims to diffuse (dissolve/fade/wipe)
                if a.transition_out not in ("dissolve", "fade", "wipe") and b.transition_in not in (
                    "dissolve",
                    "fade",
                    "wipe",
                ):
                    violations.append(
                        {
                            "shot_idx": b.idx,
                            "type": "180_rule",
                            "message": f"Screen direction flips from {a.screen_direction} to {b.screen_direction} at cut between shots {a.idx}->{b.idx}.",
                            "suggestion": "保持同一运动/视线方向（例如统一为 L_to_R），或在中性轴位镜头/建立镜头后再过渡；也可使用溶/叠等过渡弱化方向跳变。",
                        }
                    )

    # 2) 30-degree rule: avoid jump cuts with minimal angle/size change between adjacent shots
    for i in range(len(shots) - 1):
        a, b = shots[i], shots[i + 1]
        # if two different camera positions (either cam idx differs or parent-child is not strongly related)
        if a.cam_idx != b.cam_idx:
            size_a, size_b = ShotSizeRank.get(a.shot_size, 3), ShotSizeRank.get(b.shot_size, 3)
            ang_a, ang_b = AngleRank.get(a.angle, 2), AngleRank.get(b.angle, 2)

            size_diff = abs(size_a - size_b)
            ang_diff = abs(ang_a - ang_b)
            lens_diff = abs(a.lens_equiv_mm - b.lens_equiv_mm)

            # consider a violation when everything is almost the same (a typical jump cut risk)
            if size_diff == 0 and ang_diff <= 0 and lens_diff < 10 and a.screen_direction == b.screen_direction:
                violations.append(
                    {
                        "shot_idx": b.idx,
                        "type": "30_degree",
                        "message": f"Possible jump cut: consecutive shots {a.idx}->{b.idx} have nearly identical size/angle/lens/direction.",
                        "suggestion": "改变第二个镜头的角度或镜头尺寸（如 medium → close_up 或 eye_level → low），或加入明显的机位移动/切换，避免小角度切换造成跳切。",
                    }
                )

    return {"passed": len(violations) == 0, "violations": violations}

