"""
handlers/__init__.py
━━━━━━━━━━━━━━━━━━━━
119 SOP — 次類別 Handler Registry

新增次類別只需：
  1. 在 handlers/ 下建立對應 .py，繼承 SubCategoryHandler 並覆寫所需鉤子
  2. 在 _REGISTRY 中登記 {次類別名稱: HandlerInstance}
  3. 主流程 sop_119_engine.py 零改動
"""

from __future__ import annotations

from .base import SubCategoryHandler
from .急病 import JiBingHandler
from .一般受傷 import GeneralInjuryHandler
from .路倒 import LuDaoHandler
from .精神異常 import JingShenYiChangHandler
from .打架受傷 import DaJiaShouShangHandler
from .吞食藥物 import TunShiYaoWuHandler
from .墜落傷 import ZhuiLuoShangHandler
from .孕婦急產 import YunFuJiChanHandler
from .燒炭 import ShaoTanHandler
from .燒燙傷 import ShaoTangShangHandler
from .割腕 import GeWanHandler
from .上吊 import ShangDiaoHandler
from .車禍 import CheHuoHandler

_REGISTRY: dict[str, SubCategoryHandler] = {
    "急病":    JiBingHandler(),
    "一般受傷": GeneralInjuryHandler(),
    "路倒":    LuDaoHandler(),
    "精神異常": JingShenYiChangHandler(),
    "打架受傷": DaJiaShouShangHandler(),
    "吞食藥物": TunShiYaoWuHandler(),
    "墜落傷":  ZhuiLuoShangHandler(),
    "孕婦急產": YunFuJiChanHandler(),
    "燒炭":    ShaoTanHandler(),
    "燒燙傷":  ShaoTangShangHandler(),
    "割腕":    GeWanHandler(),
    "上吊":    ShangDiaoHandler(),
    "車禍":    CheHuoHandler(),
}

_DEFAULT_HANDLER = SubCategoryHandler()


def get_handler(sub_cat: str | None) -> SubCategoryHandler:
    """依次類別名稱取得對應 handler；未登記的次類別返回通用基類 handler。"""
    return _REGISTRY.get(sub_cat or "", _DEFAULT_HANDLER)
