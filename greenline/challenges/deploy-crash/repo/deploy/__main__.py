from __future__ import annotations

import json

from .bootstrap import boot


def main() -> None:
    service = boot()
    print(json.dumps(service.health(), sort_keys=True))


if __name__ == "__main__":
    main()
