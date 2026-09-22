"""让 `python3 -m claude_tg_notify` 可用（pip 安装后 hook 走这条路）。"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
