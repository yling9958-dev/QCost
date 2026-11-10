#!/usr/bin/env python3
"""Compatibility entry for the complete release validation."""
import json
from check_release import check

if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
