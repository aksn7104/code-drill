"""無料版・有料版のどちらで動いているかを知らせる（試験用）。

無料版には、キャラ・称号・すごろく（fun.py）がない。その機能の試験は、無料版では「対象外」として飛ばす。
使い方：  from tests.editions import paid_only  →  @paid_only を、試験のクラスや関数に付ける
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAID = (ROOT / "fun.py").exists()

paid_only = unittest.skipUnless(PAID, "有料版の機能（無料版には含まれない）")
